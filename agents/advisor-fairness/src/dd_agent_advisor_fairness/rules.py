"""The rule table (`checks.yaml`): whether a record meets each check is decided here, by rule and
never by a model."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from dd_agent_advisor_fairness.classes import PublishedRecord

CHECKS = Path(__file__).with_name("checks.yaml")
TESTS = frozenset({"present", "doi", "one_of", "any_in", "covered"})
# A DOI, bare or as a resolver URL: the 10. prefix, a registrant code, a slash and a suffix.
DOI = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)?10\.\d{4,9}/\S+$", re.IGNORECASE)


@dataclass(frozen=True)
class Rule:
    principle: str
    check: str
    test: str
    field: str
    recommendation: str
    priority: int
    after_deposit: bool = False
    values: frozenset[str] = frozenset()
    by: str | None = None


def load_checks(path: Path = CHECKS) -> list[Rule]:
    with path.open(encoding="utf-8") as fh:
        table = yaml.safe_load(fh)
    rules = []
    for entry in table:
        rule = Rule(
            principle=str(entry["principle"]),
            check=str(entry["check"]),
            test=str(entry["test"]),
            field=str(entry["field"]),
            recommendation=" ".join(str(entry["recommendation"]).split()),
            priority=int(entry["priority"]),
            after_deposit=bool(entry.get("after_deposit", False)),
            values=frozenset(str(v).lower() for v in entry.get("values", ())),
            by=entry.get("by"),
        )
        if rule.test not in TESTS:
            raise ValueError(f"{path}: check {rule.check!r} has unknown test {rule.test!r}")
        if rule.field not in PublishedRecord.model_fields:
            raise ValueError(f"{path}: check {rule.check!r} names unknown field {rule.field!r}")
        if rule.test == "covered" and rule.by not in PublishedRecord.model_fields:
            raise ValueError(f"{path}: check {rule.check!r} needs `by`, a field of the record")
        if not rule.principle or rule.principle[0] not in "FAIR":
            raise ValueError(f"{path}: check {rule.check!r} names no FAIR principle")
        rules.append(rule)
    return rules


def meets(rule: Rule, record: PublishedRecord) -> bool:
    value = getattr(record, rule.field)
    match rule.test:
        case "present":
            return bool(value)
        case "doi":
            return value is not None and DOI.match(value.strip()) is not None
        case "one_of":
            return value is not None and value.strip().lower() in rule.values
        case "any_in":
            return any(item.strip().lower() in rule.values for item in value)
        case "covered":
            assert rule.by is not None  # load_checks requires it
            return bool(value) and len(getattr(record, rule.by)) >= len(value)
    raise ValueError(f"unknown test {rule.test!r}")
