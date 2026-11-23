"""A project's escalations to a data steward, and a steward's queue (docs/specs/stewardship.md,
invariants 4, 5 and 11; #373).

The harness routes and records (`dd_harness.escalation_api`); this area hands it the deployment's
profile and the run store, so that a run an escalation names is checked against what was
recorded, never against what the request says of it.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from dd_app.project_service._area import Area
from dd_harness import escalation_api, notifications
from dd_harness.escalation_api import Confirmed, Requested
from dd_harness.escalation_targets import NamesOf
from dd_sdk.contract.models import Principal, now

# How far back a person's notices go (`notices`): what the shell shows, not what is kept.
NOTICE_WINDOW = timedelta(days=30)


class Escalations(Area):
    def of_project(
        self, project_id: str, reader: Principal, names: NamesOf | None = None
    ) -> dict[str, Any]:
        """The project's escalations, each with the moves `reader` may make, the teams it may send
        to, and where one would go. `names` names the colleagues a steward may reassign to."""
        return escalation_api.for_project(self._store, self._profile, project_id, reader, names)

    def open(
        self, project_id: str, confirmed: Confirmed, *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any]:
        """Open the escalation a member confirmed, and tell its team; returns the project's
        escalations."""
        opened = escalation_api.open_escalation(
            self._store,
            self._profile,
            project_id,
            confirmed,
            self._envelope,
            acted_for=acted_for,
            caused_by=caused_by,
        )
        self._tell(project_id, opened)
        return self.of_project(project_id, acted_for)

    def _tell(self, project_id: str, escalation: dict[str, Any]) -> None:
        escalation_api.tell_team(
            self.governance.notifier, self._store, self._profile, project_id, escalation
        )

    def move(
        self,
        project_id: str,
        requested: Requested,
        *,
        acted_for: Principal,
        caused_by: str,
        names: NamesOf | None = None,
    ) -> dict[str, Any]:
        """Make a move on an escalation, and tell its team of a researcher's move, or the team an
        escalation is transferred to; returns the escalation as it then stands."""
        moved = escalation_api.move(
            self._store,
            self._profile,
            project_id,
            requested,
            acted_for=acted_for,
            caused_by=caused_by,
            names=names,
        )
        self._tell(project_id, moved)
        return moved

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
        return self.of_project(project_id, acted_for)

    def queue(
        self, steward: Principal, states: Sequence[str], names: NamesOf | None = None
    ) -> list[dict[str, Any]]:
        """The escalations routed to the steward's teams; none for someone in no team."""
        if self.governance.projects is None:
            return []
        return escalation_api.queue(self._store, self._profile, steward, states or None, names)

    def notices(self, person: Principal) -> list[dict[str, Any]]:
        """What data stewards have done in `person`'s projects lately, the newest first."""
        if self.governance.projects is None:
            return []
        return notifications.for_person(
            self._store, self._profile, person, since=now() - NOTICE_WINDOW
        )
