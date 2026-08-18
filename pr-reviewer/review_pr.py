"""PR-surface gate — run the two-stage reviewer on a GitHub pull request.

Same agent core, third surface (SPEC §3.6): KiroCrew's production pattern —
agent harness in CI compute (a GitHub Actions runner), Bedrock for inference
via an OIDC-assumed IAM role, findings posted back as a PR review.

Anti-tamper: the workflow checks out the PR's BASE ref into base-tooling/ and
runs THIS script (and reads .reviewer.yaml) from there — a PR cannot rewrite
the reviewer or the rules that review it. Verdicts still derive from rule
metadata + finding counts (verdict.py), never model prose, so an injected
instruction in the diff can pollute findings but cannot forge a pass.

Environment (set by the workflow):
  GITHUB_REPOSITORY  owner/repo
  PR_NUMBER          pull request number
  BASE_SHA, HEAD_SHA merge-base endpoints for the diff
  GH_TOKEN           the job's GITHUB_TOKEN (pull-requests: write)
  AWS_REGION         Bedrock region

Exit 0 = PASS/advisory (check green), 1 = blocking findings or fail-closed
error (check red — gate merges with branch protection on this check).
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from reviewer.bedrock_reviewer import DEFAULT_MODEL, review_diff  # noqa: E402
from reviewer.rules import load_rules  # noqa: E402
from reviewer.verdict import Verdict  # noqa: E402

API = "https://api.github.com"
MAX_INLINE = 20  # keep reviews readable; the rest are summarized in the body


def _gh(method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"{API}{path}",
        method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={
            "Authorization": f"Bearer {os.environ['GH_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def _finding_comment(f: dict, agent) -> dict:
    body = (f"{agent.emoji} **{agent.name}** · **{f['rule_id']}** "
            f"({f['severity']}, {'blocking' if f['blocking'] else 'advisory'}, "
            f"confidence {f['confidence']})\n\n{f['message']}")
    if f.get("suggested_code"):
        body += f"\n\n```suggestion\n{f['suggested_code']}\n```"
    return {"path": f["path"], "line": max(1, int(f["line"])),
            "side": "RIGHT", "body": body}


def _review_body(doc: dict, model: str, agent) -> str:
    stats = doc["stats"]
    icon = {"PASS": "✅", "FAIL": "🛑"}.get(doc["verdict"], "⚠️")
    persona = f"\n> {agent.emoji} **{agent.name}** — {agent.persona}\n" \
        if agent.persona else ""
    lines = [
        f"## {icon} {agent.name}: **{doc['verdict']}**",
        persona,
        f"| blocking | total | suppressed below threshold | model | thinking |",
        f"|---|---|---|---|---|",
        f"| {stats['blocking']} | {stats['total']} | "
        f"{stats.get('suppressed_below_threshold', 0)} | `{model}` | "
        f"{agent.thinking} |",
        "",
        "_Verdict derives from rule metadata + finding counts — never from model "
        "prose. Rules, agent config, and reviewer tooling were loaded from the "
        "base ref._",
    ]
    if doc.get("error"):
        lines.insert(2, f"Gate error (per rules `fail_mode`): `{doc['error']}`")
    return "\n".join(lines)


def main() -> int:
    repo = os.environ["GITHUB_REPOSITORY"]
    pr = os.environ["PR_NUMBER"]
    base, head = os.environ["BASE_SHA"], os.environ["HEAD_SHA"]
    region = os.environ.get("AWS_REGION", "us-west-2")

    diff = subprocess.run(
        ["git", "diff", f"{base}...{head}"],
        capture_output=True, text=True, check=True).stdout
    rules_path = pathlib.Path(__file__).resolve().parents[1] / ".reviewer.yaml"
    ruleset = load_rules(rules_path.read_text())

    outcome = review_diff(diff, ruleset,
                          model_id=os.environ.get("REVIEWER_MODEL", DEFAULT_MODEL),
                          region=region)
    doc = json.loads(outcome.result.to_json())
    print(json.dumps(doc, indent=2))
    print(f"VERDICT={doc['verdict']} blocking={doc['stats']['blocking']} "
          f"discovered={outcome.discovery_count} model={outcome.model_id}",
          file=sys.stderr)

    blocking = outcome.result.verdict in (Verdict.FAIL, Verdict.BLOCKED_ERROR)
    payload = {
        "commit_id": head,
        "event": "REQUEST_CHANGES" if blocking else "COMMENT",
        "body": _review_body(doc, outcome.model_id, ruleset.agent),
        "comments": [_finding_comment(f, ruleset.agent)
                     for f in doc["findings"][:MAX_INLINE]],
    }
    status, resp = _gh("POST", f"/repos/{repo}/pulls/{pr}/reviews", payload)
    if status == 422 and payload["comments"]:
        # A finding's line may fall outside the diff hunks — degrade gracefully
        # to a body-only review rather than losing the verdict.
        print(f"inline comments rejected ({resp.get('message')}); "
              f"retrying body-only", file=sys.stderr)
        extra = "\n".join(
            f"- `{c['path']}:{c['line']}` — {c['body'].splitlines()[0]}"
            for c in payload["comments"])
        payload = {"commit_id": head, "event": payload["event"],
                   "body": payload["body"] + "\n\n### Findings\n" + extra}
        status, resp = _gh("POST", f"/repos/{repo}/pulls/{pr}/reviews", payload)
    if status >= 300:
        print(f"failed to post review: HTTP {status} {resp}", file=sys.stderr)
        return 1  # a gate that cannot report must not silently pass

    print(f"posted review {resp.get('id')} ({payload['event']})", file=sys.stderr)
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
