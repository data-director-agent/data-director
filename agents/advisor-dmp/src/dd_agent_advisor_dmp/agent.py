"""advisor.dmp: the Data Management Plan Checker persona (docs/specs/agents.md). An alpha.

Serves `governance.dmp` (R8). It compares the outputs a data management plan committed to share
with the outputs the researcher now plans to share, and lists every difference for a person to
review. It never enforces the plan: a reviewed decision not to share is a valid outcome.

Rules first (the deterministic shell): outputs are matched by name, case ignored, and repository,
access and licence are compared as text where both sides give them. What the rules leave over
goes to a matcher (`match.py`). With a model configured (`DD_DMP_MATCHER`, `factory.py`), the
model may pair a committed output with a planned one of another name, which merges the `missing`
and `unplanned` flags into one `renamed` flag, still for review; and it may judge two values of an
aspect to name the same thing, which moves that flag to the payload's `reconciled` list, shown
with its reason. It never removes a flag from what the person sees. Each discrepancy records how
it was found in `discrepancy_derivation`: `lexical` by rule, `model` for a pairing.

In a project it is also given the documents the researcher attached and the facts people decided
(`GivenProjectDocuments`, `GivenProjectDecisions`). The commitments a person confirmed
(`sharing_commitment` facts) are compared with the planned outputs as typed ones are. Where none
is confirmed or typed but a plan is attached, a model reads the plan (`read_plan.py`) and the
checker proposes each commitment it finds, with the quoted passage, as a project fact for the
researcher to confirm or correct; it compares nothing until they have (#962). It reads only its
input, so its grounding mode is `input_only` and it cites only its input. Reading a
machine-actionable plan (the RDA DMP Common Standard, #284) is TODO(#701).
"""

from __future__ import annotations

from dd_agent_advisor_dmp.classes import (
    Discrepancy,
    DmpCommitments,
    DmpDiscrepancies,
    Reconciliation,
    SharingCommitment,
)
from dd_agent_advisor_dmp.match import (
    Matcher,
    Matches,
    TemplateMatcher,
    differences_between,
    key,
    model_use,
    residue_of,
)
from dd_agent_advisor_dmp.read_plan import PlanReader, Reading, TemplateReader, confirmed
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

LIMITATIONS = (
    "It reads a plan the researcher attached only to propose its commitments, which count once "
    "the researcher confirms them; it does not read a machine-actionable plan by its identifier "
    "yet (#701).",
    "Without a matcher model (DD_DMP_MATCHER=template), it matches outputs by exact name, case "
    "ignored, so an output renamed since the plan is reported as both missing and unplanned, and "
    "it compares repository, access and licence as text, so two names for the same thing differ.",
    "A model's pairing or reconciliation is a reading of names, not a check of the plan: review "
    "each one.",
    "It does not check timing, embargoes, costs, metadata standards or any other commitment.",
    "Its matcher has no evaluation set yet, so how often it misses a renamed output or a "
    "difference of substance is not measured.",
)
MISSING = (
    "The plan committed to share '{output}', but it is not among the planned outputs. A person "
    "should review this: a reviewed decision not to share is a valid outcome."
)
UNPLANNED = (
    "'{output}' is planned for sharing but the plan did not commit to it. A person should review "
    "whether the plan needs updating."
)
DIFFERS = (
    "For '{output}', the plan committed to {aspect} '{committed}' but '{planned}' is planned. "
    "A person should review this difference."
)
RENAMED = (
    "The plan committed to share '{committed}', and '{planned}' is planned; a model read these as "
    "the same output under another name ({reason}). A person should review whether they are, and "
    "whether the plan needs updating."
)


