"""A data steward in a researcher's project (docs/specs/stewardship.md, invariants 2, 3 and 6 to 8;
#374).

A steward reads a project through its usual `GET` routes while the profile lets them reach it,
and each read is recorded (`dd_app.routes.common.in_project`). `GET /api/projects/{id}` gives the
project with what the signed-in person may do there, as a member or as its steward, and why the
rest is refused (`permitted_actions`), so that the shell renders what the harness decides.
`GET /api/projects/{id}/stewarding` gives what stewards have done in it, to its members and its
stewards alike: the pause, decisions on referred runs, notes to the researcher, and who read it
when.

A steward acts through `/api/projects/{id}/steward/…`: a note to the researcher (`messages`), a
pause and its lifting (`pause`, `resume`), clearing or refusing a referred run
(`gates/{invocation_id}`), and a proposed version of a document
(`documents/{document_id}/versions`), which the project's owners approve or reject. Someone who
does not reach the project as its steward is answered `404`, as for a project that does not
exist; a member of the project, or a steward whose access does not open the action, `403`; an
action the project's state refuses, `409`, with the refusal's slug
(`dd_harness.projects.StewardRefusal`).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar, Literal

import pydantic
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from dd_app import contract_shapes as contract
from dd_app.routes.common import (
    Deps,
    Endpoint,
    Handler,
    RequestBody,
    ResponseBody,
    caused_by,
    in_project,
    no_project,
    parse_body,
    problem,
    project_refused,
    respond,
    signed_in,
)
from dd_app.routes.projects import ProjectDetails
from dd_harness.project_access import Action
from dd_harness.projects import (
    ChangeRefusedError,
    ProjectError,
    StewardRefusal,
    StewardRefusedError,
    UnknownProjectError,
)
from dd_harness.projects.stewarding import NOTE_MAX_LENGTH
from dd_harness.steward_storage import GateDecision, ProposedEdit
from dd_sdk.contract.models import Principal

STEWARD_REFUSED = "Data Director could not do this as the project's steward"
# Refusals of whom the steward is, not of the project's state.
_FORBIDDEN = frozenset({StewardRefusal.MEMBER_OF_PROJECT, StewardRefusal.NOT_PERMITTED})


class PermittedAction(ResponseBody):
    """One thing a person may ask to do in a project, and why not if they may not."""

    action: str
    permitted: bool
    refusal: str | pydantic.MISSING = pydantic.MISSING
    """Why it is refused, as a code; absent where it is permitted."""


class PermittedActions(ResponseBody):
    acting_as: Literal["member", "steward"]
    """Whether the person is in the project as a member or as its steward."""
    actions: list[PermittedAction]


class ProjectView(ProjectDetails):
    """One project, as `GET /api/projects/{id}` opens it for a member or a steward."""

    permitted_actions: PermittedActions


class StewardPause(ResponseBody):
    team_id: str
    reason: str
    by: contract.Principal
    at: str


class StewardGateDecision(ResponseBody):
    invocation_id: str
    verdict: Literal["cleared", "refused"]
    reason: str
    by: contract.Principal
    at: str


class StewardMessage(ResponseBody):
    note: str
    by: contract.Principal
    """The steward, shown as a named person, never as an agent."""
    at: str


class StewardView(ResponseBody):
    by: contract.Principal
    at: str


class ProjectStewarding(ResponseBody):
    """What data stewards have done in a project, which its members see too."""

    paused: StewardPause | None
    """The pause a steward team holds, which stops every run but an adviser's; null if none."""
    gate_decisions: list[StewardGateDecision]
    messages: list[StewardMessage]
    views: list[StewardView]
    """Each steward's reads, at most one a day for each."""


class ProposedVersion(ResponseBody):
    document_id: str
    version: int


class Note(RequestBody):
    """A steward's note, or the reason for a pause, lifting it, or a decision."""

    note: str = pydantic.Field(min_length=1, max_length=NOTE_MAX_LENGTH)
    refusal: ClassVar[str] = f"The body is {{'note'}}, at most {NOTE_MAX_LENGTH} characters."


class GateBody(RequestBody):
    verdict: Literal["cleared", "refused"]
    note: str = pydantic.Field(min_length=1, max_length=NOTE_MAX_LENGTH)
    refusal: ClassVar[str] = "The body is {'verdict': 'cleared' or 'refused', 'note'}."


class EditBody(RequestBody):
    version: int = pydantic.Field(ge=1)
    digest: str = pydantic.Field(pattern=r"^[0-9a-f]{64}$")
    text: str = pydantic.Field(min_length=1)
    refusal: ClassVar[str] = "The body is {'version', 'digest', 'text'} of the version edited."


