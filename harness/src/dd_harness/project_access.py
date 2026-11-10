"""Who may do what in a project: the one access check (docs/specs/projects.md, invariants 16, 17).

The answer is read from the project's log and from nothing else, so it holds for every storage
backend and cannot disagree with the record. `roles` folds the log into each principal's role;
`allowed` is the spec's table of what each role may do; `may` puts the two together for a
principal and a project.

Today the log makes one owner, the principal who created the project (`project_created`). The
membership events that add members, change roles and remove them are TODO(#389): they extend
`roles` and `dd_harness.role_events.names`, and nothing that calls `may` changes.

`readable_projects` finds the projects a principal may read without reading every project's log:
the backend names the projects whose log may give them a role (`ProjectStorage.projects_naming`,
an index in a database), and only those logs are read here to confirm it.

A caller that refuses a principal with no role answers as for a project that does not exist, so
that a refusal does not reveal whether it does; one that refuses a member an owner's action says
so (docs/specs/projects.md, invariant 17).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import StrEnum
from typing import Any

from dd_harness.projects import PROJECT_CREATED
from dd_harness.storage import ProjectStorage
from dd_sdk.contract.models import Principal


class Role(StrEnum):
    """A principal's role in a project, separate from any deployment role."""

    OWNER = "owner"
    MEMBER = "member"


class Action(StrEnum):
    """What a principal may ask to do in a project, as the spec's roles table groups it."""

    # Read the project, start a conversation in it, add a turn to any of its conversations.
    READ = "read"
    # Add an inventory or documentation, edit a document as a new proposed version, answer a
    # draft's questions, mark progress, choose a repository, validate, build a package.
    CONTRIBUTE = "contribute"
    # Approve or reject a document version.
    DECIDE = "decide"
    # Add or remove a member, or change a role.
    MANAGE = "manage"


_ALLOWED: Mapping[Role, frozenset[Action]] = {
    Role.OWNER: frozenset(Action),
    Role.MEMBER: frozenset({Action.READ, Action.CONTRIBUTE}),
}


def roles(events: Iterable[Mapping[str, Any]]) -> dict[str, Role]:
    """Each principal's role in the project whose log is `events`, by `principal_id`. A
    principal with none is not a member."""
    found: dict[str, Role] = {}
    for event in events:
        if event["event"] == PROJECT_CREATED:
            found[event["acted_for"]["principal_id"]] = Role.OWNER
    return found


def allowed(role: Role | None, action: Action) -> bool:
    """Whether a principal with `role` (None: not a member) may take `action`."""
    return role is not None and action in _ALLOWED[role]


def role_of(store: ProjectStorage, project_id: str, principal: Principal) -> Role | None:
    """`principal`'s role in the project `project_id`, or None if they have none or there is no
    such project (an identifier that names none included)."""
    if not store.exists(project_id):
        return None
    return roles(store.events(project_id)).get(principal.principal_id)


def may(store: ProjectStorage, project_id: str, principal: Principal, action: Action) -> bool:
    """Whether `principal` may take `action` in the project `project_id`."""
    return allowed(role_of(store, project_id, principal), action)


def readable_projects(store: ProjectStorage, principal: Principal) -> list[str]:
    """The projects `principal` may read, the one created first first. Only the logs of the
    projects that name them are read, so the cost follows their projects, not the store's."""
    found = []
    for project_id in store.projects_naming(principal.principal_id):
        role = roles(store.events(project_id)).get(principal.principal_id)
        if allowed(role, Action.READ):
            found.append(project_id)
    return found
