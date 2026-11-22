"""A data steward in a researcher's project (docs/specs/stewardship.md, invariants 2, 3 and 6 to 8;
#374).

The harness checks and records (`dd_harness.steward_api`); this area hands it the deployment's
profile and the run store, so that a referred run a steward decides is checked against what was
recorded, and reads back what stewards have done in the project for the researcher and the
steward alike.
"""

from __future__ import annotations

from typing import Any

from dd_app.project_service._area import Area
from dd_harness import steward_api
from dd_harness.projects import STEWARD_MESSAGE, STEWARD_VIEWED, UnknownProjectError
from dd_harness.projects.stewarding import gate_decisions, pause_of
from dd_harness.steward_storage import GateDecision, ProposedEdit
from dd_sdk.contract.models import DocumentVersionRef, Principal


class Stewarding(Area):
    def of_project(self, project_id: str) -> dict[str, Any]:
        """What stewards have done in the project: its pause, their decisions on referred runs,
        their notes to the researcher and who read it when."""
        events = self._store.events(project_id)
        return {
            "paused": pause_of(events),
            "gate_decisions": [
                {"invocation_id": invocation_id, **decided}
                for invocation_id, decided in gate_decisions(events).items()
            ],
            "messages": [
                {"note": e["note"], "by": e["acted_for"], "at": e["at"]}
                for e in events
                if e["event"] == STEWARD_MESSAGE
            ],
            "views": [
                {"by": e["acted_for"], "at": e["at"]}
                for e in events
                if e["event"] == STEWARD_VIEWED
            ],
        }

    def reaches(self, project_id: str, person: Principal) -> bool:
        """Whether `person` reaches the project at all, as a member or as its steward."""
        try:
            self.permitted_actions(project_id, person)
        except UnknownProjectError:
            return False
        return True

    def permitted_actions(self, project_id: str, person: Principal) -> dict[str, Any]:
        """What `person` may do in the project, as whom, and why the rest is refused."""
        return steward_api.permitted_actions(self._store, self._profile, project_id, person)

    def message(
        self, project_id: str, note: str, *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any]:
        steward_api.message(
            self._store, self._profile, project_id, note, acted_for=acted_for, caused_by=caused_by
        )
        return self.of_project(project_id)

    def pause(
        self, project_id: str, reason: str, *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any]:
        steward_api.pause(
            self._store, self._profile, project_id, reason, acted_for=acted_for, caused_by=caused_by
        )
        return self.of_project(project_id)

    def resume(
        self, project_id: str, reason: str, *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any]:
        steward_api.resume(
            self._store, self._profile, project_id, reason, acted_for=acted_for, caused_by=caused_by
        )
        return self.of_project(project_id)

    def decide_gate(
        self, project_id: str, decision: GateDecision, *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any]:
        steward_api.decide_gate(
            self._store,
            self._profile,
            project_id,
            decision,
            self._envelope,
            acted_for=acted_for,
            caused_by=caused_by,
        )
        return self.of_project(project_id)

    def propose_edit(
        self, project_id: str, edit: ProposedEdit, *, acted_for: Principal, caused_by: str
    ) -> DocumentVersionRef:
        return steward_api.propose_edit(
            self._store, self._profile, project_id, edit, acted_for=acted_for, caused_by=caused_by
        )
