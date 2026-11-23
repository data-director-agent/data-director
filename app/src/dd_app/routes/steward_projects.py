"""A data steward's list of the projects they may see (docs/specs/stewardship.md, invariant 3;
#232).

`GET /api/steward/projects` (`?limit`, `?before`) lists, the one created last first, the
projects the harness lets the signed-in steward see (`dd_harness.steward_projects`): by default
those with a matter escalated to, or a pause held by, one of their teams, and where the profile
sets `visibility: scope`, also those whose owners chose one of their teams. Each project listed is
recorded as read by the steward, as opening it is, and the researcher sees it. Someone in no
team is answered an empty list, as the queue answers them.

Each row is the project's summary with what a steward needs beside it: its owners, the teams the
steward reaches it through, its live escalations and pause, its latest runs and their outcomes,
what awaits a person's review, and what the steward may do there (`permitted_actions`). The
shell renders it and decides nothing.
"""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from dd_app.routes.common import (
    Deps,
    ResponseBody,
    caused_by,
    listed,
    refused,
    respond_page,
    signed_in,
)
from dd_app.routes.escalations import EscalationState
from dd_app.routes.projects import PermittedActions, ProjectDetails
from dd_app.routes.runs import RunRow
from dd_app.routes.stewarding import StewardPause
from dd_harness.transport.paging import PagingError, page_params
from dd_sdk.contract.models import Principal

LIST_REFUSED = "Data Director could not list the projects you support"


class StewardTeamRef(ResponseBody):
    team_id: str
    name: str


class StewardReach(ResponseBody):
    """How the steward reaches the project."""

    teams: list[StewardTeamRef]
    """The steward's teams the project is escalated to, paused by or supported by."""
    escalated: bool
    """Whether a matter is escalated to one of those teams, which opens a steward's actions."""
    holds_pause: bool
    """Whether one of those teams holds the project's pause."""


class LiveEscalation(ResponseBody):
    escalation_id: str
    state: EscalationState
    team_id: str
    opened_at: str


class AwaitingReview(ResponseBody):
    """What in the project waits for a person to decide."""

    proposed_versions: int
    """Documents whose latest version waits for an owner's approval."""
    fact_proposals: int
    """Facts an agent proposed that no one has yet decided."""
    referred_runs: list[str]
    """The runs the policy gate referred to a steward that no steward has cleared or refused."""


class StewardProject(ProjectDetails):
    """One project the signed-in steward may see, as `GET /api/steward/projects` lists it."""

    owners: list[str]
    """The identifier each owner signs in with, such as their ORCID iD as a URL."""
    access: StewardReach
    escalations: list[LiveEscalation]
    """The matters escalated to the steward's teams that are still open, taken or waiting."""
    paused: StewardPause | None
    recent_runs: list[RunRow]
    """The project's latest runs, newest first, with their outcomes."""
    awaiting_review: AwaitingReview
    permitted_actions: PermittedActions


def routes(deps: Deps) -> list[Route]:
    return [Route("/api/steward/projects", signed_in(deps, list_projects), methods=["GET"])]


async def list_projects(request: Request, steward: Principal, deps: Deps) -> Response:
    try:
        paging = page_params(request)
    except PagingError as exc:
        return refused(str(exc), LIST_REFUSED)
    cause = caused_by(request)
    page = await listed(
        deps,
        lambda: deps.projects.stewarding.projects(steward, **paging, caused_by=cause),
        LIST_REFUSED,
    )
    if isinstance(page, Response):
        return page
    return await run_in_threadpool(respond_page, request, page, StewardProject)
