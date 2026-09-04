"""The abstaining stub. Returns `abstained(capability_not_implemented)` unconditionally.

It exists so the shell, the outcome vocabulary and the conformance report are exercised
against something other than a successful payload, and so the renderer does not grow features
only one agent needs. It accepts every input class and declares grounding mode `none`: it
retrieves nothing and calls no model.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from workbench.agents.base import AgentResult, AgentSpec, RunContext
from workbench.contract.models import (
    INPUT_TYPES,
    GroundingMode,
    InvocationRequest,
    Outcome,
    OutcomeStatus,
    ReasonCode,
)

if TYPE_CHECKING:
    from workbench.settings import Settings


class AbstainingStub:
    spec = AgentSpec(
        agent_id="stub.abstain",
        version="0.2.0",
        description="Abstains unconditionally; exercises the non-success path.",
        requirement_ids=("DD-OUTCOME",),
        action_class="advise",
        accepts=tuple(INPUT_TYPES.values()),
        grounding_mode=GroundingMode.NONE,
        payload_type=None,
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


def build(settings: Settings) -> AbstainingStub:
    return AbstainingStub()