def routes(deps: Deps) -> list[Route]:
    project = "/api/projects/{project_id}"
    steward = project + "/steward"
    return [
        Route(project, in_project(deps, Action.READ, open_project), methods=["GET"]),
        Route(project + "/stewarding", in_project(deps, Action.READ, stewarding), methods=["GET"]),
        Route(steward + "/messages", reached(deps, write_message), methods=["POST"]),
        Route(steward + "/pause", reached(deps, pause), methods=["POST"]),
        Route(steward + "/resume", reached(deps, resume), methods=["POST"]),
        Route(steward + "/gates/{invocation_id}", reached(deps, decide_gate), methods=["POST"]),
        Route(
            steward + "/documents/{document_id}/versions",
            reached(deps, propose_edit),
            methods=["POST"],
        ),
    ]


def reached(deps: Deps, handler: Handler) -> Endpoint:
    """`handler`, signed in, and run only for someone who reaches the project as a member or as
    its steward; anyone else is answered `404` before their body is read, as for a project that
    does not exist. Which steward actions they may take is the harness's check."""

    async def checked(request: Request, person: Principal, deps: Deps) -> Response:
        project_id = request.path_params["project_id"]
        if not await run_in_threadpool(deps.projects.stewarding.reaches, project_id, person):
            return no_project(project_id)
        return await handler(request, person, deps)

    return signed_in(deps, checked)


async def open_project(request: Request, person: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]

    def found() -> dict[str, Any]:
        summary = deps.projects.lifecycle.summary(project_id)
        permitted = deps.projects.stewarding.permitted_actions(project_id, person)
        return {**summary, "permitted_actions": permitted}

    return respond(ProjectView, await run_in_threadpool(found))


async def stewarding(request: Request, person: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    found = await run_in_threadpool(deps.projects.stewarding.of_project, project_id)
    return respond(ProjectStewarding, found)


async def _act(
    request: Request, project_id: str, action: Callable[[], Any], shape: type[ResponseBody]
) -> Response:
    try:
        found = await run_in_threadpool(action)
    except UnknownProjectError:
        return no_project(project_id)
    except StewardRefusedError as exc:
        status = 403 if exc.refusal in _FORBIDDEN else 409
        return problem(status, exc.refusal.value, STEWARD_REFUSED, exc.detail)
    except ChangeRefusedError as exc:
        return problem(409, exc.refusal.value, STEWARD_REFUSED, str(exc))
    except ProjectError as exc:
        return project_refused(exc, project_id, STEWARD_REFUSED)
    return respond(shape, found)


async def _noted(
    request: Request, person: Principal, deps: Deps, verb: Literal["message", "pause", "resume"]
) -> Response:
    project_id = request.path_params["project_id"]
    body = await parse_body(request, Note, STEWARD_REFUSED)
    if isinstance(body, Response):
        return body
    area = deps.projects.stewarding
    act = {"message": area.message, "pause": area.pause, "resume": area.resume}[verb]
    return await _act(
        request,
        project_id,
        lambda: act(project_id, body.note, acted_for=person, caused_by=caused_by(request)),
        ProjectStewarding,
    )


async def write_message(request: Request, person: Principal, deps: Deps) -> Response:
    return await _noted(request, person, deps, "message")


async def pause(request: Request, person: Principal, deps: Deps) -> Response:
    return await _noted(request, person, deps, "pause")


async def resume(request: Request, person: Principal, deps: Deps) -> Response:
    return await _noted(request, person, deps, "resume")


async def decide_gate(request: Request, person: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    body = await parse_body(request, GateBody, STEWARD_REFUSED)
    if isinstance(body, Response):
        return body
    decision = GateDecision(request.path_params["invocation_id"], body.verdict, body.note)
    return await _act(
        request,
        project_id,
        lambda: deps.projects.stewarding.decide_gate(
            project_id, decision, acted_for=person, caused_by=caused_by(request)
        ),
        ProjectStewarding,
    )


async def propose_edit(request: Request, person: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    body = await parse_body(request, EditBody, STEWARD_REFUSED)
    if isinstance(body, Response):
        return body
    edit = ProposedEdit(request.path_params["document_id"], body.version, body.digest, body.text)
    return await _act(
        request,
        project_id,
        lambda: deps.projects.stewarding.propose_edit(
            project_id, edit, acted_for=person, caused_by=caused_by(request)
        ),
        ProposedVersion,
    )
