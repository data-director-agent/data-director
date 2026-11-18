"""Deleting and restoring a conversation (docs/specs/app.md, rule 30; docs/specs/projects.md,
invariants 29 to 31): what the routes `DELETE /api/conversations/{id}`,
`POST /api/conversations/{id}/restore` and `GET /api/conversations/deleted` do.

The harness decides and records (`dd_harness.projects.conversations`) and says who may
(`dd_harness.project_access.may_delete_conversation`); this module finds the conversation's
project and answers with what the routes show. A conversation the person may not read is answered
as one that does not exist, so a refusal reveals nothing. A conversation in no project, which only
an app that keeps no projects has, cannot be deleted. Every method blocks, so a route calls it off
the event loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from dd_app.governance import CONVERSATION_ID, Governance, UnknownConversationError
from dd_harness import conversations, project_access
from dd_harness.listing import Page, check_limit
from dd_harness.storage import ProjectStorage
from dd_harness.transport.paging import PAGE_SIZE
from dd_sdk.contract.models import Principal


class MayNotDeleteError(PermissionError):
    """The person may read the conversation but may neither delete nor restore it."""


@dataclass(frozen=True)
class ConversationDeletion:
    governance: Governance

    def delete(
        self, conversation_id: str, *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any]:
        """Delete the conversation, which hides it from every list and removes nothing. Answers
        with its `conversation_id`, `project_id`, when (`at`) and by whom (`by`) it was deleted,
        and until when it may be restored. Raises `UnknownConversationError`,
        `MayNotDeleteError`, and the harness's `ConversationDeletedError` and
        `ProjectDeletedError`."""
        store, project_id = self._project(conversation_id, acted_for)
        deleted = store.delete_conversation(
            project_id, conversation_id, acted_for=acted_for, caused_by=caused_by
        )
        return {**deleted, "project_id": project_id}

    def restore(self, conversation_id: str, *, acted_for: Principal, caused_by: str) -> None:
        """Restore a deleted conversation. Raises `UnknownConversationError`,
        `MayNotDeleteError`, and the harness's `RestoreRefusedError` and `ProjectDeletedError`."""
        store, project_id = self._project(conversation_id, acted_for)
        store.restore_conversation(
            project_id, conversation_id, acted_for=acted_for, caused_by=caused_by
        )

    def deleted_for(
        self, person: Principal, *, limit: int = PAGE_SIZE, before: str | None = None
    ) -> Page:
        """A page of the deleted conversations `person` may still restore, the one deleted last
        first (`GET /api/conversations/deleted`): each with its `title` as the harness derives
        it, and its project, when, by whom and until when. The cursor is the last listed
        conversation; one that names none listed names an empty page."""
        check_limit(limit)
        store = self.governance.projects
        if store is None:
            return Page([])
        now = datetime.now(UTC)
        found = [
            deletion
            for project_id in project_access.readable_projects(store, person)
            for deletion in store.deleted_conversations(project_id)
            if datetime.fromisoformat(deletion["restorable_until"]) > now
            and project_access.may_delete_conversation(
                store, project_id, deletion["conversation_id"], person
            )
        ]
        found.sort(key=lambda d: d["at"], reverse=True)
        if before is not None:
            ids = [d["conversation_id"] for d in found]
            if before not in ids:
                return Page([])
            found = found[ids.index(before) + 1 :]
        page = [{**d, "title": self._title(d["conversation_id"])} for d in found[:limit]]
        return Page(page, page[-1]["conversation_id"] if len(found) > limit else None)

    def _project(self, conversation_id: str, person: Principal) -> tuple[ProjectStorage, str]:
        """The store and the project of a conversation `person` may delete or restore. One they
        may not read is unknown, and so is a deleted one they may not restore, so that only
        whoever may restore a deleted conversation learns that it is there."""
        store = self.governance.projects
        if store is None or not CONVERSATION_ID.fullmatch(conversation_id):
            raise UnknownConversationError(conversation_id)
        project_id = store.project_of(conversation_id)
        if project_id is None or not self.governance.may_read_project(project_id, person):
            raise UnknownConversationError(conversation_id)
        may = project_access.may_delete_conversation(store, project_id, conversation_id, person)
        is_deleted = project_access.conversation_deleted(store, project_id, conversation_id)
        if is_deleted and not may:
            raise UnknownConversationError(conversation_id)
        if not may:
            raise MayNotDeleteError(conversation_id)
        return store, project_id

    def _title(self, conversation_id: str) -> str | None:
        """The conversation's title as a list shows it, or None while it has no turn."""
        store = self.governance.conductor.store
        first = next(
            (
                e
                for e in store.iter_envelopes(conversation_id=conversation_id)
                if not e.get("parent_invocation_id")
            ),
            None,
        )
        return conversations.title_of(store, first)["title"] if first else None
