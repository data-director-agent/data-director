"""advisor.fairness: the FAIR Assessor persona (docs/specs/agents.md). A model-backed alpha.

Serves `post.fairness` (R12) and `post.retrofit` (R9). It checks the metadata of an already
published dataset, as the researcher gives it (`PublishedRecord`), against a short list of
FAIR-related presence checks, and recommends a retrofit for each check not met.

It also gives feedback on the project's metadata record while it is drafted
(`ProjectMetadataDraft`, #430, #432), at any point in the work and for no step of its own: the
conductor gives it the record's latest version and the version a person approved last
(`GivenProjectMetadataRecord`). The feedback puts what is met first, tallies the checks for each
of F, A, I and R, names the next steps most worth taking, and says which checks are newly met since
the approved version. A check the repository fills at deposit, such as the DOI, is not expected of
a draft and not counted (`after_deposit` in `checks.yaml`).

It is advisory and changes no record: the researcher decides what to change. It gives no score and
is not a FAIRness evaluation (R4). Whether each check is met is decided by the rule table, never by
a model (`rules.py`); so are the tallies and next steps (`feedback.py`). The recommendation for
each check to act on comes from a writer (`write.py`): text a model writes for this record by
default, or, with `DD_FAIRNESS_WRITER=template` (`factory.py`), the table's own text, recorded in
`recommendation_derivation`. It retrieves nothing and resolves no identifier, so its grounding
mode is `input_only` and it cites only its input. Resolving the record and running a community
FAIRness tool is TODO(#704); discovering related datasets is TODO(#954).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from dd_agent_advisor_fairness import datacite
from dd_agent_advisor_fairness.classes import (
    FairCheck,
    FairnessReport,
    ProjectMetadataDraft,
    PublishedRecord,
)
from dd_agent_advisor_fairness.feedback import Verdict, judge, next_steps, summary, tallies
from dd_agent_advisor_fairness.rules import Rule, load_checks
from dd_agent_advisor_fairness.write import Recommendation, TemplateWriter, Unmet, Writer, Writing
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
    DocumentVersionRef,
    GroundingMode,
    InvocationRequest,
    Outcome,
    OutcomeStatus,
    ReasonCode,
)

NOT_AN_EVALUATION = (
    "This is not a FAIRness evaluation: it checks only whether the metadata given here are present "
    "and in an expected form, against a short list."
)
LIMITATIONS = (
    NOT_AN_EVALUATION,
    "Nothing was retrieved: the identifier was not resolved and the repository's record, files and "
    "landing page were not read.",
    "It does not yet discover related datasets or outputs.",
    "Its recommendations change no record. Submit any change to the repository yourself.",
)
DRAFT_LIMITATIONS = (
    NOT_AN_EVALUATION.replace("the metadata given here", "the draft's metadata"),
    "Its feedback changes no record. Edit or approve the draft yourself.",
)
AFTER_DEPOSIT_LIMITATION = (
    "Checks of what the repository supplies at deposit, such as the DOI and how the data are "
    "accessed, are left until then and not counted."
)
MODEL_LIMITATION = (
    "Recommendations marked as written by a model were tailored to the metadata given here and "
    "were not checked against the published record. Review each before acting on it."
)
NO_DRAFT = (
    "The project holds no metadata record yet. Ask the Metadata Librarian to draft one, then ask "
    "again for feedback on it."
)


@dataclass(frozen=True)
class Assessment:
    """What a run assesses: the record, the verdicts on it, and for a draft, the versions."""

    record: PublishedRecord
    verdicts: list[Verdict]
    limitations: tuple[str, ...]
    assessed_version: DocumentVersionRef | None = None
    compared_with: DocumentVersionRef | None = None


class FairAssessor:
    spec = AgentSpec(
        agent_id="advisor.fairness",
        version="0.3.0a1",
        title="FAIR Assessor",
        icon="🌱",
        description=(
            "Alpha. Checks a dataset's metadata against a short list of FAIR-related presence "
            "checks: a published record the researcher gives, or, at any time, the project's draft "
            "metadata record. It says what is already met first, tallies the checks for each of "
            "F, A, I and R, names the next steps most worth taking and, for a draft, what is newly "
            "met since the version approved. With a model configured, the recommendations are "
            "tailored to the record. Not a FAIRness evaluation; retrieves nothing and changes no "
            "record."
        ),
        action_class="advise",
        accepts=(ClassSchema.of(PublishedRecord), ClassSchema.of(ProjectMetadataDraft)),
        grounding_mode=GroundingMode.INPUT_ONLY,
        payload=ClassSchema.of(FairnessReport),
        derivations={
            "checks.principle": Derived(Derivation.TEMPLATE),
            "checks.check": Derived(Derivation.TEMPLATE),
            "checks.met": Derived(Derivation.LEXICAL),
            "checks.after_deposit": Derived(Derivation.LEXICAL),
            "checks.newly_met": Derived(Derivation.LEXICAL),
            "checks.recommendation": Derived(
                Derivation.MODEL, recorded_in="recommendation_derivation"
            ),
            "principle_tallies": Derived(Derivation.LEXICAL),
            "next_steps": Derived(Derivation.LEXICAL),
            "limitations": Derived(Derivation.TEMPLATE),
        },
        serves=("post.fairness", "post.retrofit"),
    )

    def __init__(self, writer: Writer | None = None, rules: list[Rule] | None = None) -> None:
        self.writer = writer or TemplateWriter()
        self.rules = rules if rules is not None else load_checks()

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        given = request.input
        if isinstance(given, ProjectMetadataDraft):
            assessed = self._draft(given)
        else:
            assert isinstance(given, PublishedRecord)  # the conductor checked spec.accepts
            assessed = self._published(given)
        if isinstance(assessed, AgentResult):
            return assessed
        return self._report(assessed, ctx, draft=isinstance(given, ProjectMetadataDraft))

    def _published(self, record: PublishedRecord) -> Assessment | AgentResult:
        if not record.identifier and not record.title:
            return abstain(
                ReasonCode.INSUFFICIENT_INPUT, "Give the published dataset's identifier or title."
            )
        return Assessment(record, judge(self.rules, record, draft=False), LIMITATIONS)

    def _draft(self, given: ProjectMetadataDraft) -> Assessment | AgentResult:
        draft = given.project_metadata_draft
        text = draft.document_text if draft is not None else given.draft_text
        if not text or not text.strip():
            return abstain(ReasonCode.INSUFFICIENT_INPUT, NO_DRAFT)
        try:
            record = PublishedRecord.model_validate(datacite.fields(text))
        except datacite.NotDataCiteError as exc:
            return abstain(
                ReasonCode.INSUFFICIENT_INPUT,
                f"The metadata record cannot be read as DataCite JSON: {exc}.",
            )
        approved, compared_with = self._approved(given)
        verdicts = judge(self.rules, record, draft=True, approved=approved)
        limitations: tuple[str, ...] = DRAFT_LIMITATIONS
        if any(v.after_deposit for v in verdicts):
            limitations = (*limitations, AFTER_DEPOSIT_LIMITATION)
        return Assessment(
            record,
            verdicts,
            limitations,
            assessed_version=draft.version_ref if draft is not None else None,
            compared_with=compared_with,
        )

    @staticmethod
    def _approved(
        given: ProjectMetadataDraft,
    ) -> tuple[PublishedRecord | None, DocumentVersionRef | None]:
        """The approved version to compare the draft with, read as a record, and its reference;
        neither when none was approved, it is the version assessed, or it cannot be read."""
        approved = given.project_metadata_approved
        draft = given.project_metadata_draft
        if approved is None or (draft is not None and draft.version_ref == approved.version_ref):
            return None, None
        try:
            fields = datacite.fields(approved.document_text)
        except datacite.NotDataCiteError:
            return None, None
        return PublishedRecord.model_validate(fields), approved.version_ref

    def _report(self, assessed: Assessment, ctx: RunContext, *, draft: bool) -> AgentResult:
        verdicts = assessed.verdicts
        to_act_on = [v for v in verdicts if v.to_act_on]
        writing = self.writer.write(
            assessed.record,
            [Unmet(v.rule.principle, v.rule.check, v.rule.recommendation) for v in to_act_on],
            ctx,
        )
        written = dict(zip((v.rule.check for v in to_act_on), writing.recommendations, strict=True))
        counted = tallies(verdicts)
        steps = next_steps(verdicts)
        by_model = any(r.derivation == Derivation.MODEL for r in writing.recommendations)
        limitations = [*assessed.limitations, *((MODEL_LIMITATION,) if by_model else ())]
        whose, verb = (
            ("Your draft metadata record", "meets") if draft else ("The metadata given", "meet")
        )
        calls = writing.calls
        return AgentResult(
            outcome=Outcome(
                status=OutcomeStatus.SUCCEEDED,
                statement=(
                    f"{summary(whose, verb, verdicts, counted, steps)} {_how_written(writing)} "
                    "This is not a FAIRness evaluation."
                ),
            ),
            payload=FairnessReport(
                checks=_checks(verdicts, written),
                principle_tallies=counted,
                next_steps=steps,
                assessed_version=assessed.assessed_version,
                compared_with=assessed.compared_with,
                limitations=limitations,
                grounded_on=[input_ref(ctx)],
            ),
            evidence=[input_evidence(ctx)],
            model_id=writing.model_id,
            input_tokens=writing.usage.input_tokens,
            output_tokens=writing.usage.output_tokens,
            model_calls=calls.calls if calls is not None else (),
            prompts=calls.prompts if calls is not None else {},
        )


def _checks(verdicts: Sequence[Verdict], written: dict[str, Recommendation]) -> list[FairCheck]:
    checks = []
    for verdict in verdicts:
        got = written.get(verdict.rule.check)
        checks.append(
            FairCheck(
                principle=verdict.rule.principle,
                check=verdict.rule.check,
                met=verdict.met,
                after_deposit=verdict.after_deposit or None,
                newly_met=verdict.newly_met,
                recommendation=got.text if got else None,
                recommendation_derivation=got.derivation if got else None,
            )
        )
    return checks


def _how_written(writing: Writing) -> str:
    """What the statement says about the writer: whether a model wrote the recommendations, and
    what was not used."""
    if not writing.recommendations:
        return "There is nothing to recommend."
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
