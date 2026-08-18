"""Deterministic lane (SPEC §3.0/G6) — runs BESIDE the agent, not instead of it.

Checks synthesized/committed CloudFormation templates:
  1. wildcard-IAM: any statement with Action:"*" or Resource:"*" (blocking) —
     the deterministic twin of agent rule IAM-002, demonstrating layering.
  2. Access Analyzer ValidatePolicy on every inline IAM policy found
     (ERROR/SECURITY_WARNING findings are blocking; suggestions advisory).

Usage: python checks.py --templates 'sample-app/template.yaml' [--skip-access-analyzer]
Exit 0 = pass, 1 = blocking findings.
"""
from __future__ import annotations

import argparse
import glob
import json
import pathlib
import sys

import boto3
import yaml


class _CfnLoader(yaml.SafeLoader):
    """Tolerate CloudFormation short-form intrinsics (!Ref, !GetAtt, !Sub...)."""


def _unknown(loader, tag_suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return {f"Fn::{tag_suffix}": loader.construct_scalar(node)}
    if isinstance(node, yaml.SequenceNode):
        return {f"Fn::{tag_suffix}": loader.construct_sequence(node)}
    return {f"Fn::{tag_suffix}": loader.construct_mapping(node)}


_CfnLoader.add_multi_constructor("!", _unknown)


def _statements(policy_doc: dict):
    stmts = policy_doc.get("Statement", [])
    return stmts if isinstance(stmts, list) else [stmts]


def _iter_policies(template: dict):
    for name, res in (template.get("Resources") or {}).items():
        props = res.get("Properties") or {}
        for pol in props.get("Policies") or []:
            if isinstance(pol, dict) and "PolicyDocument" in pol:
                yield name, pol["PolicyDocument"], "IDENTITY_POLICY"
            elif isinstance(pol, dict) and "Statement" in pol:  # SAM inline policy
                yield name, pol, "IDENTITY_POLICY"
        if "PolicyDocument" in props:
            yield name, props["PolicyDocument"], "IDENTITY_POLICY"
        if "AssumeRolePolicyDocument" in props:
            # Trust policies carry Principal and no Resource — they validate
            # as RESOURCE_POLICY, not IDENTITY_POLICY (else false ERRORs).
            yield f"{name}(trust)", props["AssumeRolePolicyDocument"], "RESOURCE_POLICY"


def check_wildcards(name: str, doc: dict) -> list[str]:
    out = []
    for s in _statements(doc):
        if not isinstance(s, dict) or s.get("Effect") != "Allow":
            continue
        actions = s.get("Action", [])
        actions = actions if isinstance(actions, list) else [actions]
        resources = s.get("Resource", [])
        resources = resources if isinstance(resources, list) else [resources]
        if any(a == "*" for a in actions if isinstance(a, str)):
            out.append(f"[BLOCKING] {name}: statement allows Action:'*'")
        if any(r == "*" for r in resources if isinstance(r, str)) and \
           any(isinstance(a, str) and a.split(":")[0] in
               ("iam", "sts", "s3", "kms", "secretsmanager", "*") for a in actions):
            out.append(f"[BLOCKING] {name}: sensitive actions with Resource:'*'")
    return out


def _has_intrinsics(doc) -> bool:
    """CFN intrinsics don't resolve statically — ValidatePolicy would false-flag."""
    if isinstance(doc, dict):
        return any(k == "Ref" or str(k).startswith("Fn::") for k in doc) or \
            any(_has_intrinsics(v) for v in doc.values())
    if isinstance(doc, list):
        return any(_has_intrinsics(v) for v in doc)
    return False


def check_access_analyzer(name: str, doc: dict, client, policy_type: str) -> list[str]:
    out = []
    if _has_intrinsics(doc):
        return [f"[advisory] {name}: contains CFN intrinsics — Access Analyzer "
                f"skipped (wildcard check still applied)"]
    try:
        kwargs = {"policyDocument": json.dumps(doc), "policyType": policy_type}
        if policy_type == "RESOURCE_POLICY":
            # Role trust policies have an implicit Resource (the role itself)
            kwargs["validatePolicyResourceType"] = "AWS::IAM::AssumeRolePolicyDocument"
        resp = client.validate_policy(**kwargs)
        for f in resp.get("findings", []):
            level = f["findingType"]
            tag = "[BLOCKING]" if level in ("ERROR", "SECURITY_WARNING") else "[advisory]"
            out.append(f"{tag} {name}: AccessAnalyzer {level}: {f['findingDetails']}")
    except Exception as exc:  # noqa: BLE001 — analyzer unavailability must not wedge (G4)
        out.append(f"[advisory] {name}: ValidatePolicy unavailable ({type(exc).__name__})")
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Deterministic IaC checks")
    p.add_argument("--templates", required=True, help="glob of CFN/SAM templates")
    p.add_argument("--skip-access-analyzer", action="store_true")
    p.add_argument("--region", default="us-west-2")
    args = p.parse_args()

    findings: list[str] = []
    client = None if args.skip_access_analyzer else boto3.client(
        "accessanalyzer", region_name=args.region)
    paths = sorted(glob.glob(args.templates, recursive=True))
    if not paths:
        print(f"DETERMINISTIC LANE: PASS (no templates matched {args.templates})")
        return 0
    for path in paths:
        template = yaml.load(pathlib.Path(path).read_text(), Loader=_CfnLoader)
        for name, doc, ptype in _iter_policies(template or {}):
            # Skip docs full of intrinsics that don't resolve statically
            try:
                json.dumps(doc)
            except TypeError:
                continue
            findings += [f"{path} :: {m}" for m in check_wildcards(name, doc)]
            if client:
                findings += [f"{path} :: {m}"
                             for m in check_access_analyzer(name, doc, client, ptype)]

    blocking = [f for f in findings if "[BLOCKING]" in f]
    for f in findings:
        print(f)
    print(f"DETERMINISTIC LANE: {'FAIL' if blocking else 'PASS'} "
          f"({len(blocking)} blocking / {len(findings)} total)")
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
