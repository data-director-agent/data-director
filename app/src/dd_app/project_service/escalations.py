"""A project's escalations to a data steward, and a steward's queue (docs/specs/stewardship.md,
invariants 4, 5 and 11; #373).

The harness routes and records (`dd_harness.escalation_api`); this area hands it the deployment's
profile and the run store, so that a run an escalation names is checked against what was
recorded, never against what the request says of it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from dd_app.project_service._area import Area
from dd_harness import escalation_api
from dd_harness.escalation_api import Confirmed, Requested
from dd_harness.policy import Profile
from dd_sdk.contract.models import Principal


class Escalations(Area):
    @property
    def _profile(self) -> Profile:
        return self.governance.conductor.profile

    def _envelope(self, invocation_id: str) -> Mapping[str, Any] | None:
        return self.governance.conductor.store.get(invocation_id)

    def of_project(self, project_id: str) -> dict[str, Any]:
        """The project's escalations, the teams it may send to, and where one would go."""
        return escalation_api.for_project(self._store, self._profile, project_id)

    def open(
        self, project_id: str, confirmed: Confirmed, *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any]:
        """Open the escalation a member confirmed; returns the project's escalations."""
        escalation_api.open_escalation(
            self._store,
            self._profile,
            project_id,
            confirmed,
            self._envelope,
            acted_for=acted_for,
            caused_by=caused_by,
        )
        return self.of_project(project_id)

    def move(
        self,
        project_id: str,
        requested: Requested,
        *,
        as_steward: bool,
        acted_for: Principal,
        caused_by: str,
    ) -> dict[str, Any]:
        """Make a move on an escalation; returns the escalation as it then stands."""
        return escalation_api.move(
            self._store,
            self._profile,
            project_id,
            requested,
            as_steward=as_steward,
            acted_for=acted_for,
            caused_by=caused_by,
        )

    def choose_support_team(
        self, project_id: str, team_id: str, *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any]:
        """Record the project's support team; returns the project's escalations."""
        escalation_api.choose_support_team(
            self._store,
            self._profile,
            project_id,
            team_id,
            acted_for=acted_for,
            caused_by=caused_by,
        )
        return self.of_project(project_id)

    def queue(self, steward: Principal, states: Sequence[str]) -> list[dict[str, Any]]:
        """The escalations routed to the steward's teams; none for someone in no team."""
        if self.governance.projects is None:
            return []
        return escalation_api.queue(self._store, self._profile, steward, states or None)
