"""Results a scripted agent can return, and the sources they are grounded on."""

from __future__ import annotations

from dd_harness.testing.classes import ProbeCheck, ProbeReview
from dd_harness.testing.doubles import Retrieve
from dd_sdk.agent import AgentResult, RunContext
from dd_sdk.contract.models import (
    Derivation,
    EvidenceItem,
    GroundingRef,
    InvocationRequest,
    Outcome,
    OutcomeStatus,
    Reply,
)
from dd_sdk.delegate import Delegated, HarnessDelegate
from dd_sdk.evidence import HASH_ALGORITHM, INPUT_CANONICALISATION


def input_ref(ctx: RunContext) -> GroundingRef:
    return GroundingRef(source_id=ctx.input_ref, content_hash=ctx.input_hash)


def input_evidence(ctx: RunContext) -> EvidenceItem:
    return EvidenceItem(
        source_id=ctx.input_ref,
        hash_algorithm=HASH_ALGORITHM,
        canonicalisation=INPUT_CANONICALISATION,
        content_hash=ctx.input_hash,
    )


def review_of_input(request: InvocationRequest, ctx: RunContext) -> AgentResult:
    """A succeeded ProbeReview grounded on the input, as an input_only/none agent should."""
    return AgentResult(
        outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement="Reviewed."),
        payload=ProbeReview(score=1.0, grounded_on=[input_ref(ctx)]),
        evidence=[input_evidence(ctx)],
    )


def fact_check_over(*sources: Retrieve) -> AgentResult:
    """A succeeded ProbeCheck grounded on exactly the given sources."""
    return AgentResult(
        outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement="Checked."),
        payload=ProbeCheck(
            rationale="Scripted.",
            rationale_derivation=Derivation.TEMPLATE,
            grounded_on=[s.ref() for s in sources],
        ),
        evidence=[s.evidence() for s in sources],
    )


def grant_token(ctx: RunContext) -> str:
    """The grant token behind a delegation agent's `delegate`, for a test that presents it to
    the conductor directly instead of through `delegate`."""
    assert isinstance(ctx.delegate, HarnessDelegate), "the agent was not issued a grant"
    return ctx.delegate.grant.token


def reply_over(ctx: RunContext, *delegated: Delegated) -> AgentResult:
    """A succeeded Reply grounded on the input and the given child envelopes."""
    text = "; ".join(f"{d.envelope.agent_id}: {d.envelope.outcome.statement}" for d in delegated)
    return AgentResult(
        outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement="Relayed."),
        payload=Reply(
            reply_text=text or "Nothing delegated.",
            reply_derivation=Derivation.TEMPLATE,
            grounded_on=[input_ref(ctx), *(d.ref for d in delegated)],
        ),
        evidence=[input_evidence(ctx), *(d.evidence for d in delegated)],
    )


SOURCE_A = Retrieve("src:a", {"source_id": "src:a", "text": "Alpha."})
SOURCE_B = Retrieve("src:b", {"source_id": "src:b", "text": "Beta."})