class DmpChecker:
    spec = AgentSpec(
        agent_id="advisor.dmp",
        version="0.2.0a1",
        title="Data Management Plan Checker",
        icon="📋",
        description=(
            "Alpha. Compares what a data management plan committed to share with what is planned "
            "at publication, and lists each difference in output, repository, access or licence "
            "for a person to review. With a model, it reads renamed outputs and two names for one "
            "thing among what its rules leave over. Never enforces the plan."
        ),
        action_class="advise",
        accepts=(ClassSchema.of(DmpCommitments),),
        grounding_mode=GroundingMode.INPUT_ONLY,
        payload=ClassSchema.of(DmpDiscrepancies),
        derivations={
            "discrepancies.aspect": Derived(
                Derivation.LEXICAL, recorded_in="discrepancy_derivation"
            ),
            "discrepancies.reason": Derived(Derivation.MODEL),
            "discrepancies.message": Derived(Derivation.TEMPLATE),
            "reconciled.reason": Derived(Derivation.MODEL),
            "dropped": Derived(Derivation.TEMPLATE),
            "limitations": Derived(Derivation.TEMPLATE),
        },
        serves=("governance.dmp",),
        reads_attached=(
            "to find a data management plan's commitments to share your data, which you then "
            "confirm or correct"
        ),
    )

    def __init__(self, matcher: Matcher | None = None, reader: PlanReader | None = None) -> None:
        self.matcher: Matcher = TemplateMatcher() if matcher is None else matcher
        self.reader: PlanReader = TemplateReader() if reader is None else reader

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        commitments = request.input
        assert isinstance(commitments, DmpCommitments)  # the conductor checked spec.accepts
        committed = [*commitments.committed_outputs, *confirmed(commitments)]
        if not committed and commitments.project_documents:
            return self._read(commitments, ctx)
        if not committed:
            return abstain(
                ReasonCode.INSUFFICIENT_INPUT,
                "Attach the data management plan, or give the outputs it committed to share.",
            )

        residue = residue_of(committed, commitments.planned_outputs)
        matches = self.matcher.match(residue, ctx)
        discrepancies, reconciled = compare(committed, commitments.planned_outputs, matches)
        count = f"{len(discrepancies)} difference{'' if len(discrepancies) == 1 else 's'}"
        statement = (
            f"{count} between the plan's commitments and the planned sharing, each for a person "
            f"to review. {_how_matched(matches, reconciled)}"
        )
        ref = input_ref(ctx)
        model_id = matches.model_id if matches.called else None
        return AgentResult(
            outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement=statement),
            payload=DmpDiscrepancies(
                discrepancies=discrepancies,
                reconciled=reconciled,
                dropped=list(matches.dropped),
                limitations=list(LIMITATIONS),
                grounded_on=[ref],
            ),
            evidence=[input_evidence(ctx)],
            **model_use(model_id, matches.usage, matches.calls),
        )

    def _read(self, commitments: DmpCommitments, ctx: RunContext) -> AgentResult:
        """A plan's commitments, proposed as facts for the researcher to confirm; nothing is
        compared until they have."""
        reading = self.reader.read(commitments.project_documents, ctx)
        if reading.model_id is None:
            return abstain(
                ReasonCode.CAPABILITY_NOT_IMPLEMENTED,
                "A plan is attached, but reading one needs a model, and none is configured "
                "(DD_DMP_MATCHER=template). Give the outputs it committed to share instead.",
            )
        return AgentResult(
            outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement=_how_read(reading)),
            payload=DmpDiscrepancies(
                dropped=list(reading.dropped),
                limitations=list(LIMITATIONS),
                proposed_facts=list(reading.proposals),
                grounded_on=[input_ref(ctx)],
            ),
            evidence=[input_evidence(ctx)],
            **model_use(reading.model_id, reading.usage, reading.calls),
        )


def _how_read(reading: Reading) -> str:
    """What the statement says about reading a plan: what was proposed, and what to do next."""
    read = ", ".join(reading.read) or "the attached documents"
    if reading.unused:
        return (
            f"It could not read {read}, because {reading.unused} ({reading.model_id}). Try again, "
            "or give the outputs the plan committed to share."
        )
    if reading.proposals:
        said = (
            f"A model ({reading.model_id}) read {read} and found "
            f"{_count(len(reading.proposals), 'sharing commitment')}, each with the passage it "
            "rests on. Confirm, correct or reject each on the project page; the check compares "
            "only the commitments you confirm, and runs once you have."
        )
    elif reading.vague:
        said = (
            f"A model ({reading.model_id}) read {read}: it speaks of sharing only in terms too "
            "general to name an output. Give the outputs it committed to share, if any."
        )
    else:
        said = (
            f"A model ({reading.model_id}) read {read} and found no commitment to share an "
            "output. That is a valid result; give the outputs if you know of any."
        )
    if reading.cut:
        said += f" Only the start of {', '.join(reading.cut)} was read, for room."
    if reading.dropped:
        said += f" {_count(len(reading.dropped), 'reading')} was not used: " + "; ".join(
            reading.dropped
        )
    return said


