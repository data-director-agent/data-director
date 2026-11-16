"""What every area of the project rules shares: the log they are written over, how a change
enters a project's exclusive section, the event every change appends, and why a change is refused
(docs/specs/projects.md, docs/specs/storage.md).

There is one log and one fold (`dd_harness.projects.fold`). Each area of the rules
(`dd_harness.projects`) is a `ProjectRules` over the same log, so an area can be built alone over a
`ProjectLog`, and `Projects` is all of them together.

An event is never changed or removed. Each names whom it acted for and what caused it: the run
or request, or the command a person ran.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final

from dd_sdk.contract.models import UUID7_PATTERN, Principal, new_invocation_id, now

if TYPE_CHECKING:
    from dd_harness.storage import ProjectLog, ProjectSection

PROJECT_CREATED = "project_created"
PROJECT_RENAMED = "project_renamed"
PROJECT_DELETED = "project_deleted"
PROJECT_RESTORED = "project_restored"
CONVERSATION_STARTED = "conversation_started"
INVENTORY_ADDED = "inventory_added"
DOCUMENTATION_ADDED = "documentation_added"
RESEARCHER_ADDED = "researcher_added"
RESEARCHER_WITHDRAWN = "researcher_withdrawn"
REPOSITORY_CHOSEN = "repository_chosen"
DOCUMENT_VERSION_ADDED = "document_version_added"
DOCUMENT_VERSION_DECIDED = "document_version_decided"
DOCUMENT_CHANGE_REFUSED = "document_change_refused"
DOCUMENT_QUESTION_ANSWERED = "document_question_answered"
PROJECT_VALIDATED = "project_validated"
PACKAGE_BUILT = "package_built"
PROJECT_ID = re.compile(UUID7_PATTERN)
# Members every event has, which what an event carries never replaces.
ENVELOPE_KEYS = frozenset({"event", "event_id", "project_id", "at", "acted_for", "caused_by"})
DIGEST = re.compile(r"[0-9a-f]{64}")
# How long an owner may restore a deleted project, unless the deployment says otherwise
# (docs/specs/projects.md, invariant 25). Zero makes a deletion final to the app.
DEFAULT_RESTORE_PERIOD: Final = timedelta(days=30)


class ProjectError(ValueError):
    """The project does not exist, or what was to be added to it was refused."""


class UnknownProjectError(ProjectError):
    """No project has this identifier."""


class ProjectDeletedError(ProjectError):
    """The project is deleted, so it takes no new work until it is restored
    (docs/specs/projects.md, invariant 24)."""


class RestoreRefusedError(ProjectError):
    """The project is not deleted, or the period in which it could be restored is over
    (docs/specs/projects.md, invariant 25)."""


class Refusal(StrEnum):
    """Why a decision, an edit or an answer was refused as not naming what it must
    (docs/specs/projects.md, invariant 12). Each value is a Problem Details slug."""

    NO_DOCUMENT = "document-not-found"
    NOT_LATEST = "version-not-latest"
    DECIDED = "version-decided"
    DIGEST = "digest-mismatch"
    NOT_ASKED = "question-not-asked"


class ChangeRefusedError(ProjectError):
    """A decision or edit that does not name the document's latest text, a decision on a
    version already decided, or an answer to a question the latest version does not ask. The
    refusal is recorded, and nothing else is."""

    def __init__(self, refusal: Refusal, detail: str) -> None:
        super().__init__(detail)
        self.refusal = refusal
        self.detail = detail


@dataclass(frozen=True)
class Refused:
    """A change the project rules refuse: why, what a person is told, and what the
    `document_change_refused` event names. Returned, not raised, so that the refusal is written
    in the change's exclusive section before `ChangeRefusedError` is raised."""

    refusal: Refusal
    detail: str
    named: dict[str, Any]


