"""What the project holds of the researcher's files, and of the researcher."""

from __future__ import annotations

from typing import Any

from dd_app.project_service._area import Area
from dd_harness.storage import ProjectHoldings, ProjectResearchers
from dd_sdk.contract.models import Principal


class Materials(Area):
    def inventory(self, project_id: str) -> dict[str, Any] | None:
        store: ProjectHoldings = self._store
        return store.inventory(project_id)

    def add_inventory(
        self, project_id: str, inventory: dict[str, Any], *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any]:
        """The project's latest inventory: a revision of the one it holds, or a new scan."""
        store = self._store
        store.add_inventory(project_id, inventory, acted_for=acted_for, caused_by=caused_by)
        held: dict[str, Any] = store.summary(project_id)["inventory"]
        return held

    def documentation(self, project_id: str) -> list[dict[str, Any]]:
        store: ProjectHoldings = self._store
        return store.documentation(project_id)

    def documentation_text(self, project_id: str, digest: str) -> str | None:
        store: ProjectHoldings = self._store
        return store.documentation_text(project_id, digest)

    def documentation_source(self, project_id: str, digest: str) -> tuple[bytes, str] | None:
        store: ProjectHoldings = self._store
        return store.documentation_source(project_id, digest)

    def researchers(self, project_id: str) -> list[dict[str, Any]]:
        store: ProjectResearchers = self._store
        return store.researchers(project_id) or []

    def keep_researcher(
        self, project_id: str, chosen: dict[str, Any], *, acted_for: Principal, caused_by: str
    ) -> list[dict[str, Any]]:
        store: ProjectResearchers = self._store
        store.add_researcher(project_id, chosen, acted_for=acted_for, caused_by=caused_by)
        return store.researchers(project_id) or []

    def withdraw_researcher(
        self, project_id: str, *, acted_for: Principal, caused_by: str
    ) -> list[dict[str, Any]]:
        store: ProjectResearchers = self._store
        store.withdraw_researcher(
            project_id, acted_for.principal_id, acted_for=acted_for, caused_by=caused_by
        )
        return store.researchers(project_id) or []
