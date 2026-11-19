"""One project's log as read once, for the reads of one invocation (docs/specs/storage.md,
invariant 12).

Every read of the project rules reads the whole log, so a caller that asks several questions of one
project reads it several times. The conductor asks many before a run: whether the principal may
read the project, whether it is deleted, and each fact it gives the agent
(`dd_harness.project_facts`). `SnapshotLog` is a `ProjectLog` that reads one project's events the
first time they are asked for and answers every later read from them, so `Projects` over it
answers as the store does, from one consistent read. It keeps no change: a change goes to the store,
whose exclusive section reads the log afresh. A snapshot lives as long as the invocation that took
it, and is never shared.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dd_harness.storage import ProjectLog, ProjectSection


class SnapshotLog:
    """The events and content of the project `project_id` in `log`, each read at most once."""

    def __init__(self, log: ProjectLog, project_id: str) -> None:
        self._log = log
        self._project_id = project_id
        self._events: list[dict[str, Any]] | None = None
        self._absent = False
        self._blobs: dict[str, bytes | None] = {}

    def _read(self) -> list[dict[str, Any]]:
        """The project's events, read from the log the first time. Raises `KeyError`, as the log
        does, for a project that does not exist."""
        if self._absent:
            raise KeyError(self._project_id)
        if self._events is None:
            try:
                self._events = self._log.events(self._project_id)
            except KeyError:
                self._absent = True
                raise
        return self._events

    def exists(self, project_id: str) -> bool:
        if project_id != self._project_id:
            return False
        try:
            self._read()
        except KeyError:
            return False
        return True

    def events(self, project_id: str) -> list[dict[str, Any]]:
        if project_id != self._project_id:
            raise KeyError(project_id)
        # A copy of the list: a caller may build on it, never change what later reads see.
        return list(self._read())

    def blob(self, project_id: str, digest: str) -> bytes | None:
        if not self.exists(project_id):
            return None
        if digest not in self._blobs:
            self._blobs[digest] = self._log.blob(project_id, digest)
        return self._blobs[digest]

    def project_of(self, conversation_id: str) -> str | None:
        return self._log.project_of(conversation_id)

    def project_ids(self) -> list[str]:
        return self._log.project_ids()

    def projects_naming(self, principal_id: str) -> list[str]:
        return self._log.projects_naming(principal_id)

    def logs_naming(self, principal_id: str) -> dict[str, list[dict[str, Any]]]:
        return self._log.logs_naming(principal_id)

    def create(self, project_id: str, event: dict[str, Any]) -> None:
        raise TypeError("a project snapshot takes no change")

    def section(self, project_id: str) -> AbstractContextManager[ProjectSection]:
        raise TypeError("a project snapshot takes no change")

    def keep_blob(self, project_id: str, digest: str, content: bytes) -> None:
        raise TypeError("a project snapshot takes no change")


__all__ = ["SnapshotLog"]
