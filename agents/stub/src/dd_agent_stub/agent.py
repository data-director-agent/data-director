"""The abstaining stub. Returns `abstained(capability_not_implemented)` unconditionally.

It exists so the viewer, the outcome vocabulary and the conformance report are exercised
against something other than a successful payload, and so the renderer does not grow features
only one agent needs. It accepts the core's `Message`, the one input class every agent can share
(ADR-0019), and declares grounding mode `none`: it retrieves nothing and calls no model.
"""

from __future__ import annotations

from dd_sdk import serve
from dd_sdk.agent import AgentResult, AgentSpec, RunContext
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
    GroundingMode,
    InvocationRequest,
    Message,
    Outcome,
    OutcomeStatus,
    ReasonCode,
)


class AbstainingStub:
    spec = AgentSpec(
        agent_id="stub.abstain",
        version="0.3.0",
        description="Abstains unconditionally; exercises the non-success path.",
        requirement_ids=("DD-OUTCOME",),
        action_class="advise",
        accepts=(ClassSchema.of(Message),),
        grounding_mode=GroundingMode.NONE,
        payload=None,
    )

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        return AgentResult(
            outcome=Outcome(
                status=OutcomeStatus.ABSTAINED,
                reason_code=ReasonCode.CAPABILITY_NOT_IMPLEMENTED,
                statement=(
                    "This agent is a stub and abstains unconditionally. No registry was searched "
                    "and no model was called."
                ),
            )
        )


def build() -> AbstainingStub:
    return AbstainingStub()


def main() -> int:
    """Console script: serve this agent over A2A (`dd_sdk.serve`)."""
    return serve.main(build)
