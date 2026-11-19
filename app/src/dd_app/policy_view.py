"""The rules the policy gate holds every run to (`GET /api/policy`), for the policy page.

Split from `Governance`, which is over the size limit and may not grow.
"""

from __future__ import annotations

from typing import Any

from dd_app.step_autonomy import step_autonomy
from dd_harness.conductor import Conductor


def policy_view(conductor: Conductor) -> dict[str, Any]:
    """The profile as the conductor loaded it: its identifier, version, digest and description,
    the agent the conversation goes to, each agent it enables with the action class it assigns
    and whether that class needs approval, every class that needs approval, and how far each
    Blueprint step is delegated. The shell renders this and decides nothing from it
    (docs/specs/app.md).
    """
    profile = conductor.profile
    return {
        "profile": {
            "id": profile.profile_id,
            "version": profile.version,
            "ref": profile.ref,
            "digest": profile.digest,
            "description": profile.description,
            "orchestrator": profile.orchestrator,
        },
        "agents": [
            {
                "agent_id": agent_id,
                "action_class": action_class,
                "requires_approval": action_class in profile.actions_requiring_approval,
            }
            for agent_id, action_class in sorted(profile.agents.items())
        ],
        "actions_requiring_approval": sorted(profile.actions_requiring_approval),
        "steps": step_autonomy(conductor),
    }
