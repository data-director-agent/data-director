"""The abstaining stub. Returns `abstained(capability_not_implemented)` unconditionally.

It exists so the shell, the outcome vocabulary and the conformance report are exercised
against something other than a successful recommendation, and so the renderer does not grow
features only one agent needs.
"""

from __future__ import annotations

from workbench.agents.base import AgentResult, RunContext
from workbench.contract.models import InvocationRequest, Outcome, OutcomeStatus, ReasonCode


class AbstainingStub:
    agent_id = "stub.abstain"
    version = "0.1.0"
    requirement_ids: tuple[str, ...] = ("DD-OUTCOME",)
    action_class = "advise"

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
