"""Escalation to a data steward (docs/specs/stewardship.md, invariants 4, 5 and 11; #373).

A member of a project reads its escalations, and where a new one would go
(`GET /api/projects/{id}/escalations`), opens one they confirmed (`POST …/escalations`, with
their note, the scope they were shown and, where the project has no support team and the
deployment several, the team they picked), and replies to, withdraws or re-opens one
(`POST …/escalations/{escalation_id}`, `{"move", "note"}`). An owner chooses the project's
support team (`PUT /api/projects/{id}/support-team`).

A steward reads the escalations routed to their teams (`GET /api/steward/escalations`, by default
those still open, taken or waiting, or `?state=` each state wanted) and takes, releases, asks
about, resolves or hands back one (`POST /api/steward/escalations/{project_id}/{escalation_id}`).
A steward opens the project through its own routes (`dd_app.routes.stewarding`), and reads its
escalations through `GET /api/projects/{id}/escalations`, recorded as a read. A project whose
escalation the steward may not move is answered `404`, as for anyone with no role in it.

Each escalation carries `permitted_moves`: the moves the reader may make on it, as the harness
decides (`dd_harness.escalation_api.permitted_moves`).

A person reads what data stewards have done in their projects lately
(`GET /api/notices`): each notice a kind, a subject, the page to look at and when, and never the
note itself (`dd_harness.notifications`, invariant 13).

A move or an escalation the rules refuse is `409` with the refusal's slug
(`dd_harness.projects.EscalationRefusal`). The shell renders what these answer and decides
nothing.
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import MISSING, Field
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from dd_app import contract_shapes as contract
from dd_app.routes.common import (
    Deps,
    RequestBody,
    ResponseBody,
    caused_by,
    in_project,
    no_project,
    parse_body,
    problem,
    project_deleted,
    project_refused,
    respond,
    signed_in,
)
from dd_harness.escalation_api import Confirmed, Requested
from dd_harness.project_access import Action
from dd_harness.projects import (
    EscalationRefusedError,
    ProjectDeletedError,
    ProjectError,
    UnknownProjectError,
)
from dd_harness.projects.escalations import NOTE_MAX_LENGTH, SCOPE_MAX_LINES
from dd_sdk.contract.models import Principal

ESCALATION_REFUSED = "Data Director could not send this to a data steward"
MOVE_REFUSED = "Data Director could not change the escalation"

type EscalationState = Literal[
    "open", "taken", "waiting_for_researcher", "resolved", "handed_back", "withdrawn"
]
type OriginKind = Literal["researcher", "policy_gate", "agent", "orchestrator"]
type MoveName = Literal[
    "open",
    "take",
    "release",
    "wait",
    "reply",
    "resolve",
    "hand_back",
    "withdraw",
    "reopen",
    "reassign",
    "transfer",
    "reroute",
]
type PermittedMoveName = Literal[
    "take",
    "release",
    "wait",
    "reply",
    "resolve",
    "hand_back",
    "withdraw",
    "reopen",
    "reassign",
    "transfer",
]


class EscalationOrigin(ResponseBody):
    """Where an escalation came from: the researcher, or a run of the project that ended in a
    referral or an abstention, or the orchestrator's offer."""

    kind: OriginKind
    invocation_id: str | MISSING = MISSING
    """The run it came from; absent for one the researcher raised."""
    agent_id: str | MISSING = MISSING


class EscalationMove(ResponseBody):
    """One move in an escalation's history, the opening first. `reroute` is the deployment
    sending it to its team again because nobody took it in time, which no person makes."""

    move: MoveName
    event_id: str
    """The project event that made the move."""
    by: contract.Principal
    at: str
    note: str | MISSING = MISSING
    acting_as: Literal["steward"] | MISSING = MISSING
    """Set for a move a steward made as a steward."""
    from_steward: contract.Principal | MISSING | None = MISSING
    """For `reassign`: the steward who had taken it."""
    to_steward: contract.Principal | MISSING = MISSING
    """For `reassign`: the colleague in the same team who takes it over."""
    from_team: str | MISSING = MISSING
    """For `transfer`: the team it was with."""
    team_id: str | MISSING = MISSING
    """For `transfer`: the team it was sent to."""
    team_name: str | MISSING = MISSING
    """For `transfer`: the name of the team it was sent to."""


