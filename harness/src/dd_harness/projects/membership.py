"""A project's members and their roles (docs/specs/projects.md, invariants 16, 17 and 19).

Membership is a set of events in the project's log. `project_created` makes the creator an owner.
After that, `member_added` adds a person by the principal identifier they sign in with (an ORCID iD
for ORCID sign-in), `member_role_changed` changes a member's role, and `member_removed` removes
one. A member who leaves is removed by themselves. Each event names the member by `member_id`
and the role (`owner` or `member`), and its envelope says who acted and when. No name is kept:
a person may be added before they have ever signed in.

`member_roles` folds the log into each member's role. It is the one fold, and the access check
(`dd_harness.project_access.roles`) reads it. Removing a member takes effect from that event.
Earlier events keep their attribution, because no event is changed (invariant 19).

A project always has at least one owner, so the rules refuse to remove or demote the last one.
Who may change membership (an owner, or anyone removing themselves) is the caller's check
(`project_access`, `Action.MANAGE`), as for deleting a project.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any, Final, Literal

from dd_harness.projects.rules import (
    MEMBER_ADDED,
    MEMBER_REMOVED,
    MEMBER_ROLE_CHANGED,
    PROJECT_CREATED,
    MembershipRefusal,
    MembershipRefusedError,
    ProjectError,
    ProjectRules,
)
from dd_sdk.contract.models import IRI_PATTERN, Principal

OWNER: Final = "owner"
MEMBER: Final = "member"
type MemberRole = Literal["owner", "member"]
MEMBER_ROLES: Final = (OWNER, MEMBER)
_IRI = re.compile(IRI_PATTERN)


def member_roles(events: Iterable[Mapping[str, Any]]) -> dict[str, MemberRole]:
    """Each member's role in the project whose log is `events`, by `principal_id`, in the order
    they became members. A principal who is not in it is not a member."""
    found: dict[str, MemberRole] = {}
    for event in events:
        kind = event["event"]
        if kind == PROJECT_CREATED:
            found[event["acted_for"]["principal_id"]] = OWNER
        elif kind in (MEMBER_ADDED, MEMBER_ROLE_CHANGED):
            found[event["member_id"]] = event["role"]
        elif kind == MEMBER_REMOVED:
            found.pop(event["member_id"], None)
    return found


def _members(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each member, their role and when they became a member, in the order they did."""
    since: dict[str, str] = {}
    for event in events:
        kind = event["event"]
        if kind == PROJECT_CREATED:
            since[event["acted_for"]["principal_id"]] = event["at"]
        elif kind == MEMBER_ADDED:
            since[event["member_id"]] = event["at"]
        elif kind == MEMBER_REMOVED:
            since.pop(event["member_id"], None)
    roles = member_roles(events)
    return [
        {"member_id": member_id, "role": roles[member_id], "member_since": at}
        for member_id, at in since.items()
        if member_id in roles
    ]


def _check_role(role: str) -> None:
    if role not in MEMBER_ROLES:
        raise ProjectError(f"a project role is {' or '.join(MEMBER_ROLES)}, not {role!r}")


def _check_member_id(member_id: str) -> None:
    if not _IRI.fullmatch(member_id):
        raise ProjectError(f"a member is named by a principal identifier (an IRI): {member_id!r}")


def _refuse_last_owner(roles: Mapping[str, MemberRole], member_id: str, doing: str) -> None:
    if roles.get(member_id) == OWNER and sum(r == OWNER for r in roles.values()) == 1:
        raise MembershipRefusedError(
            MembershipRefusal.LAST_OWNER,
            f"a project always has an owner, so its last owner cannot be {doing}",
        )


def _refuse_non_member(roles: Mapping[str, MemberRole], member_id: str) -> None:
    if member_id not in roles:
        raise MembershipRefusedError(
            MembershipRefusal.NOT_A_MEMBER, f"{member_id} is not a member of the project"
        )


class Membership(ProjectRules):
    """The rules of a project's members and their roles."""

    def add_member(
        self,
        project_id: str,
        member_id: str,
        role: MemberRole = MEMBER,
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> None:
        """Add the person `member_id` names to the project with `role`. Raises
        `MembershipRefusedError` for someone already a member, `ProjectError` for a malformed
        identifier or role, and `UnknownProjectError` or `ProjectDeletedError`."""
        _check_member_id(member_id)
        _check_role(role)
        with self._section(project_id) as section:
            if member_id in member_roles(section.events()):
                raise MembershipRefusedError(
                    MembershipRefusal.ALREADY_MEMBER, f"{member_id} is already a member"
                )
            detail = {"member_id": member_id, "role": role}
            section.append([self._event(project_id, MEMBER_ADDED, acted_for, caused_by, detail)])

    def change_role(
        self,
        project_id: str,
        member_id: str,
        role: MemberRole,
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> None:
        """Give the member `member_id` names the role `role`. Raises `MembershipRefusedError`
        for someone who is not a member, a role they already have, or demoting the last owner."""
        _check_role(role)
        with self._section(project_id) as section:
            roles = member_roles(section.events())
            _refuse_non_member(roles, member_id)
            if roles[member_id] == role:
                raise MembershipRefusedError(
                    MembershipRefusal.SAME_ROLE, f"{member_id} is already a project {role}"
                )
            _refuse_last_owner(roles, member_id, "demoted")
            detail = {"member_id": member_id, "role": role}
            section.append(
                [self._event(project_id, MEMBER_ROLE_CHANGED, acted_for, caused_by, detail)]
            )

    def remove_member(
        self, project_id: str, member_id: str, *, acted_for: Principal, caused_by: str
    ) -> None:
        """Remove the member `member_id` names, from this event on; a member who leaves removes
        themselves. Raises `MembershipRefusedError` for someone who is not a member, or the last
        owner."""
        with self._section(project_id) as section:
            roles = member_roles(section.events())
            _refuse_non_member(roles, member_id)
            _refuse_last_owner(roles, member_id, "removed")
            detail = {"member_id": member_id}
            section.append([self._event(project_id, MEMBER_REMOVED, acted_for, caused_by, detail)])

    def members(self, project_id: str) -> list[dict[str, Any]]:
        """Each member of the project, by `member_id`, with their `role` and when they became a
        member (`member_since`), the creator first. Raises `UnknownProjectError`."""
        return _members(self.events(project_id))
