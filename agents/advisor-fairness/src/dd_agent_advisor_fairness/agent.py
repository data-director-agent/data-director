"""advisor.fairness: the FAIR Assessor persona (ADR-0033). A mock.

Serves `post.fairness` (R12) and `post.retrofit` (R9). It checks the metadata of an already
published dataset, as the researcher gives it, against a short list of FAIR-related presence
checks, and suggests a retrofit for each check not met. It is advisory and changes no record: the
researcher decides what to submit to the repository. It gives no score and is not a FAIRness
evaluation (R4).

The mock applies the rule table in `checks.yaml` to its input. It retrieves nothing, resolves no
identifier, consults no source and calls no model, so its grounding mode is `none` and it cites
only its input. The real assessor, drawing on community tools such as F-UJI and discovering
related datasets, is TODO(#361).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml

from dd_agent_advisor_fairness.classes import FairCheck, FairnessReport, PublishedRecord
from dd_sdk import serve
from dd_sdk.agent import AgentResult, AgentSpec, Derived, RunContext
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
    Derivation,
    EvidenceItem,
    GroundingMode,
    GroundingRef,
    InvocationRequest,
    Outcome,
    OutcomeStatus,
    ReasonCode,
)
from dd_sdk.evidence import HASH_ALGORITHM, INPUT_CANONICALISATION

CHECKS = Path(__file__).with_name("checks.yaml")
TESTS = frozenset({"present", "doi", "one_of", "any_in", "covered"})
# A DOI, bare or as a resolver URL: the 10. prefix, a registrant code, a slash and a suffix.
DOI = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)?10\.\d{4,9}/\S+$", re.IGNORECASE)

LIMITATIONS = (
    "This is a mock and not a FAIRness evaluation: it checks only whether the metadata given here "
    "are present and in an expected form, against a short list.",
    "Nothing was retrieved: the identifier was not resolved and the repository's record, files and "
    "landing page were not read.",
    "It does not yet discover related datasets or outputs.",
    "Its suggestions change no record. Submit any change to the repository yourself.",
)


@dataclass(frozen=True)
class Rule:
    principle: str
    check: str
    test: str
    field: str
    recommendation: str
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
            values=frozenset(str(v).lower() for v in entry.get("values", ())),
            by=entry.get("by"),
        )
        if rule.test not in TESTS:
            raise ValueError(f"{path}: check {rule.check!r} has unknown test {rule.test!r}")
        if rule.field not in PublishedRecord.model_fields:
            raise ValueError(f"{path}: check {rule.check!r} names unknown field {rule.field!r}")
        if rule.test == "covered" and rule.by not in PublishedRecord.model_fields:
            raise ValueError(f"{path}: check {rule.check!r} needs `by`, a field of the record")
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


class FairAssessor:
    spec = AgentSpec(
        agent_id="advisor.fairness",
        version="0.1.0a1",
        title="FAIR Assessor",
        description=(
            "Mock. Checks the metadata given for a published dataset against a short list of "
            "FAIR-related presence checks and suggests what to retrofit. Not a FAIRness "
            "evaluation; retrieves nothing and changes no record."
        ),
        action_class="advise",
        accepts=(ClassSchema.of(PublishedRecord),),
        grounding_mode=GroundingMode.NONE,
        payload=ClassSchema.of(FairnessReport),
        derivations={
            "checks.principle": Derived(Derivation.TEMPLATE),
            "checks.check": Derived(Derivation.TEMPLATE),
            "checks.met": Derived(Derivation.LEXICAL),
            "checks.recommendation": Derived(Derivation.TEMPLATE),
            "limitations": Derived(Derivation.TEMPLATE),
        },
        serves=("post.fairness", "post.retrofit"),
    )

    def __init__(self, rules: list[Rule] | None = None) -> None:
        self.rules = rules if rules is not None else load_checks()

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        record = request.input
        assert isinstance(record, PublishedRecord)  # the conductor checked spec.accepts
        if not record.identifier and not record.title:
            return AgentResult(
                outcome=Outcome(
                    status=OutcomeStatus.ABSTAINED,
                    reason_code=ReasonCode.INSUFFICIENT_INPUT,
                    statement="Give the published dataset's identifier or title.",
                )
            )

        checks = []
        for rule in self.rules:
            met = meets(rule, record)
            checks.append(
                FairCheck(
                    principle=rule.principle,
                    check=rule.check,
                    met=met,
                    recommendation=None if met else rule.recommendation,
                )
            )
        unmet = sum(not c.met for c in checks)

        ref = GroundingRef(source_id=ctx.input_ref, content_hash=ctx.input_hash)
        return AgentResult(
            outcome=Outcome(
                status=OutcomeStatus.SUCCEEDED,
                statement=(
                    f"Mock: the metadata given meet {len(checks) - unmet} of {len(checks)} "
                    f"presence checks, with {unmet} suggestions to retrofit. This is not a "
                    "FAIRness evaluation."
                ),
            ),
            payload=FairnessReport(
                checks=checks,
                limitations=list(LIMITATIONS),
                grounded_on=[ref],
            ),
            evidence=[
                EvidenceItem(
                    source_id=ctx.input_ref,
                    retrieved_at=datetime.now(UTC),
                    hash_algorithm=HASH_ALGORITHM,
                    canonicalisation=INPUT_CANONICALISATION,
                    content_hash=ctx.input_hash,
                )
            ],
        )


def build() -> FairAssessor:
    return FairAssessor()


def main() -> int:
    """The `dd-advisor-fairness` console script: serve over A2A with `dd_sdk.serve`."""
    return serve.main(build)
