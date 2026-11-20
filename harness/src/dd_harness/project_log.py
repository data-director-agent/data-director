"""What a backend provides for projects: the project log the project rules are written over
(docs/specs/storage.md, "Project rules and the project log").

`ProjectLog` stores and reads, and decides nothing; `dd_harness.projects.Projects` gives callers
`ProjectStorage` (`dd_harness.storage`) over it. `dd_harness.project_files.FileProjectLog` is the
file backend, and `dd_harness.postgres.PostgresProjectLog` the PostgreSQL one.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any, Protocol


class ProjectSection(Protocol):
    """A project's exclusive section in a `ProjectLog`, in which the project rules read the log
    and append the events of one change."""

    def events(self) -> list[dict[str, Any]]:
        """Every event of the project, oldest first, as the section sees them."""
        ...

    def append(self, events: list[dict[str, Any]]) -> None:
        """Append `events` to the project's log, together or not at all."""
        ...


class ProjectLog(Protocol):
    """What a backend provides for projects: it stores and reads, and decides nothing. The
    project rules (`dd_harness.projects.Projects`) are written once over it, and give callers
    `ProjectStorage` (docs/specs/storage.md, "Project rules and the project log").

    A backend keeps these guarantees:

    1. A project's log is append-only: an event is never changed or removed, and events come
       back in the order they were appended. The log stores events as it is given them, and
       does not check or change them.
    2. `section` is exclusive for its project: while one is open, no other section of that
       project is entered, in this store or any other over the same record that the backend
       says it serves. Sections of different projects do not wait on one another. What a
       section appends is kept once the section ends without an exception; the project rules
       append a refusal and end the section before raising it.
    3. Content is kept once by digest and read back byte for byte. Keeping content is not part
       of a section: content kept for a change that is refused is harmless, because it is named
       by its digest alone.
    4. `project_of`, `project_ids` and every other read answer from what is stored when asked.
       Only what can never change, such as a conversation's project once recorded, may be
       cached.
    5. A malformed `project_id` or digest names nothing: `exists` is False, `blob` None, and
       `events` and `section` raise `KeyError`, as for a project that does not exist.
    """

    def create(self, project_id: str, event: dict[str, Any]) -> None:
        """A new project whose log begins with `event`. Raises `FileExistsError` if the project
        exists and `ValueError` for a malformed `project_id`."""
        ...

    def exists(self, project_id: str) -> bool:
        """Whether the project exists."""
        ...

    def events(self, project_id: str) -> list[dict[str, Any]]:
        """Every event of the project, oldest first. Raises `KeyError` for an unknown one."""
        ...

    def section(self, project_id: str) -> AbstractContextManager[ProjectSection]:
        """The project's exclusive section. Raises `KeyError` for an unknown project."""
        ...

    def keep_blob(self, project_id: str, digest: str, content: bytes) -> None:
        """Keep `content` under `digest`; content already kept is left as it is."""
        ...

    def blob(self, project_id: str, digest: str) -> bytes | None:
        """The content kept under `digest`, or None."""
        ...

    def project_of(self, conversation_id: str) -> str | None:
        """The project whose log records the conversation's `conversation_started` event, or
        None."""
        ...

    def project_ids(self) -> list[str]:
        """Every project, in the order created."""
        ...

    def projects_naming(self, principal_id: str) -> list[str]:
        """Every project with an event that `dd_harness.role_events.names` the principal, in the
        order created: the projects whose log may give them a role. A database answers from an
        index, so the cost follows the principal's projects, not the store's."""
        ...

    def logs_naming(self, principal_id: str) -> dict[str, list[dict[str, Any]]]:
        """Every event of each project `projects_naming` gives, oldest first, by project in the
        order created: what deciding the principal's access to all their projects reads, in one
        read. A database answers in one query, so the number of queries does not grow with the
        principal's projects."""
        ...
