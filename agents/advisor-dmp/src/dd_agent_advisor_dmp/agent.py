"""advisor.dmp: the Data Management Plan Checker persona (ADR-0033). A mock.

Serves `governance.dmp` (R8). It compares the outputs a data management plan committed to share
with the outputs the researcher now plans to share, and lists every difference for a person to
review. It never enforces the plan: a reviewed decision not to share is a valid outcome.

The mock matches outputs by name, case ignored, and compares repository, access and licence where
both sides give them. It reads no plan itself, consults no source and calls no model, so its
grounding mode is `none` and it cites only its input. The real checker reads machine-actionable
plans (the RDA DMP Common Standard, #284) and is TODO(#356).
"""

from __future__ import annotations

from datetime import UTC, datetime

from dd_agent_advisor_dmp.classes import (
    Discrepancy,
    DmpCommitments,
    DmpDiscrepancies,
    SharingCommitment,
)
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

# The aspects of a commitment compared when an output is both committed and planned, in order.
COMPARED = ("repository", "access", "licence")

LIMITATIONS = (
    "This is a mock: it compares the commitments it is given and reads no data management plan.",
    "It matches outputs by exact name, case ignored, so an output renamed since the plan is "
    "reported as both missing and unplanned.",
    "It compares repository, access and licence as text, so two names for the same thing differ.",
    "It does not check timing, embargoes, costs, metadata standards or any other commitment.",
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


def _key(text: str) -> str:
    return text.strip().casefold()


class DmpChecker:
    spec = AgentSpec(
        agent_id="advisor.dmp",
        version="0.1.0a1",
        title="Data Management Plan Checker",
        description=(
            "Mock. Compares what a data management plan committed to share with what is planned "
            "at publication, and lists each difference in output, repository, access or licence "
            "for a person to review. Never enforces the plan."
        ),
        action_class="advise",
        accepts=(ClassSchema.of(DmpCommitments),),
        grounding_mode=GroundingMode.NONE,
        payload=ClassSchema.of(DmpDiscrepancies),
        derivations={
            "discrepancies.aspect": Derived(Derivation.LEXICAL),
            "discrepancies.message": Derived(Derivation.TEMPLATE),
            "limitations": Derived(Derivation.TEMPLATE),
        },
        serves=("governance.dmp",),
    )

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        commitments = request.input
        assert isinstance(commitments, DmpCommitments)  # the conductor checked spec.accepts
        if not commitments.committed_outputs:
            return AgentResult(
                outcome=Outcome(
                    status=OutcomeStatus.ABSTAINED,
                    reason_code=ReasonCode.INSUFFICIENT_INPUT,
                    statement="Give the outputs the data management plan committed to share.",
                )
            )

        discrepancies = compare(commitments.committed_outputs, commitments.planned_outputs)
        count = f"{len(discrepancies)} difference{'' if len(discrepancies) == 1 else 's'}"
        ref = GroundingRef(source_id=ctx.input_ref, content_hash=ctx.input_hash)
        return AgentResult(
            outcome=Outcome(
                status=OutcomeStatus.SUCCEEDED,
                statement=(
                    f"Mock: {count} between the plan's commitments and "
                    "the planned sharing, each for a person to review."
                ),
            ),
            payload=DmpDiscrepancies(
                discrepancies=discrepancies,
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


def compare(
    committed: list[SharingCommitment], planned: list[SharingCommitment]
) -> list[Discrepancy]:
    """Every difference between committed and planned outputs: committed order, then unplanned."""
    planned_by_name = {_key(p.output): p for p in planned}
    committed_names = {_key(c.output) for c in committed}
    found = []
    for c in committed:
        p = planned_by_name.get(_key(c.output))
        if p is None:
            found.append(
                Discrepancy(
                    output=c.output, aspect="missing", message=MISSING.format(output=c.output)
                )
            )
            continue
        for aspect in COMPARED:
            was, now = getattr(c, aspect), getattr(p, aspect)
            if was is not None and now is not None and _key(was) != _key(now):
                found.append(
                    Discrepancy(
                        output=c.output,
                        aspect=aspect,
                        committed=was,
                        planned=now,
                        message=DIFFERS.format(
                            output=c.output, aspect=aspect, committed=was, planned=now
                        ),
                    )
                )
    for p in planned:
        if _key(p.output) not in committed_names:
            found.append(
                Discrepancy(
                    output=p.output, aspect="unplanned", message=UNPLANNED.format(output=p.output)
                )
            )
    return found


def build() -> DmpChecker:
    return DmpChecker()


def main() -> int:
    """The `dd-advisor-dmp` console script: serve over A2A with `dd_sdk.serve`."""
    return serve.main(build)
