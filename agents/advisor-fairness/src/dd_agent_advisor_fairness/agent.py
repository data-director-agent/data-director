"""advisor.fairness: the FAIR Assessor persona (docs/specs/agents.md). A model-backed alpha.

Serves `post.fairness` (R12) and `post.retrofit` (R9). It checks the metadata of an already
published dataset, as the researcher gives it, against a short list of FAIR-related presence
checks, and recommends a retrofit for each check not met. It is advisory and changes no record:
the researcher decides what to submit to the repository. It gives no score and is not a FAIRness
evaluation (R4).

Whether each check is met is decided by the rule table in `checks.yaml`, never by a model. The
recommendation for each unmet check comes from a writer (`write.py`): the table's own text by
default, or, with a model configured (`DD_FAIRNESS_WRITER`, `factory.py`), text a model writes
for this record, recorded in `recommendation_derivation`. It retrieves nothing and resolves no
identifier, so its grounding mode is `input_only` and it cites only its input. Resolving the
record and running a community FAIRness tool is TODO(#704); discovering related datasets is
TODO(#954).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from dd_agent_advisor_fairness.classes import FairCheck, FairnessReport, PublishedRecord
from dd_agent_advisor_fairness.write import TemplateWriter, Unmet, Writer, Writing
from dd_sdk.agent import (
    AgentResult,
    AgentSpec,
    Derived,
    RunContext,
    abstain,
    input_evidence,
    input_ref,
)
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
    Derivation,
    GroundingMode,
    InvocationRequest,
    Outcome,
    OutcomeStatus,
    ReasonCode,
)

CHECKS = Path(__file__).with_name("checks.yaml")
TESTS = frozenset({"present", "doi", "one_of", "any_in", "covered"})
# A DOI, bare or as a resolver URL: the 10. prefix, a registrant code, a slash and a suffix.
DOI = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)?10\.\d{4,9}/\S+$", re.IGNORECASE)

LIMITATIONS = (
    "This is not a FAIRness evaluation: it checks only whether the metadata given here are present "
    "and in an expected form, against a short list.",
    "Nothing was retrieved: the identifier was not resolved and the repository's record, files and "
    "landing page were not read.",
    "It does not yet discover related datasets or outputs.",
    "Its recommendations change no record. Submit any change to the repository yourself.",
)
MODEL_LIMITATION = (
    "Recommendations marked as written by a model were tailored to the metadata given here and "
    "were not checked against the published record. Review each before acting on it."
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
        version="0.2.0a1",
        title="FAIR Assessor",
        description=(
            "Alpha. Checks the metadata given for a published dataset against a short list of "
            "FAIR-related presence checks and recommends what to retrofit; with a model "
            "configured, the recommendations are tailored to the record. Not a FAIRness "
            "evaluation; retrieves nothing and changes no record."
        ),
        action_class="advise",
        accepts=(ClassSchema.of(PublishedRecord),),
        grounding_mode=GroundingMode.INPUT_ONLY,
        payload=ClassSchema.of(FairnessReport),
        derivations={
            "checks.principle": Derived(Derivation.TEMPLATE),
            "checks.check": Derived(Derivation.TEMPLATE),
            "checks.met": Derived(Derivation.LEXICAL),
            "checks.recommendation": Derived(
                Derivation.MODEL, recorded_in="recommendation_derivation"
            ),
            "limitations": Derived(Derivation.TEMPLATE),
        },
        serves=("post.fairness", "post.retrofit"),
    )

    def __init__(self, writer: Writer | None = None, rules: list[Rule] | None = None) -> None:
        self.writer = writer or TemplateWriter()
        self.rules = rules if rules is not None else load_checks()

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        record = request.input
        assert isinstance(record, PublishedRecord)  # the conductor checked spec.accepts
        if not record.identifier and not record.title:
            return abstain(
                ReasonCode.INSUFFICIENT_INPUT, "Give the published dataset's identifier or title."
            )

        met = {rule.check: meets(rule, record) for rule in self.rules}
        unmet = [
            Unmet(rule.principle, rule.check, rule.recommendation)
            for rule in self.rules
            if not met[rule.check]
        ]
        writing = self.writer.write(record, unmet, ctx)
        written = dict(zip((u.check for u in unmet), writing.recommendations, strict=True))
        checks = []
        for rule in self.rules:
            got = written.get(rule.check)
            checks.append(
                FairCheck(
                    principle=rule.principle,
                    check=rule.check,
                    met=met[rule.check],
                    recommendation=got.text if got else None,
                    recommendation_derivation=got.derivation if got else None,
                )
            )
        by_model = any(r.derivation == Derivation.MODEL for r in writing.recommendations)
        limitations = [*LIMITATIONS, MODEL_LIMITATION] if by_model else list(LIMITATIONS)

        ref = input_ref(ctx)
        calls = writing.calls
        return AgentResult(
            outcome=Outcome(
                status=OutcomeStatus.SUCCEEDED,
                statement=(
                    f"The metadata given meet {len(checks) - len(unmet)} of {len(checks)} "
                    f"presence checks, with {_count(len(unmet), 'recommendation')} to retrofit. "
                    f"{_how_written(writing)} This is not a FAIRness evaluation."
                ),
            ),
            payload=FairnessReport(
                checks=checks,
                limitations=limitations,
                grounded_on=[ref],
            ),
            evidence=[input_evidence(ctx)],
            model_id=writing.model_id,
            input_tokens=writing.usage.input_tokens,
            output_tokens=writing.usage.output_tokens,
            model_calls=calls.calls if calls is not None else (),
            prompts=calls.prompts if calls is not None else {},
        )


def _how_written(writing: Writing) -> str:
    """What the statement says about the writer: whether a model wrote the recommendations, and
    what was not used."""
    if writing.model_id is None:
        return "No model is configured, so each recommendation is the rule table's own."
    if writing.unused:
        return (
            f"Each recommendation is the rule table's own, because {writing.unused} "
            f"({writing.model_id})."
        )
    by_model = sum(r.derivation == Derivation.MODEL for r in writing.recommendations)
    said = (
        f"A model ({writing.model_id}) tailored {by_model} of "
        f"{_count(len(writing.recommendations), 'recommendation')} to the record"
    )
    if writing.dropped:
        said += (
            f"; {_count(len(writing.dropped), 'item')} it returned "
            f"{'was' if len(writing.dropped) == 1 else 'were'} not used ("
            + "; ".join(writing.dropped)
            + ")"
        )
    return said + ". Review each before acting on it."


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def build() -> FairAssessor:
    """The template assessor. `factory.build` reads the agent's settings."""
    return FairAssessor()