class MoveTarget(ResponseBody):
    """A colleague or a team a move may pass the escalation to."""

    id: str
    """The colleague's principal identifier, or the team's id."""
    name: str


class PermittedMove(ResponseBody):
    """A move the reader may make on an escalation, or one refused with why."""

    move: PermittedMoveName
    permitted: bool
    note: Literal["required", "optional", "none"]
    """Whether the move carries a note: required, optional, or none."""
    targets: list[MoveTarget] | MISSING = MISSING
    """For `reassign`, the colleagues in the team it may go to; for `transfer`, the other teams.
    A move that names a target is listed only where there is one."""
    refusal: Literal["member-of-project"] | MISSING = MISSING
    """Why a move of the reader's side is refused."""


class Escalation(ResponseBody):
    """A matter handed to a data steward team (docs/specs/stewardship.md, invariant 4)."""

    escalation_id: str
    state: EscalationState
    team_id: str
    team_name: str
    origin: EscalationOrigin
    note: str
    """The researcher's note when they sent it."""
    scope_shared: list[str]
    """What the researcher was told would be shared, as they saw it when they confirmed it."""
    opened_by: contract.Principal
    opened_at: str
    updated_at: str
    routed_at: str
    """When its team was last asked to take it: opened, released, re-opened or sent again."""
    taken_by: contract.Principal | None
    history: list[EscalationMove]
    permitted_moves: list[PermittedMove]
    """The moves the reader may make on it now; empty for someone on neither side."""


class SupportTeamOption(ResponseBody):
    """A steward team the deployment names, which a project may choose as its support team."""

    team_id: str
    name: str
    supports: list[str]
    """The labels of the projects the team supports."""
    contact: str | MISSING = MISSING
    response_time: str | MISSING = MISSING


class ProjectEscalations(ResponseBody):
    """A project's escalations, the teams it may send to, and where a new one would go."""

    escalations: list[Escalation]
    teams: list[SupportTeamOption]
    support_team: str | None
    """The team the project's owners chose, or null."""
    routes_to: str | None
    """The team a new escalation would go to without a pick, or null with `unrouted` saying why."""
    unrouted: Literal["no-steward-team", "team-required"] | None


class QueuedEscalation(Escalation):
    """An escalation routed to one of the steward's teams, with its project."""

    project_id: str
    project_title: str | None
    member_of_project: bool
    """Whether the steward is a member of the project, and so may not act in it as its steward."""


class StewardQueue(ResponseBody):
    """The escalations routed to the signed-in steward's teams, the oldest first."""

    escalations: list[QueuedEscalation]


class Notice(ResponseBody):
    """Something a data steward did in one of the person's projects (docs/specs/stewardship.md,
    invariant 13): a subject and where to look, never research content."""

    kind: Literal["waiting", "resolved", "handed_back", "rerouted", "message"]
    project_id: str
    event_id: str
    """The project event it tells of, which the shell remembers as seen."""
    at: str
    subject: str
    path: str
    """The app's page to look at."""
    escalation_id: str | MISSING = MISSING


class Notices(ResponseBody):
    """What data stewards did in the person's projects in the last 30 days, the newest first."""

    notices: list[Notice]


class OpenOrigin(RequestBody):
    refusal: ClassVar[str] = "`origin.kind` is one of researcher, policy_gate, agent, orchestrator."

    kind: OriginKind
    invocation_id: str | None = None


class OpenEscalation(RequestBody):
    refusal: ClassVar[str] = (
        f"`note` says what the matter is (at most {NOTE_MAX_LENGTH} characters), `origin` where "
        f"it comes from, `scope_shared` the lines shown of what is shared (at most "
        f"{SCOPE_MAX_LINES}), and `team_id`, if given, the steward team picked."
    )

    note: str
    origin: OpenOrigin = Field(default_factory=lambda: OpenOrigin(kind="researcher"))
    scope_shared: list[str] = Field(default_factory=list)
    team_id: str | None = None


class MoveRequest(RequestBody):
    refusal: ClassVar[str] = (
        "`move` names a move, `note` is the note it carries, if any, and `to` the colleague's "
        "principal identifier or the team's id that `reassign` or `transfer` names."
    )

    move: str
    note: str | None = None
    to: str | None = None


class ChooseSupportTeam(RequestBody):
    refusal: ClassVar[str] = "`team_id` names one of the deployment's steward teams."

    team_id: str


