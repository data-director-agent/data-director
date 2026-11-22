"""A project's lifecycle (docs/specs/projects.md, "Deletion and retention")."""

from __future__ import annotations

from typing import Any

from dd_app.governance import CREATED_BY_ROUTE
from dd_app.project_service._area import Area, TitleMismatchError
from dd_harness.projects import TITLE_BY_RESEARCHER
from dd_harness.storage import ProjectLifecycle
from dd_sdk.contract.models import Principal


class Lifecycle(Area):
    @property
    def keeps_projects(self) -> bool:
        return self.governance.projects is not None

    def summary(self, project_id: str) -> dict[str, Any]:
        """The project as its log gives it."""
        return self._store.summary(project_id)

    def create(self, title: str | None, *, acted_for: Principal) -> dict[str, Any]:
        """A project of its own, with no conversation, as `GET /api/projects` lists it."""
        store: ProjectLifecycle = self._store
        project_id = store.create(acted_for=acted_for, caused_by=CREATED_BY_ROUTE, title=title)
        return {**store.summary(project_id), "conversations": []}

    def delete(
        self, project_id: str, typed: str, *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any]:
        """Delete the project, which hides it and removes nothing, once the person has typed its
        name: its title, or its identifier while it has none. The check is here as well as on the
        page, so no client can skip it. Answers with its summary, whose `deleted` says until when
        it may be restored."""
        store: ProjectLifecycle = self._store
        if typed.strip() != (store.summary(project_id)["title"] or project_id):
            raise TitleMismatchError(
                "`title` is not the project's name. Type it exactly to delete the project."
            )
        store.delete(project_id, acted_for=acted_for, caused_by=caused_by)
        return store.summary(project_id)

    def restore(self, project_id: str, *, acted_for: Principal, caused_by: str) -> dict[str, Any]:
        store: ProjectLifecycle = self._store
        store.restore(project_id, acted_for=acted_for, caused_by=caused_by)
        return store.summary(project_id)

    def rename(
        self, project_id: str, title: str, *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any]:
        """A person's name for the project, which a model's never replaces."""
        store: ProjectLifecycle = self._store
        store.rename(
            project_id, title, source=TITLE_BY_RESEARCHER, acted_for=acted_for, caused_by=caused_by
        )
        return store.summary(project_id)
