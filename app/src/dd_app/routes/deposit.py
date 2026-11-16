"""A project's repository, its validation and deposit package, and its AI-use disclosure.

`GET /api/projects/{id}/repository` is the requirements of the repository the project chose last,
and `404` when none has been; `PUT` on it chooses one by its re3data identifier, which the pinned
re3data export resolves to the repository's name and declared standards, for the person signed in,
and answers with the requirements it resolved to and their warnings (docs/specs/deposit.md).
`GET /api/repositories?q=…` searches the pinned re3data export by name, re3data identifier,
re3data DOI or URL; without `q` it answers with the repositories the deployment suggests (its
overrides, then `suggested.yaml`), so a researcher can choose one on the project's page.
`POST /api/projects/{id}/validation` validates the project against the requirements recorded
for the repository chosen last and keeps the report; `POST /api/projects/{id}/package` does the
same and, only if the project is valid, builds the deposit package, answering `409` with the
validation when it is not; `GET /api/projects/{id}/packages/{digest}` is a package the project
log records as built, as a zip. `GET /api/projects/{id}/disclosure` says how each approved
document came about and what generative AI was used, as a statement and as a PROV-O graph
(docs/specs/disclosure.md).
"""

from __future__ import annotations

from typing import ClassVar

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from dd_app.project_service import PackageRefusedError, RepositoriesUnavailableError
from dd_app.routes.common import (
    Deps,
    Endpoint,
    Handler,
    RequestBody,
    in_project,
    parse_body,
    problem,
    project_refused,
    signed_in,
)
from dd_harness.project_access import Action
from dd_harness.projects import ProjectError
from dd_harness.requirements import RequirementsError
from dd_harness.sources import SourceConfigError
from dd_sdk.contract.models import Principal

REPOSITORY_REFUSED = "Data Director could not record this repository"


class ChooseRepository(RequestBody):
    """The repository, by its re3data identifier alone."""

    refusal: ClassVar[str] = "`re3data_id` is the repository's re3data identifier."

    re3data_id: str


def routes(deps: Deps) -> list[Route]:
    def read(handler: Handler) -> Endpoint:
        return in_project(deps, Action.READ, handler)

    def contribute(handler: Handler) -> Endpoint:
        return in_project(deps, Action.CONTRIBUTE, handler)

    project = "/api/projects/{project_id}"
    return [
        Route(f"{project}/disclosure", read(get_disclosure), methods=["GET"]),
        Route(f"{project}/repository", read(get_repository), methods=["GET"]),
        Route(f"{project}/repository", contribute(choose_repository), methods=["PUT"]),
        Route(f"{project}/validation", contribute(validate_project), methods=["POST"]),
        Route(f"{project}/package", contribute(package_project), methods=["POST"]),
        Route(f"{project}/packages/{{digest}}", read(get_package), methods=["GET"]),
        Route("/api/repositories", signed_in(deps, search_repositories), methods=["GET"]),
    ]


async def get_repository(request: Request, _: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    found = await run_in_threadpool(deps.projects.requirements, project_id)
    if found is None:
        return problem(
            404,
            "repository-not-chosen",
            "No repository chosen",
            f"Project {project_id!r} has not chosen one.",
        )
    return JSONResponse(found)


async def choose_repository(request: Request, person: Principal, deps: Deps) -> Response:
    """The researcher's choice of repository (`ProjectService.choose_repository`). Answers with
    the requirements it resolved to."""
    project_id = request.path_params["project_id"]
    if not deps.projects.offers_repositories:
        return _repositories_unavailable("This server has no repository requirement sets.")
    body = await parse_body(request, ChooseRepository, REPOSITORY_REFUSED)
    if isinstance(body, Response):
        return body
    try:
        chosen = await run_in_threadpool(
            lambda: deps.projects.choose_repository(
                project_id, body.re3data_id, acted_for=person, caused_by=f"PUT {request.url.path}"
            )
        )
    except RepositoriesUnavailableError as exc:
        return _repositories_unavailable(str(exc))
    except SourceConfigError as exc:
        return problem(503, "re3data-unavailable", REPOSITORY_REFUSED, str(exc))
    except ProjectError as exc:
        return project_refused(exc, project_id, REPOSITORY_REFUSED)
    except RequirementsError as exc:
        return problem(400, "request-refused", REPOSITORY_REFUSED, str(exc))
    return JSONResponse(chosen, status_code=201)


def _repositories_unavailable(detail: str) -> Response:
    return problem(503, "repositories-unavailable", REPOSITORY_REFUSED, detail)


async def search_repositories(request: Request, _: Principal, deps: Deps) -> Response:
    """Repositories a researcher may choose: those the pinned re3data export holds that `q`
    names, or, without `q`, those the deployment suggests (docs/specs/deposit.md)."""
    query = request.query_params.get("q", "").strip()
    try:
        return JSONResponse(await run_in_threadpool(deps.projects.search_repositories, query))
    except SourceConfigError as exc:
        return problem(503, "re3data-unavailable", "Repositories cannot be searched", str(exc))


async def validate_project(request: Request, acting_for: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    validation = await run_in_threadpool(
        lambda: deps.projects.validate(
            project_id, acted_for=acting_for, caused_by=f"POST {request.url.path}"
        )
    )
    return JSONResponse(validation, status_code=201)


async def package_project(request: Request, acting_for: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    try:
        built, validation = await run_in_threadpool(
            lambda: deps.projects.package(
                project_id, acted_for=acting_for, caused_by=f"POST {request.url.path}"
            )
        )
    except PackageRefusedError as exc:
        refused = await run_in_threadpool(deps.projects.validation_view, project_id, exc.validation)
        return problem(409, "package-refused", "No package was built", str(exc), validation=refused)
    return JSONResponse(
        {
            **validation,
            "package": {
                "digest": built.digest,
                "size": len(built.content),
                "href": f"{request.url.path.removesuffix('/package')}/packages/{built.digest}",
            },
        },
        status_code=201,
    )


async def get_package(request: Request, _: Principal, deps: Deps) -> Response:
    project_id, digest = request.path_params["project_id"], request.path_params["digest"]
    content = await run_in_threadpool(deps.projects.package_content, project_id, digest)
    if content is None:
        return problem(
            404,
            "package-not-found",
            "No such package",
            f"Project {project_id!r} has built no package {digest!r}.",
        )
    return Response(
        content,
        media_type="application/zip",
        headers={
            "content-disposition": f'attachment; filename="deposit-package-{digest[:12]}.zip"'
        },
    )


async def get_disclosure(request: Request, _: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    found = await run_in_threadpool(deps.projects.disclosure, project_id)
    return JSONResponse({**found.to_document(), "prov": found.prov_jsonld()})
