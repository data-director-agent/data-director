"""A project's members (docs/specs/projects.md, Roles and invariants 16, 17 and 19; #391).

`GET /api/projects/{id}/members` lists the members, their roles and since when, with the name a
member kept from their own ORCID record where they kept one, and says what the person asking may
do: whether they may manage members (`may_manage`), whom they may remove (each `removable`), and
whether they may leave (`may_leave`). The shell offers only that; it decides nothing.

An owner adds a person by the identifier they sign in with, an ORCID iD for ORCID sign-in
(`POST …/members`, `{"member", "role"}`), and changes a member's role (`PATCH …/members`,
`{"member_id", "role"}`). `DELETE …/members?member_id=…` removes a member: an owner may remove
anyone, and any member may remove themselves, which is leaving. Each answers with the members as
the person then sees them, except that someone who leaves is answered `204`: the project is no
longer theirs to read. A change the rules refuse (the last owner, someone already a member or not
one, a role they already have) is `409` with the refusal's slug.
"""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import MISSING
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from dd_app.routes.common import (
    Deps,
    RequestBody,
    ResponseBody,
    caused_by,
    in_project,
    parse_body,
    problem,
    project_deleted,
    project_refused,
    respond,
)
from dd_harness.project_access import Action
from dd_harness.projects import (
    MembershipRefusedError,
    ProjectDeletedError,
    ProjectError,
    UnknownProjectError,
)
from dd_sdk.contract.models import Principal

MEMBERS_REFUSED = "Data Director could not change the project's members"

type Role = Literal["owner", "member"]


class ProjectMember(ResponseBody):
    """One member of a project."""

    member_id: str
    """The identifier the member signs in with, such as their ORCID iD as a URL."""
    role: Role
    member_since: str
    """When they became a member: the project's creation, for its creator."""
    researcher_name: str | MISSING = MISSING
    """The name the member kept from their own ORCID record in this project; left out while they
    have kept none. The project keeps no other name for a member."""
    is_you: bool
    """Whether this member is the person asking."""
    removable: bool
    """Whether the person asking may remove this member (or leave, for themselves)."""
    role_changeable: bool
    """Whether the person asking may change this member's role: an owner, and not of the last
    owner."""


class ProjectMembers(ResponseBody):
    """A project's members, the creator first, and what the person asking may do."""

    members: list[ProjectMember]
    your_role: Role | None
    may_manage: bool
    """Whether the person asking may add members and change their roles: an owner."""
    may_leave: bool
    """Whether the person asking may leave: a member, or an owner who is not the last."""


class AddMember(RequestBody):
    refusal: ClassVar[str] = (
        "`member` is the person's ORCID iD, or the identifier they sign in with, and `role` is "
        "`owner` or `member`."
    )

    member: str
    role: Role = "member"


class ChangeRole(RequestBody):
    refusal: ClassVar[str] = "`member_id` names a member, and `role` is `owner` or `member`."

    member_id: str
    role: Role


def _refused(exc: ProjectError, project_id: str) -> Response:
    """`409` with the refusal's slug for a change the membership rules refuse; otherwise `404`
    for a project that is not there and `400` for a malformed identifier."""
    if isinstance(exc, MembershipRefusedError):
        return problem(409, exc.refusal.value, MEMBERS_REFUSED, exc.detail)
    if isinstance(exc, ProjectDeletedError):
        return project_deleted(project_id)
    return project_refused(exc, project_id, MEMBERS_REFUSED)


def routes(deps: Deps) -> list[Route]:
    path = "/api/projects/{project_id}/members"
    return [
        Route(path, in_project(deps, Action.READ, list_members), methods=["GET"]),
        Route(path, in_project(deps, Action.MANAGE, add_member), methods=["POST"]),
        Route(path, in_project(deps, Action.MANAGE, change_role), methods=["PATCH"]),
        Route(path, in_project(deps, Action.READ, remove_member), methods=["DELETE"]),
    ]


async def list_members(request: Request, person: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    found = await run_in_threadpool(deps.projects.members.members, project_id, person)
    return respond(ProjectMembers, found)


async def add_member(request: Request, person: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    body = await parse_body(request, AddMember, MEMBERS_REFUSED)
    if isinstance(body, Response):
        return body
    try:
        found = await run_in_threadpool(
            lambda: deps.projects.members.add(
                project_id, body.member, body.role, acted_for=person, caused_by=caused_by(request)
            )
        )
    except ProjectError as exc:
        return _refused(exc, project_id)
    return respond(ProjectMembers, found, status_code=201)


async def change_role(request: Request, person: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    body = await parse_body(request, ChangeRole, MEMBERS_REFUSED)
    if isinstance(body, Response):
        return body
    try:
        found = await run_in_threadpool(
            lambda: deps.projects.members.change_role(
                project_id,
                body.member_id,
                body.role,
                acted_for=person,
                caused_by=caused_by(request),
            )
        )
    except ProjectError as exc:
        return _refused(exc, project_id)
    return respond(ProjectMembers, found)


async def remove_member(request: Request, person: Principal, deps: Deps) -> Response:
    """An owner removes anyone; a member removes themselves, which is leaving."""
    project_id = request.path_params["project_id"]
    member_id = request.query_params.get("member_id", "").strip()
    if not member_id:
        return problem(400, "request-refused", MEMBERS_REFUSED, "`member_id` names the member.")
    members = deps.projects.members
    if not await run_in_threadpool(members.may_remove, project_id, person, member_id):
        return problem(
            403,
            "project-action-forbidden",
            "Not yours to do in this project",
            "Only an owner may remove another member; any member may leave.",
        )
    try:
        found = await run_in_threadpool(
            lambda: members.remove(
                project_id, member_id, acted_for=person, caused_by=caused_by(request)
            )
        )
    except UnknownProjectError:
        raise
    except ProjectError as exc:
        return _refused(exc, project_id)
    if found is None:
        return Response(status_code=204)
    return respond(ProjectMembers, found)
