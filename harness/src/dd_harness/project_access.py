"""Who may do what in a project: the one access check (docs/specs/projects.md, invariants 16, 17).

The answer is read from the project's log and from nothing else, so it holds for every storage
backend and cannot disagree with the record. `roles` folds the log into each principal's role;
`allowed` is the spec's table of what each role may do; `may` puts the two together for a
principal and a project.

The project's creator is its first owner (`project_created`). After that, the membership events
add members, change their roles and remove them (`dd_harness.projects.membership`), and
`roles` reads them with `member_roles`, the one fold of membership.

`readable_logs` finds the projects a principal may read without reading every project's log:
the backend reads, at once, the logs of the projects whose log may give them a role
(`ProjectLifecycle.logs_naming`, one query over an index in a database), and those logs alone
decide it here. `readable_projects`, `deleted_projects` and `hidden_in` are each one read too, so
what a listing asks of the store does not grow with the number of projects.

A caller that refuses a principal with no role answers as for a project that does not exist, so
that a refusal does not reveal whether it does; one that refuses a member an owner's action says
so (docs/specs/projects.md, invariant 17).

A deleted project is hidden from everyone but its owners (invariant 23): `role_of` gives no other
principal a role in it, and `readable_projects` leaves it out for everyone. An owner keeps their
role, so that they may restore it, and finds it in `deleted_projects`.

A conversation in a project may be deleted and restored by whoever started it, while they may
still contribute to the project, and by an owner (invariant 30): `may_delete_conversation`.
`hidden_in` gives the deleted conversations of the logs of the projects a principal may read, which
every listing leaves out (`dd_harness.listing.Readable`).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol

from dd_harness import steward_access
from dd_harness.listing import Readable
from dd_harness.projects import (
    ProjectDeletedError,
    UnknownProjectError,
    conversation_deletions,
    deletion,
    is_last_owner,
    member_roles,
)
from dd_harness.storage import ProjectConversations, ProjectLifecycle

if TYPE_CHECKING:
    from dd_harness.policy import Profile
    from dd_harness.project_facts import FactSource
from dd_sdk.contract.models import Principal


class Role(StrEnum):
    """A principal's role in a project, separate from any deployment role."""

    OWNER = "owner"
    MEMBER = "member"


class Action(StrEnum):
    """What a principal may ask to do in a project, as the spec's roles table groups it."""

    # Read the project, start a conversation in it, add a turn to any of its conversations.
    READ = "read"
    # Add an inventory, documentation or their own ORCID facts, edit a document as a new proposed
    # version, answer a draft's questions, mark progress, choose a repository, validate, build a
    # package.
    CONTRIBUTE = "contribute"
    # Approve or reject a document version.
    DECIDE = "decide"
    # Add or remove a member, or change a role; delete the project, or restore a deleted one;
    # delete or restore any of its conversations.
    MANAGE = "manage"


_ALLOWED: Mapping[Role, frozenset[Action]] = {
    Role.OWNER: frozenset(Action),
    Role.MEMBER: frozenset({Action.READ, Action.CONTRIBUTE}),
}


def roles(events: Iterable[Mapping[str, Any]]) -> dict[str, Role]:
    """Each principal's role in the project whose log is `events`, by `principal_id`. A
    principal with none is not a member."""
    return {principal_id: Role(role) for principal_id, role in member_roles(events).items()}


def allowed(role: Role | None, action: Action) -> bool:
    """Whether a principal with `role` (None: not a member) may take `action`."""
    return role is not None and action in _ALLOWED[role]


def role_of(store: ProjectLifecycle, project_id: str, principal: Principal) -> Role | None:
    """`principal`'s role in the project `project_id`, or None if they have none, if there is no
    such project (an identifier that names none included), or if it is deleted and they are not
    an owner."""
    if not store.exists(project_id):
        return None
    return _role(store.events(project_id), principal)


def _role(events: list[dict[str, Any]], principal: Principal) -> Role | None:
    role = roles(events).get(principal.principal_id)
    if role is not Role.OWNER and deletion(events) is not None:
        return None
    return role


def may(store: ProjectLifecycle, project_id: str, principal: Principal, action: Action) -> bool:
    """Whether `principal` may take `action` in the project `project_id`."""
    return allowed(role_of(store, project_id, principal), action)


def readable_logs(store: ProjectLifecycle, principal: Principal) -> dict[str, list[dict[str, Any]]]:
    """The log of each project `principal` may read, by project, the one created first first,
    deleted ones left out. Only the logs of the projects that name them are read, in one read, so
    the cost follows their projects, not the store's, and the number of reads follows neither."""
    return {
        project_id: events
        for project_id, events in store.logs_naming(principal.principal_id).items()
        if deletion(events) is None and allowed(_role(events, principal), Action.READ)
    }