def deletion(events: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    """The `project_deleted` event that stands, or None if the project is not deleted: a project
    is deleted when the last of its deletions and restorations is a deletion
    (docs/specs/projects.md, invariant 22)."""
    found: Mapping[str, Any] | None = None
    for event in events:
        if event["event"] == PROJECT_DELETED:
            found = event
        elif event["event"] == PROJECT_RESTORED:
            found = None
    return found


class ProjectRules:
    """The base of every area of the project rules: a `ProjectLog` (`dd_harness.storage`,
    docs/specs/storage.md) that stores and reads, and how a change reads and appends to it. The
    log decides nothing; the areas built on this decide whether a change is allowed."""

    def __init__(
        self, log: ProjectLog, *, restore_period: timedelta = DEFAULT_RESTORE_PERIOD
    ) -> None:
        if restore_period < timedelta(0):
            raise ValueError("a restore period is not negative")
        self.log = log
        self.restore_period = restore_period

    def exists(self, project_id: str) -> bool:
        return bool(PROJECT_ID.fullmatch(project_id)) and self.log.exists(project_id)

    def events(self, project_id: str) -> list[dict[str, Any]]:
        """Every event of the project, oldest first. Raises `ProjectError` for an unknown one."""
        self._require(project_id)
        try:
            return self.log.events(project_id)
        except KeyError:
            raise UnknownProjectError(f"no project {project_id!r}") from None

    def _latest(self, project_id: str, kind: str) -> dict[str, Any] | None:
        """The blob the last event of `kind` kept, or None if there is no such event."""
        found = [e for e in self.events(project_id) if e["event"] == kind]
        if not found:
            return None
        data: dict[str, Any] = json.loads(self._blob(project_id, found[-1]["digest"]))
        return data

    @contextmanager
    def _section(self, project_id: str, *, allow_deleted: bool = False) -> Iterator[ProjectSection]:
        """The project's exclusive section in the log. Raises `UnknownProjectError`, and
        `ProjectDeletedError` for a deleted project unless `allow_deleted`: a deleted project
        takes no new work (docs/specs/projects.md, invariant 24)."""
        self._require(project_id)
        with self.log.section(project_id) as section:
            if not allow_deleted and deletion(section.events()) is not None:
                raise ProjectDeletedError(f"project {project_id} is deleted")
            yield section

    def _deleted(self, events: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
        """When the project was deleted, by whom, and until when it may be restored, or None."""
        event = deletion(events)
        if event is None:
            return None
        until = datetime.fromisoformat(event["at"]) + self.restore_period
        return {
            "at": event["at"],
            "by": event["acted_for"],
            "restorable_until": until.isoformat(),
        }

    def _restorable(self, deleted: Mapping[str, Any]) -> bool:
        return self.restore_period > timedelta(0) and now() <= datetime.fromisoformat(
            deleted["restorable_until"]
        )

    def _checked[T](
        self,
        project_id: str,
        acted_for: Principal,
        caused_by: str,
        change: Callable[[ProjectSection], T | Refused],
    ) -> T:
        """Run `change` in the project's exclusive section (docs/specs/storage.md, invariant
        10). If it returns a refusal, its `document_change_refused` event is appended in the
        section, and `ChangeRefusedError` is raised once the section has ended, so the refusal
        is kept whether or not a backend undoes a section that raises (invariant 11). A
        `ProjectError` that `change` raises records nothing."""
        with self._section(project_id) as section:
            result = change(section)
            if isinstance(result, Refused):
                section.append(
                    [
                        self._event(
                            project_id,
                            DOCUMENT_CHANGE_REFUSED,
                            acted_for,
                            caused_by,
                            {**result.named, "refusal": result.refusal.value},
                        )
                    ]
                )
        if isinstance(result, Refused):
            raise ChangeRefusedError(result.refusal, result.detail)
        return result

    def _require(self, project_id: str) -> None:
        if not self.exists(project_id):
            raise UnknownProjectError(f"no project {project_id!r}")

    def _keep_blob(self, project_id: str, digest: str, content: bytes) -> None:
        self.log.keep_blob(project_id, digest, content)

    def _blob(self, project_id: str, digest: str) -> bytes:
        """Content an event of the project names. The log keeps it before the event is appended,
        so a missing blob is a damaged store, not a refusal."""
        content = self.log.blob(project_id, digest)
        if content is None:
            raise LookupError(f"project {project_id} keeps no content {digest}")
        return content

    def _append(
        self,
        project_id: str,
        kind: str,
        acted_for: Principal,
        caused_by: str,
        detail: dict[str, Any],
    ) -> None:
        """Append one event that no rule checks against the log, in its own section."""
        with self._section(project_id) as section:
            section.append([self._event(project_id, kind, acted_for, caused_by, detail)])

    @staticmethod
    def _event(
        project_id: str, kind: str, acted_for: Principal, caused_by: str, detail: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "event": kind,
            "event_id": new_invocation_id(),
            "project_id": project_id,
            "at": now().isoformat(),
            "acted_for": acted_for.model_dump(mode="json", exclude_none=True),
            "caused_by": caused_by,
            **detail,
        }
