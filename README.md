# agentic-gates-pr-demo (guarded repo — PR surface)

Every pull request is reviewed by the two-stage agentic gate from
[sample-agentic-cicd-gates](https://github.com/leozhad/sample-agentic-cicd-gates):
a GitHub Actions job assumes a repo-scoped AWS IAM role via OIDC, runs the
reviewer against Amazon Bedrock, and posts findings back as a PR review with
inline comments. Blocking findings post as REQUEST_CHANGES and fail the check.

Anti-tamper: the workflow runs the reviewer and rules from the PR's **base
ref** (`base-tooling/` checkout) — a PR cannot rewrite its own gate.

Rules live in `.reviewer.yaml`; the vendored agent core is `pr-reviewer/`.
