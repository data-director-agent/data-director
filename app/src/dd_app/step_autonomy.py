"""How far each Blueprint step is delegated here, for the policy page (`GET /api/policy`, #448).

Split from `Governance`, which is over the size limit and may not grow.
"""

from __future__ import annotations

from typing import Any

from dd_harness.conductor import Conductor
from dd_harness.refusals import DATA_STEWARD
from dd_sdk.process_flow import ENTRIES, plan


def step_autonomy(conductor: Conductor) -> list[dict[str, Any]]:
    """How far each Blueprint step is delegated here, for the policy page (#448).

    Worked out from facts the gate already holds runs to, not from a profile key of its own:
    a step out of scope, or one a person decides (C2), is never an agent's; a step no agent
    this profile enables serves is not offered; a step served by an agent whose class needs
    approval is referred to a data steward, as the gate refers its runs; any other step is
    delegated to the agents serving it, as the class the profile assigns them.
    TODO(#373): name the person or team each step is referred to, from the profile.
    """
    profile = conductor.profile
    conductor.registry.refresh()  # an agent started since the app was is found now
    manifest = [
        entry for entry in conductor.registry.manifest() if entry["agent_id"] in profile.agents
    ]
    steps = []
    for planned in plan(ENTRIES[0], manifest):
        step = planned.step
        classes = sorted({profile.agents[a] for a in planned.agent_ids})
        reason: str | None = None
        refers_to: str | None = None
        if step.out_of_scope:
            autonomy, reason = "not_offered", "out_of_scope"
        elif step.person_decides:
            autonomy = "never_delegated"
        elif not planned.agent_ids:
            # TODO(#362): the steps that act in a repository or an institutional system.
            autonomy, reason = "not_offered", "no_agent"
        elif any(c in profile.actions_requiring_approval for c in classes):
            autonomy, refers_to = "must_approve", DATA_STEWARD
        else:
            autonomy = "delegated"
        steps.append(
            {
                "step_id": step.id,
                "phase_number": planned.phase.number,
                "phase_name": planned.phase.name,
                "label": step.label,
                "autonomy": autonomy,
                "reason": reason,
                "agent_ids": list(planned.agent_ids),
                "action_classes": classes,
                "refers_to": refers_to,
            }
        )
    return steps
