"""Where the project is (docs/specs/orchestration.md) and its intake (docs/specs/app.md)."""

from __future__ import annotations

from typing import Any

from dd_app.project_service._area import Area
from dd_harness.storage import ProjectProgress
from dd_sdk.contract.models import Principal


class Progress(Area):
    def progress(self, project_id: str) -> dict[str, Any]:
        store: ProjectProgress = self._store
        return store.progress(project_id)

    def choose_entry(
        self, project_id: str, entry: int, *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any]:
        store: ProjectProgress = self._store
        store.choose_entry(project_id, entry, acted_for=acted_for, caused_by=caused_by)
        return store.progress(project_id)

    def mark_step(
        self, project_id: str, step_id: str, mark: str, *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any]:
        store: ProjectProgress = self._store
        store.mark_step(project_id, step_id, mark, acted_for=acted_for, caused_by=caused_by)
        return store.progress(project_id)

    def intake(self, project_id: str) -> dict[str, Any]:
        store: ProjectProgress = self._store
        return store.intake(project_id)

    def answer_intake(
        self,
        project_id: str,
        question_id: str,
        values: list[str],
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> dict[str, Any]:
        store: ProjectProgress = self._store
        store.answer_intake(
            project_id, question_id, values, acted_for=acted_for, caused_by=caused_by
        )
        return store.intake(project_id)

    def dismiss_intake(
        self, project_id: str, *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any]:
        store: ProjectProgress = self._store
        store.dismiss_intake(project_id, acted_for=acted_for, caused_by=caused_by)
        return store.intake(project_id)
