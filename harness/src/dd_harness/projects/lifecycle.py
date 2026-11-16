"""A project's life: creating, naming, deleting and restoring it, the conversations started in
it, and what a list of projects shows of each (docs/specs/projects.md).

A project is a record of its own that outlives any conversation. The run store is separate:
conversations are still derived from it (docs/specs/orchestration.md), and the project is not. A
conversation started from a project is a `conversation_started` event; `project_of` says which
project a conversation was started in, from what the logs hold when asked.

A project may have a title, so that a person can tell projects apart. A person gives it when
creating the project or renames it later; while no person has, an orchestrator's model may name
it (`rename`, a `project_renamed` event saying which). The latest title counts, and a model's is
refused once a person has given one.

An owner deletes a project with a `project_deleted` event and restores it with
`project_restored` (`delete`, `restore`). Nothing is removed: a deleted project takes no new work,
except that a run already going is recorded, and it can be restored within `restore_period` of
its deletion, which the deployment sets (docs/specs/projects.md, invariants 22 to 26). Who sees a
deleted project is `dd_harness.project_access`.
"""

from __future__ import annotations

from typing import Any, Final, Literal

from dd_harness import intake
from dd_harness import progress as flow
from dd_harness.projects.fold import APPROVED, PROPOSED, REJECTED, fold
from dd_harness.projects.rules import (
    CONVERSATION_STARTED,
    INVENTORY_ADDED,
    PROJECT_CREATED,
    PROJECT_DELETED,
    PROJECT_RENAMED,
    PROJECT_RESTORED,
    REPOSITORY_CHOSEN,
    ProjectError,
    ProjectRules,
    RestoreRefusedError,
    deletion,
)
from dd_sdk.contract.models import Principal, new_invocation_id

# The longest project title the harness keeps, in characters: a name, not a description.
TITLE_MAX_LENGTH = 200
# Who gave a project its title: a person (when creating or renaming it) or an orchestrator's
# model. A person's title is never replaced by a model's.
TITLE_BY_RESEARCHER: Final = "researcher"
TITLE_BY_MODEL: Final = "model"
type TitleSource = Literal["researcher", "model"]


def _check_title(title: str) -> None:
    if len(title) > TITLE_MAX_LENGTH:
        raise ProjectError(f"a project title is at most {TITLE_MAX_LENGTH} characters")


def _title(events: list[dict[str, Any]]) -> tuple[str | None, TitleSource | None]:
    """A project's latest title and who gave it: a title given at creation is a person's."""
    for event in reversed(events):
        if event["event"] == PROJECT_RENAMED:
            return event["title"], event["title_source"]
        if event["event"] == PROJECT_CREATED and event.get("title"):
            return event["title"], TITLE_BY_RESEARCHER
    return None, None


