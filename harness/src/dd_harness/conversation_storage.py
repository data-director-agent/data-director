"""What the harness asks of a store for deleting and restoring a project's conversations
(`dd_harness.projects.conversations`, docs/specs/projects.md, invariants 29 to 31).
`dd_harness.storage` composes it into `ProjectStorage` with the other areas of the project rules;
both changes are checked against the log in the project's exclusive section, as `ProjectStorage`
guarantee 2 says."""

from __future__ import annotations

from typing import Any, Protocol

from dd_sdk.contract.models import Principal


class ProjectConversations(Protocol):
    """Deleting and restoring a conversation started in a project."""

    def delete_conversation(
        self, project_id: str, conversation_id: str, *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any]:
        """Delete the conversation (a `conversation_deleted` event); `ConversationDeletedError`
        if it is already, `UnknownConversationError` if it was not started in the project.
        Returns when it was deleted, by whom and until when it may be restored."""
        ...

    def restore_conversation(
        self, project_id: str, conversation_id: str, *, acted_for: Principal, caused_by: str
    ) -> None:
        """Restore a deleted conversation (a `conversation_restored` event);
        `RestoreRefusedError` if it is not deleted or its restore period is over."""
        ...

    def deleted_conversations(self, project_id: str) -> list[dict[str, Any]]:
        """The project's deleted conversations, the one deleted first first."""
        ...

    def started_by(self, project_id: str, conversation_id: str) -> str | None:
        """The `principal_id` of whoever started the conversation, or None if the project
        records no such conversation."""
        ...