def readable_projects(store: ProjectLifecycle, principal: Principal) -> list[str]:
    """The projects `principal` may read, the one created first first, deleted ones left out
    (`readable_logs`)."""
    return list(readable_logs(store, principal))


def deleted_projects(store: ProjectLifecycle, principal: Principal) -> list[str]:
    """The deleted projects `principal` may restore, the one created first first: those they
    own (docs/specs/projects.md, invariant 23). Whether each may still be restored is in its
    summary's `deleted`. One read, as for `readable_logs`."""
    return [
        project_id
        for project_id, events in store.logs_naming(principal.principal_id).items()
        if deletion(events) is not None and allowed(_role(events, principal), Action.MANAGE)
    ]


def may_remove_member(
    store: ProjectLifecycle, project_id: str, principal: Principal, member_id: str
) -> bool:
    """Whether `principal` may remove the member `member_id` names from the project
    `project_id`: an owner may remove anyone, and any member may leave
    (docs/specs/projects.md, Roles). That the last owner stays is the rules' check
    (`dd_harness.projects.Membership.remove_member`)."""
    role = role_of(store, project_id, principal)
    return allowed(role, Action.MANAGE) or (
        role is not None and member_id == principal.principal_id
    )


def may_leave(store: ProjectLifecycle, project_id: str, principal: Principal) -> bool:
    """Whether `principal` may leave the project `project_id`: a member may, and an owner may
    unless they are its last (docs/specs/projects.md, Roles)."""
    if role_of(store, project_id, principal) is None:
        return False
    return not is_last_owner(member_roles(store.events(project_id)), principal.principal_id)


class ConversationAccess(ProjectLifecycle, ProjectConversations, Protocol):
    """What deciding who may delete a project's conversations reads."""


def may_delete_conversation(
    store: ConversationAccess, project_id: str, conversation_id: str, principal: Principal
) -> bool:
    """Whether `principal` may delete or restore the conversation `conversation_id` in the
    project `project_id`: an owner may, and whoever started it may while they may contribute."""
    role = role_of(store, project_id, principal)
    if allowed(role, Action.MANAGE):
        return True
    starter = store.started_by(project_id, conversation_id)
    return starter == principal.principal_id and allowed(role, Action.CONTRIBUTE)


def readable_from(reader: Principal, logs: Mapping[str, list[dict[str, Any]]]) -> Readable:
    """What a listing includes for `reader`, from the logs of the projects they may read
    (`readable_logs`): runs in those projects but not in their deleted conversations, and runs
    in no project that acted for them."""
    return Readable(reader.principal_id, frozenset(logs), hidden_in(logs.values()))


def hidden_in(logs: Iterable[Iterable[Mapping[str, Any]]]) -> frozenset[str]:
    """The deleted conversations of the projects whose logs, already read, are `logs`, which a
    listing leaves out."""
    return frozenset(
        conversation_id for events in logs for conversation_id in conversation_deletions(events)
    )


def conversation_deleted(store: ProjectLifecycle, project_id: str, conversation_id: str) -> bool:
    """Whether the conversation `conversation_id` in the project `project_id` is deleted."""
    return conversation_id in conversation_deletions(store.events(project_id))


class Snapshots(Protocol):
    def snapshot(self, project_id: str) -> FactSource: ...


def run_facts(
    projects: Snapshots | None,
    project_id: str | None,
    acting_for: Principal,
    profile: Profile | None = None,
) -> FactSource | None:
    """The snapshot of `project_id` a run reads everything it asks of its project from, or None
    for a run in no project. Only someone who may read the project runs anything in it, or a
    steward the profile lets run an agent there (docs/specs/stewardship.md, invariant 6); anyone
    else is answered as for a project that does not exist (docs/specs/projects.md, invariant
    17). A deleted project takes no new run, not even its owner's (invariant 24). A delegated
    child is not checked again: its grant carries its parent's project."""
    if projects is None or project_id is None:
        return None
    facts = projects.snapshot(project_id)
    if not may(facts, project_id, acting_for, Action.READ) and not _steward_runs(
        facts, profile, project_id, acting_for
    ):
        raise UnknownProjectError(f"no project {project_id!r}")
    if facts.is_deleted(project_id):
        raise ProjectDeletedError(f"project {project_id} is deleted")
    return facts


def _steward_runs(
    facts: FactSource, profile: Profile | None, project_id: str, acting_for: Principal
) -> bool:
    if profile is None:
        return False
    found = steward_access.steward_of(facts, profile, project_id, acting_for)
    return found is not None and found.refusal("run") is None