class Lifecycle(ProjectRules):
    """The rules of a project's life: creating, naming, deleting and restoring it, starting a
    conversation in it, and summarising it."""

    def create(self, *, acted_for: Principal, caused_by: str, title: str | None = None) -> str:
        """A new project, and its `project_created` event. Returns its `project_id` (UUIDv7).

        Raises `ProjectError` for a title longer than `TITLE_MAX_LENGTH`; a blank title is none."""
        title = (title or "").strip() or None
        if title is not None:
            _check_title(title)
        project_id = new_invocation_id()
        detail = {"title": title} if title else {}
        self.log.create(
            project_id, self._event(project_id, PROJECT_CREATED, acted_for, caused_by, detail)
        )
        return project_id

    def rename(
        self,
        project_id: str,
        title: str,
        *,
        source: TitleSource,
        acted_for: Principal,
        caused_by: str,
    ) -> bool:
        """Give the project a new title, a `project_renamed` event saying who gave it. Returns
        False, and records nothing, for a model's title once a person has given one. Raises
        `ProjectError` for an unknown project, a blank title, one longer than
        `TITLE_MAX_LENGTH` or a source that is neither."""
        if source not in (TITLE_BY_RESEARCHER, TITLE_BY_MODEL):
            raise ProjectError(f"a title is given by a researcher or a model, not {source!r}")
        title = title.strip()
        if not title:
            raise ProjectError("a project title may not be blank")
        _check_title(title)
        with self._section(project_id) as section:
            _, held = _title(section.events())
            if source == TITLE_BY_MODEL and held == TITLE_BY_RESEARCHER:
                return False
            detail = {"title": title, "title_source": source}
            section.append([self._event(project_id, PROJECT_RENAMED, acted_for, caused_by, detail)])
        return True

    def delete(self, project_id: str, *, acted_for: Principal, caused_by: str) -> dict[str, Any]:
        """Delete the project: a `project_deleted` event, which hides it and stops it taking new
        work; nothing is removed (docs/specs/projects.md, invariants 22 to 26). Returns what
        `summary` gives of `deleted`. Raises `UnknownProjectError` for an unknown project and
        `ProjectDeletedError` for one already deleted. Who may delete is the caller's check
        (`project_access`, `Action.MANAGE`)."""
        event = self._event(project_id, PROJECT_DELETED, acted_for, caused_by, {})
        with self._section(project_id) as section:
            section.append([event])
        deleted = self._deleted([event])
        if deleted is None:  # pragma: no cover - the event just appended is a deletion
            raise LookupError(f"project {project_id} was not deleted")
        return deleted

    def restore(self, project_id: str, *, acted_for: Principal, caused_by: str) -> None:
        """Restore a deleted project within the restore period: one `project_restored` event,
        which changes nothing else, so the project is as it was (docs/specs/projects.md,
        invariant 25). Raises `UnknownProjectError` for an unknown project and
        `RestoreRefusedError` for one not deleted or whose period is over."""
        with self._section(project_id, allow_deleted=True) as section:
            deleted = self._deleted(section.events())
            if deleted is None:
                raise RestoreRefusedError("the project is not deleted")
            if not self._restorable(deleted):
                raise RestoreRefusedError(
                    f"the project could be restored until {deleted['restorable_until']}"
                )
            section.append([self._event(project_id, PROJECT_RESTORED, acted_for, caused_by, {})])

    def is_deleted(self, project_id: str) -> bool:
        """Whether the project is deleted. Raises `UnknownProjectError` for an unknown one."""
        return deletion(self.events(project_id)) is not None

    def start_conversation(self, project_id: str, *, acted_for: Principal, caused_by: str) -> str:
        """A new conversation in the project, and its `conversation_started` event. Returns its
        `conversation_id` (UUIDv7). Raises `UnknownProjectError` for an unknown project."""
        conversation_id = new_invocation_id()
        self._append(
            project_id,
            CONVERSATION_STARTED,
            acted_for,
            caused_by,
            {"conversation_id": conversation_id},
        )
        return conversation_id

    def project_of(self, conversation_id: str) -> str | None:
        """The project the conversation was started in, or None if the logs record it in none
        when asked."""
        return self.log.project_of(conversation_id)

    def projects(self) -> list[dict[str, Any]]:
        """A summary of every project, the one created first first (see `summary`)."""
        return [self.summary(project_id) for project_id in self.log.project_ids()]

    def projects_naming(self, principal_id: str) -> list[str]:
        """The projects whose log may give the principal a role, the one created first first."""
        return self.log.projects_naming(principal_id)

    def summary(self, project_id: str) -> dict[str, Any]:
        """What a list of projects shows of one: its latest title and who gave it (`title_source`:
        `researcher`, `model`, or None while it has none), who created it and when, the latest
        inventory and repository chosen, how many conversations were started in it, how many
        documents it has whose latest version is in each state, where it is in the process flow,
        whether its intake is pending, complete or dismissed, if it is deleted, when, by whom and
        until when it may be restored (`deleted`, else None), and for how many days after a
        deletion it may be (`restore_days`, 0 if deletion is final). Raises
        `UnknownProjectError`."""
        events = self.events(project_id)
        created = events[0]
        title, title_source = _title(events)
        states = {PROPOSED: 0, APPROVED: 0, REJECTED: 0}
        for document in fold(events).values():
            states[document["versions"][-1]["state"]] += 1
        return {
            "project_id": project_id,
            "title": title,
            "title_source": title_source,
            "created_at": created["at"],
            "created_by": created["acted_for"],
            "inventory": _inventory_summary(events),
            "repository": _repository_summary(events),
            "conversation_count": sum(1 for e in events if e["event"] == CONVERSATION_STARTED),
            "documents": states,
            "progress": flow.describe(events),
            "intake": intake.state(events),
            "deleted": self._deleted(events),
            "restore_days": self.restore_period.days,
        }


def _inventory_summary(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """What a summary shows of the inventory added last, or None."""
    inventory = next((e for e in reversed(events) if e["event"] == INVENTORY_ADDED), None)
    if inventory is None:
        return None
    return {
        "digest": inventory["digest"],
        "file_count": inventory["file_count"],
        "inventory_made_at": inventory["inventory_made_at"],
        "added_at": inventory["at"],
        "revises": inventory.get("revises"),
        "part_count": inventory.get("part_count"),
    }


def _repository_summary(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """What a summary shows of the repository chosen last, or None."""
    repository = next((e for e in reversed(events) if e["event"] == REPOSITORY_CHOSEN), None)
    if repository is None:
        return None
    return {
        "re3data_id": repository["re3data_id"],
        "repository_name": repository["repository_name"],
        "warnings": repository["warnings"],
        "chosen_at": repository["at"],
    }
