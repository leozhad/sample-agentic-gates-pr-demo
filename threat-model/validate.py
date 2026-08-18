"""Threat-model lane v1 — deterministic gate (SPEC §3.4).

The threat model is code: `threat-model/app.tc.json` (Threat Composer format)
travels in the guarded repo and is diffed and reviewed like everything else.
This validator fails the gate if:
  (a) the file is invalid (JSON / minimal Threat Composer shape),
  (b) a trust boundary declared in threat-model/boundaries.yaml has no threat
      that references it (coverage check), or
  (c) infra changed in this diff but the threat model was untouched
      (staleness heuristic — the demo's favorite trick).

No LLM anywhere in this file, on purpose: this is the deterministic backstop
the agentic lane (stride_agent.py, advisory) sits beside, not instead of.

Usage:
    python validate.py --model threat-model/app.tc.json \
        --boundaries threat-model/boundaries.yaml [--changed-files files.txt]
Exit 0 = pass, 1 = gate failure (reasons on stdout).
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import pathlib
import sys

import yaml

INFRA_PATTERNS = ["infra/**", "**/infra/**", "template.yaml", "**/template.yaml",
                  "**/*.tf", "**/cdk.json"]


def load_model(path: pathlib.Path) -> tuple[dict | None, list[str]]:
    errors: list[str] = []
    try:
        doc = json.loads(path.read_text())
    except FileNotFoundError:
        return None, [f"threat model missing: {path}"]
    except json.JSONDecodeError as exc:
        return None, [f"threat model is not valid JSON: {exc}"]
    if not isinstance(doc, dict):
        return None, ["threat model root must be a JSON object"]
    threats = doc.get("threats")
    if not isinstance(threats, list) or not threats:
        errors.append("threat model has no threats[] — an empty model is not a model")
    for i, t in enumerate(threats or []):
        if not isinstance(t, dict) or not t.get("statement"):
            errors.append(f"threats[{i}] missing 'statement'")
    return doc, errors


def boundary_coverage(model: dict, boundaries_path: pathlib.Path) -> list[str]:
    try:
        declared = yaml.safe_load(boundaries_path.read_text()) or {}
    except FileNotFoundError:
        return []  # no declared boundaries => nothing to cover
    errors = []
    blob = json.dumps(model).lower()
    for b in declared.get("boundaries", []):
        bid, name = b.get("id", ""), b.get("name", "")
        if bid.lower() not in blob and name.lower() not in blob:
            errors.append(
                f"trust boundary '{bid or name}' declared in boundaries.yaml has no "
                f"threat referencing it — add a threat or remove the boundary")
    return errors


def staleness(changed_files: list[str]) -> list[str]:
    if not changed_files:
        return []
    infra_changed = [f for f in changed_files
                     if any(fnmatch.fnmatch(f, p) for p in INFRA_PATTERNS)]
    tm_changed = any(f.startswith("threat-model/") for f in changed_files)
    if infra_changed and not tm_changed:
        return [(f"infra changed ({', '.join(infra_changed[:5])}) but threat-model/ "
                 f"was untouched — update app.tc.json or record why no new threats apply")]
    return []


def main() -> int:
    p = argparse.ArgumentParser(description="Deterministic threat-model gate")
    p.add_argument("--model", required=True)
    p.add_argument("--boundaries", required=True)
    p.add_argument("--changed-files", help="newline-separated list of changed paths")
    args = p.parse_args()

    model, errors = load_model(pathlib.Path(args.model))
    if model is not None:
        errors += boundary_coverage(model, pathlib.Path(args.boundaries))
    if args.changed_files:
        changed = [l.strip() for l in
                   pathlib.Path(args.changed_files).read_text().splitlines() if l.strip()]
        errors += staleness(changed)

    if errors:
        print("THREAT-MODEL GATE: FAIL")
        for e in errors:
            print(f"  - {e}")
        return 1
    n = len(model.get("threats", [])) if model else 0
    print(f"THREAT-MODEL GATE: PASS ({n} threats, boundaries covered, model fresh)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
