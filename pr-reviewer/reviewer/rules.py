"""Rules-as-code loader for the agentic review gate.

Rules are the ONLY source of blocking-ness (closed blocking list). The caller
is responsible for reading the YAML from the BASE ref of the change under
review; this module never touches git.
"""
from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field

import yaml

VALID_SEVERITIES = {"low", "medium", "high"}
VALID_FAIL_MODES = {"open", "closed"}


@dataclass(frozen=True)
class Rule:
    id: str
    description: str
    severity: str = "medium"
    blocking: bool = False
    file_patterns: tuple[str, ...] = ("**/*",)

    def matches_path(self, path: str) -> bool:
        return any(
            fnmatch.fnmatch(path, pat) or fnmatch.fnmatch("/" + path, pat)
            for pat in self.file_patterns
        )


@dataclass(frozen=True)
class RuleSet:
    version: int
    confidence_threshold: int = 80
    fail_mode: str = "open"
    max_findings: int = 25
    rules: tuple[Rule, ...] = field(default_factory=tuple)

    def by_id(self, rule_id: str) -> Rule | None:
        return next((r for r in self.rules if r.id == rule_id), None)

    @property
    def has_blocking_rules(self) -> bool:
        return any(r.blocking for r in self.rules)


class RulesError(ValueError):
    """Invalid rules file. Callers decide fail-open/closed; we just refuse to guess."""


def load_rules(text: str) -> RuleSet:
    """Parse and validate a .reviewer.yaml document."""
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:  # pragma: no cover - message passthrough
        raise RulesError(f"rules file is not valid YAML: {exc}") from exc
    if not isinstance(doc, dict) or doc.get("version") != 1:
        raise RulesError("rules file must be a mapping with version: 1")

    defaults = doc.get("defaults") or {}
    threshold = int(defaults.get("confidence_threshold", 80))
    if not 0 <= threshold <= 100:
        raise RulesError("defaults.confidence_threshold must be 0-100")
    fail_mode = str(defaults.get("fail_mode", "open"))
    if fail_mode not in VALID_FAIL_MODES:
        raise RulesError(f"defaults.fail_mode must be one of {sorted(VALID_FAIL_MODES)}")
    max_findings = int(defaults.get("max_findings", 25))

    rules: list[Rule] = []
    seen: set[str] = set()
    for i, raw in enumerate(doc.get("rules") or []):
        if not isinstance(raw, dict) or "id" not in raw or "description" not in raw:
            raise RulesError(f"rules[{i}] needs id and description")
        rid = str(raw["id"])
        if rid in seen:
            raise RulesError(f"duplicate rule id {rid}")
        seen.add(rid)
        severity = str(raw.get("severity", "medium"))
        if severity not in VALID_SEVERITIES:
            raise RulesError(f"rules[{i}].severity must be one of {sorted(VALID_SEVERITIES)}")
        patterns = tuple(str(p) for p in (raw.get("file_patterns") or ["**/*"]))
        rules.append(
            Rule(
                id=rid,
                description=str(raw["description"]),
                severity=severity,
                blocking=bool(raw.get("blocking", False)),
                file_patterns=patterns,
            )
        )
    if not rules:
        raise RulesError("rules file declares no rules")

    return RuleSet(
        version=1,
        confidence_threshold=threshold,
        fail_mode=fail_mode,
        max_findings=max_findings,
        rules=tuple(rules),
    )
