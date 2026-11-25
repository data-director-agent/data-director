"""The metadata standard a project's record is drafted and checked in (docs/specs/deposit.md,
invariant 5): the standard of the repository chosen last and why, the standards the deployment
has a requirement set for, and a person's choice of one."""

from __future__ import annotations

from typing import ClassVar

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from dd_app.project_service import RepositoriesUnavailableError
from dd_app.routes.common import (
    Deps,
    RequestBody,
    ResponseBody,
    in_project,
    parse_body,
    problem,
    respond,
)
from dd_app.routes.deposit import REPOSITORY_REFUSED, choice_refused, repositories_unavailable
from dd_app.routes.projects import ChosenStandard
from dd_harness.project_access import Action
from dd_harness.projects import ProjectError
from dd_harness.requirements import RequirementsError
from dd_harness.sources import SourceConfigError
from dd_sdk.contract.models import Principal


class ChooseStandard(RequestBody):
    """The metadata standard, by the `conforms_to` URI of a standard the deployment has a set
    for."""

    refusal: ClassVar[str] = "`conforms_to` names a standard the deployment has a set for."

    conforms_to: str


class MetadataStandard(ResponseBody):
    """A metadata standard the deployment has a requirement set for."""

    conforms_to: str
    title: str


class StandardChoice(ResponseBody):
    """The metadata standard a project's record is drafted and checked in, why it is that one,
    the standards the deployment has a set for, in its order of preference, and whether another
    may be chosen (docs/specs/deposit.md, invariant 5)."""

    standard: ChosenStandard | None
    standards: list[MetadataStandard]
    may_choose: bool
    """False when the deployment's settings for the repository name its standard."""


def routes(deps: Deps) -> list[Route]:
    project = "/api/projects/{project_id}"
    return [
        Route(
            f"{project}/repository/standard",
            in_project(deps, Action.CONTRIBUTE, choose_standard),
            methods=["PUT"],
        ),
        Route(
            f"{project}/repository/standard",
            in_project(deps, Action.READ, get_standard),
            methods=["GET"],
        ),
    ]


async def choose_standard(request: Request, person: Principal, deps: Deps) -> Response:
    """A person's choice of metadata standard for the repository chosen last
    (`Deposit.choose_standard`). Answers with the standard it resolved to, as `get_standard`
    does; the requirements it resolved to are read at `GET …/repository`."""
    project_id = request.path_params["project_id"]
    if not deps.projects.deposit.offers_repositories:
        return repositories_unavailable("This server has no repository requirement sets.")
    body = await parse_body(request, ChooseStandard, REPOSITORY_REFUSED)
    if isinstance(body, Response):
        return body
    if await run_in_threadpool(deps.projects.deposit.requirements, project_id) is None:
        return _not_chosen(project_id)
    try:
        await run_in_threadpool(
            lambda: deps.projects.deposit.choose_standard(
                project_id,
                body.conforms_to,
                acted_for=person,
                caused_by=f"PUT {request.url.path}",
            )
        )
    except (
        RepositoriesUnavailableError,
        SourceConfigError,
        ProjectError,
        RequirementsError,
    ) as exc:
        return choice_refused(exc, project_id)
    found = await run_in_threadpool(deps.projects.deposit.standard_choice, project_id)
    return respond(StandardChoice, found, status_code=201)


async def get_standard(request: Request, _: Principal, deps: Deps) -> Response:
    """The metadata standard of the repository chosen last, why, and what may be chosen."""
    project_id = request.path_params["project_id"]
    found = await run_in_threadpool(deps.projects.deposit.standard_choice, project_id)
    if found is None:
        return _not_chosen(project_id)
    return respond(StandardChoice, found)


def _not_chosen(project_id: str) -> Response:
    return problem(
        404,
        "repository-not-chosen",
        "No repository chosen",
        f"Project {project_id!r} has not chosen one, so it has no metadata standard.",
    )
