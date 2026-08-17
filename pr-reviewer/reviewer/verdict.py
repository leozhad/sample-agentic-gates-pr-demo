"""Findings and verdicts.

THE core security property of this gate (SPEC G2): the verdict is COMPUTED
here from rule metadata + validated finding counts. The model never emits a
verdict, and nothing the model writes (message text, suggested code, or an
injected instruction inside the diff) can change which rules are blocking.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import Enum

from .rules import RuleSet


class Verdict(str, Enum):
    PASS = "PASS"                     # no blocking findings
    FAIL = "FAIL"                     # >=1 blocking finding at/above threshold
    ADVISORY_ERROR = "ADVISORY_ERROR"  # infra/parse failure under fail_mode=open
    BLOCKED_ERROR = "BLOCKED_ERROR"    # infra/parse failure under fail_mode=closed


@dataclass(frozen=True)
class Finding:
    rule_id: str
    path: str
    line: int
    message: str
    confidence: int
    severity: str = "medium"
    blocking: bool = False            # ALWAYS overwritten from the rule set
    suggested_code: str | None = None


class FindingsValidationError(ValueError):
    """Model output did not conform to the findings contract."""


def parse_model_findings(raw_text: str, ruleset: RuleSet) -> list[Finding]:
    """Validate model output into Findings.

    Contract: the model returns a JSON object {"findings": [...]}. We accept a
    fenced code block around it. Every finding must reference a known rule id;
    unknown rule ids are DROPPED (a hallucinated or injected rule id must not
    influence anything). severity and blocking are taken from the RULE, never
    from the model.
    """
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        text = text.split("\n", 1)[1] if "\n" in text else text
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FindingsValidationError(f"model output is not valid JSON: {exc}") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("findings"), list):
        raise FindingsValidationError('model output must be {"findings": [...]}')

    findings: list[Finding] = []
    for raw in doc["findings"]:
        if not isinstance(raw, dict):
            continue
        rule = ruleset.by_id(str(raw.get("rule_id", "")))
        if rule is None:
            continue  # unknown/injected rule id: drop silently, count nothing
        path = str(raw.get("path", ""))
        if not path or not rule.matches_path(path):
            continue  # finding outside the rule's declared scope doesn't count
        try:
            line = max(0, int(raw.get("line", 0)))
            confidence = int(raw.get("confidence", 0))
        except (TypeError, ValueError):
            continue
        confidence = min(100, max(0, confidence))
        findings.append(
            Finding(
                rule_id=rule.id,
                path=path,
                line=line,
                message=str(raw.get("message", ""))[:2000],
                confidence=confidence,
                severity=rule.severity,          # from rule, not model
                blocking=rule.blocking,          # from rule, not model
                suggested_code=(str(raw["suggested_code"])[:2000]
                                if raw.get("suggested_code") else None),
            )
        )
    return findings[: ruleset.max_findings]


@dataclass(frozen=True)
class GateResult:
    verdict: Verdict
    findings: tuple[Finding, ...]
    suppressed_below_threshold: int
    error: str | None = None

    @property
    def blocking_count(self) -> int:
        return sum(1 for f in self.findings if f.blocking)

    def to_json(self) -> str:
        return json.dumps(
            {
                "verdict": self.verdict.value,
                "stats": {
                    "total": len(self.findings),
                    "blocking": self.blocking_count,
                    "suppressed_below_threshold": self.suppressed_below_threshold,
                },
                "findings": [asdict(f) for f in self.findings],
                "error": self.error,
            },
            indent=2,
        )


def compute_verdict(findings: list[Finding], ruleset: RuleSet) -> GateResult:
    """Apply the confidence floor, then derive the verdict from counts."""
    kept = [f for f in findings if f.confidence >= ruleset.confidence_threshold]
    suppressed = len(findings) - len(kept)
    blocking = any(f.blocking for f in kept)
    return GateResult(
        verdict=Verdict.FAIL if blocking else Verdict.PASS,
        findings=tuple(kept),
        suppressed_below_threshold=suppressed,
    )


def error_result(ruleset: RuleSet, error: str) -> GateResult:
    """Infra/parse failure path: fail-open (advisory) or fail-closed per rules."""
    verdict = Verdict.ADVISORY_ERROR if ruleset.fail_mode == "open" else Verdict.BLOCKED_ERROR
    return GateResult(verdict=verdict, findings=(), suppressed_below_threshold=0, error=error)
