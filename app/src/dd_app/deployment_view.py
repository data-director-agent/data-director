"""What the deployment is: its agents for the capabilities panel, the policy gate's rules, and
what an operator's check reads (`GET /api/agents`, `GET /api/policy`, `GET /api/about`)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dd_app.governance import Governance
from dd_app.policy_view import policy_view
from dd_app.principals import principal_summary
from dd_sdk.contract.models import Principal


@dataclass(frozen=True)
class DeploymentView:
    governance: Governance

    def agents(self, acting_for: Principal) -> dict[str, Any]:
        """What the shell's capabilities panel is drawn from (`GET /api/agents`).

        Each registered agent's manifest, as its card declares it, beside what this deployment's
        profile assigns it: the action class, and whether that class needs approval
        (docs/specs/policy-and-identity.md). An agent the profile does not list is shown with
        `assigned_action_class: null`; the gate refuses it. The profile and `acting_for`, the
        caller's principal, are named so the page can say whose rules apply and whom runs act for,
        and the profile's `orchestrator` so the home page converses with that agent and no other
        (docs/specs/app.md).
        """
        profile, registry = self.governance.conductor.profile, self.governance.conductor.registry
        registry.refresh()  # an agent started since the app was is found now
        listing = registry.listing()
        for entry in listing["agents"]:
            assigned = profile.agents.get(entry["agent_id"])
            entry["assigned_action_class"] = assigned
            entry["requires_approval"] = (
                assigned is not None and assigned in profile.actions_requiring_approval
            )
        return {
            **listing,
            "profile": {
                "ref": profile.ref,
                "digest": profile.digest,
                "orchestrator": profile.orchestrator,
                "attached_documents": profile.attached_documents,
            },
            "acting_for": principal_summary(acting_for),
        }

    def policy(self) -> dict[str, Any]:
        """The rules the policy gate holds every run to (`GET /api/policy`), for the policy page."""
        return policy_view(self.governance.conductor)

    def deployment(self) -> dict[str, Any]:
        """What this deployment runs, for an operator's check (`GET /api/about`, open to all).

        The profile the conductor holds runs to, and which configured agents it reaches. An agent
        is named by its entry in the agent configuration, never with its address or the reason it
        is missing: the answer is public, and a reason can carry an internal address.

        The answer is open to callers with no session, so it retries the missing agents at most
        once per interval (`AboutRefresh`), and otherwise answers from what the registry last
        saw (#726). A request that arrives while another is refreshing does not wait for it.
        """
        profile = self.governance.conductor.profile
        registry = self.governance.conductor.registry
        self.governance.about_refresh.run(registry.refresh)
        return {
            "profile": {
                "id": profile.profile_id,
                "version": profile.version,
                "digest": profile.digest,
                "orchestrator": profile.orchestrator,
            },
            "unavailable": sorted(registry.unavailable),
            "incompatible": sorted(registry.incompatible),
        }
