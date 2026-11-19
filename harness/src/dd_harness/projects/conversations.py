"""Deleting and restoring a conversation started in a project (docs/specs/projects.md,
invariants 29 to 31).

A conversation is derived from the run store, which is written once, so deleting one removes
nothing: a `conversation_deleted` event in its project's log hides it from every list, and a
`conversation_restored` event within the project's restore period brings it back as it was. A
conversation is deleted when the last of its deletions and restorations is a deletion, as a
project is (`dd_harness.projects.rules.deletion`). Who may delete one is the caller's check
(`dd_harness.project_access.may_delete_conversation`).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from dd_harness.projects.rules import (
    CONVERSATION_DELETED,
    CONVERSATION_RESTORED,
    CONVERSATION_STARTED,
    ConversationDeletedError,
    ProjectRules,
    RestoreRefusedError,
    UnknownConversationError,
)
from dd_sdk.contract.models import Principal


def conversation_deletions(events: Iterable[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    """The `conversation_deleted` event that stands for each deleted conversation of the project
    whose log is `events`, by `conversation_id`."""
    found: dict[str, Mapping[str, Any]] = {}
    for event in events:
        if event["event"] == CONVERSATION_DELETED:
            found[event["conversation_id"]] = event
        elif event["event"] == CONVERSATION_RESTORED:
            found.pop(event["conversation_id"], None)
    return found


def started(events: Iterable[Mapping[str, Any]], conversation_id: str) -> Mapping[str, Any] | None:
    """The `conversation_started` event of `conversation_id`, or None if the log records none."""
    return next(
        (
            e
            for e in events
            if e["event"] == CONVERSATION_STARTED and e["conversation_id"] == conversation_id
        ),
        None,
    )


class Conversations(ProjectRules):
    """Deleting and restoring a project's conversations."""

    def delete_conversation(
        self, project_id: str, conversation_id: str, *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any]:
        """Delete the conversation: a `conversation_deleted` event, which hides it; nothing is
        removed. Returns its `conversation_id`, when and by whom it was deleted and until when it
        may be restored. Raises `UnknownProjectError` for an unknown project,
        `ProjectDeletedError` for a deleted one, `UnknownConversationError` for a conversation
        not started in it, and `ConversationDeletedError` for one already deleted."""
        with self._section(project_id) as section:
            events = section.events()
            if started(events, conversation_id) is None:
                raise UnknownConversationError(f"no conversation {conversation_id!r}")
            if conversation_id in conversation_deletions(events):
                raise ConversationDeletedError(f"conversation {conversation_id} is deleted")
            event = self._event(
                project_id,
                CONVERSATION_DELETED,
                acted_for,
                caused_by,
                {"conversation_id": conversation_id},
            )
            section.append([event])
        return {"conversation_id": conversation_id, **self._deletion_summary(event)}

    def restore_conversation(
        self, project_id: str, conversation_id: str, *, acted_for: Principal, caused_by: str
    ) -> None:
        """Restore a deleted conversation within the restore period: one
        `conversation_restored` event. Raises `UnknownProjectError`, `ProjectDeletedError`, and
        `RestoreRefusedError` for a conversation not deleted or whose period is over."""
        with self._section(project_id) as section:
            deletion = conversation_deletions(section.events()).get(conversation_id)
            if deletion is None:
                raise RestoreRefusedError("the conversation is not deleted")
            deleted = self._deletion_summary(deletion)
            if not self._restorable(deleted):
                raise RestoreRefusedError(
                    f"the conversation could be restored until {deleted['restorable_until']}"
                )
            detail = {"conversation_id": conversation_id}
            section.append(
                [self._event(project_id, CONVERSATION_RESTORED, acted_for, caused_by, detail)]
            )

    def deleted_conversations(self, project_id: str) -> list[dict[str, Any]]:
        """The project's deleted conversations, the one deleted first first: each one's
        `conversation_id`, who started it (`started_by`, a `principal_id`), when and by whom it
        was deleted, and until when it may be restored. Raises `UnknownProjectError`."""
        events = self.events(project_id)
        found = []
        for conversation_id, event in conversation_deletions(events).items():
            start = started(events, conversation_id) or {}
            starter = (start.get("acted_for") or {}).get("principal_id")
            found.append(
                {
                    "conversation_id": conversation_id,
                    "project_id": project_id,
                    "started_by": starter,
                    **self._deletion_summary(event),
                }
            )
        return sorted(found, key=lambda item: item["at"])

    def started_by(self, project_id: str, conversation_id: str) -> str | None:
        """The `principal_id` of whoever started the conversation in the project, or None if the
        project records no such conversation. Raises `UnknownProjectError`."""
        event = started(self.events(project_id), conversation_id)
        return None if event is None else (event.get("acted_for") or {}).get("principal_id")