def _refused(exc: ProjectError, project_id: str, title: str) -> Response:
    if isinstance(exc, EscalationRefusedError):
        return problem(409, exc.refusal.value, title, exc.detail)
    if isinstance(exc, ProjectDeletedError):
        return project_deleted(project_id)
    return project_refused(exc, project_id, title)


def routes(deps: Deps) -> list[Route]:
    path = "/api/projects/{project_id}/escalations"
    steward = "/api/steward/escalations"
    return [
        Route(path, in_project(deps, Action.READ, list_escalations), methods=["GET"]),
        Route(path, in_project(deps, Action.CONTRIBUTE, open_escalation), methods=["POST"]),
        Route(
            path + "/{escalation_id}",
            in_project(deps, Action.CONTRIBUTE, researcher_move),
            methods=["POST"],
        ),
        Route(
            "/api/projects/{project_id}/support-team",
            in_project(deps, Action.MANAGE, choose_support_team),
            methods=["PUT"],
        ),
        Route(steward, signed_in(deps, steward_queue), methods=["GET"]),
        Route("/api/notices", signed_in(deps, notices), methods=["GET"]),
        Route(
            steward + "/{project_id}/{escalation_id}",
            signed_in(deps, steward_move),
            methods=["POST"],
        ),
    ]


async def list_escalations(request: Request, person: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    found = await run_in_threadpool(
        lambda: deps.projects.escalations.of_project(project_id, person, deps.public_names.names)
    )
    return respond(ProjectEscalations, found)


async def open_escalation(request: Request, person: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    body = await parse_body(request, OpenEscalation, ESCALATION_REFUSED)
    if isinstance(body, Response):
        return body
    confirmed = Confirmed(
        origin=body.origin.model_dump(exclude_none=True),
        note=body.note,
        scope_shared=body.scope_shared,
        team_id=body.team_id,
    )
    try:
        found = await run_in_threadpool(
            lambda: deps.projects.escalations.open(
                project_id, confirmed, acted_for=person, caused_by=caused_by(request)
            )
        )
    except ProjectError as exc:
        return _refused(exc, project_id, ESCALATION_REFUSED)
    return respond(ProjectEscalations, found, status_code=201)


async def _move(request: Request, person: Principal, deps: Deps, *, as_steward: bool) -> Response:
    project_id = request.path_params["project_id"]
    body = await parse_body(request, MoveRequest, MOVE_REFUSED)
    if isinstance(body, Response):
        return body
    requested = Requested(
        request.path_params["escalation_id"], body.move, body.note, body.to, as_steward
    )
    try:
        moved: dict[str, Any] = await run_in_threadpool(
            lambda: deps.projects.escalations.move(
                project_id,
                requested,
                acted_for=person,
                caused_by=caused_by(request),
                names=deps.public_names.names,
            )
        )
    except UnknownProjectError:
        return no_project(project_id)
    except ProjectError as exc:
        return _refused(exc, project_id, MOVE_REFUSED)
    return respond(Escalation, moved)


async def researcher_move(request: Request, person: Principal, deps: Deps) -> Response:
    return await _move(request, person, deps, as_steward=False)


async def steward_move(request: Request, person: Principal, deps: Deps) -> Response:
    return await _move(request, person, deps, as_steward=True)


async def choose_support_team(request: Request, person: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    body = await parse_body(request, ChooseSupportTeam, ESCALATION_REFUSED)
    if isinstance(body, Response):
        return body
    try:
        found = await run_in_threadpool(
            lambda: deps.projects.escalations.choose_support_team(
                project_id, body.team_id, acted_for=person, caused_by=caused_by(request)
            )
        )
    except ProjectError as exc:
        return _refused(exc, project_id, ESCALATION_REFUSED)
    return respond(ProjectEscalations, found)


async def steward_queue(request: Request, person: Principal, deps: Deps) -> Response:
    states = request.query_params.getlist("state")
    found = await run_in_threadpool(
        lambda: deps.projects.escalations.queue(person, states, deps.public_names.names)
    )
    return respond(StewardQueue, {"escalations": found})


async def notices(request: Request, person: Principal, deps: Deps) -> Response:
    found = await run_in_threadpool(lambda: deps.projects.escalations.notices(person))
    return respond(Notices, {"notices": found})