def compare(
    committed: list[SharingCommitment],
    planned: list[SharingCommitment],
    matches: Matches | None = None,
) -> tuple[list[Discrepancy], list[Reconciliation]]:
    """Every difference between committed and planned outputs, in committed order and then the
    unplanned; and the differences a matcher reconciled. With no matches, the rules' result."""
    matches = Matches() if matches is None else matches
    planned_by_name = {key(p.output): p for p in planned}
    committed_names = {key(c.output) for c in committed}
    paired = {key(m.committed.output): m for m in matches.pairings}
    paired_planned = {key(m.planned.output) for m in matches.pairings}
    found: list[Discrepancy] = []
    reconciled: list[Reconciliation] = []
    for c in committed:
        p = planned_by_name.get(key(c.output))
        if p is None and (pairing := paired.get(key(c.output))) is not None:
            p = pairing.planned
            found.append(
                Discrepancy(
                    output=c.output,
                    aspect="renamed",
                    committed=c.output,
                    planned=p.output,
                    message=RENAMED.format(
                        committed=c.output, planned=p.output, reason=pairing.reason
                    ),
                    discrepancy_derivation=Derivation.MODEL,
                    reason=pairing.reason,
                )
            )
        if p is None:
            found.append(
                Discrepancy(
                    output=c.output,
                    aspect="missing",
                    message=MISSING.format(output=c.output),
                    discrepancy_derivation=Derivation.LEXICAL,
                )
            )
            continue
        for d in differences_between(c, p):
            same = matches.equivalent(d.aspect, d.committed, d.planned)
            if same is not None:
                reconciled.append(
                    Reconciliation(
                        output=d.output,
                        aspect=d.aspect,
                        committed=d.committed,
                        planned=d.planned,
                        reason=same.reason,
                    )
                )
                continue
            found.append(
                Discrepancy(
                    output=d.output,
                    aspect=d.aspect,
                    committed=d.committed,
                    planned=d.planned,
                    message=DIFFERS.format(
                        output=d.output, aspect=d.aspect, committed=d.committed, planned=d.planned
                    ),
                    discrepancy_derivation=Derivation.LEXICAL,
                )
            )
    for p in planned:
        if key(p.output) not in committed_names and key(p.output) not in paired_planned:
            found.append(
                Discrepancy(
                    output=p.output,
                    aspect="unplanned",
                    message=UNPLANNED.format(output=p.output),
                    discrepancy_derivation=Derivation.LEXICAL,
                )
            )
    return found, reconciled


def _how_matched(matches: Matches, reconciled: list[Reconciliation]) -> str:
    """What the statement says about the matcher: whether a model read the residue, and what it
    changed or was not used."""
    if matches.model_id is None:
        return (
            "They were found by rule: no matcher model is configured, so outputs are matched by "
            "exact name and values compared as text."
        )
    if not matches.called:
        return (
            f"They were found by rule; the rules left nothing for the matcher model "
            f"({matches.model_id}) to read."
        )
    if matches.unused:
        return f"They were found by rule, because {matches.unused} ({matches.model_id})."
    said = (
        f"A model ({matches.model_id}) read what the rules left over and paired "
        f"{_count(len(matches.pairings), 'renamed output')}, each still flagged for review, and "
        f"reconciled {_count(len(reconciled), 'difference')} as two names for one thing, listed "
        "with its reason"
    )
    if matches.dropped:
        said += (
            f"; {_count(len(matches.dropped), 'proposal')} it made "
            f"{'was' if len(matches.dropped) == 1 else 'were'} not used ("
            + "; ".join(matches.dropped)
            + ")"
        )
    return said + ". Check its pairings and reconciliations as you review."


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def build() -> DmpChecker:
    """The template checker. `factory.build` reads the agent's settings."""
    return DmpChecker()
