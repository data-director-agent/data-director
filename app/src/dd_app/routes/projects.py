"""Projects: listing, creating, naming, deleting and restoring them (docs/specs/projects.md).

`GET /api/projects` lists the projects the person signed in may read, the one created last first
and a page at a time, each with what it holds and the conversations started in it
(docs/specs/storage.md "Listing"); `POST /api/projects` creates one for the person signed in, with
no conversation, named by the optional `title` it is sent, and answers `201` with its summary as
the list shows it (docs/specs/app.md, rule 27). `PUT /api/projects/{id}/title` renames it.
`DELETE /api/projects/{id}` deletes a project for an owner who sends its name as `{"title": …}`
(its identifier while it has none), `400` otherwise; deleting removes nothing, and the summary it
answers with says until when the project may be restored. `POST /api/projects/{id}/restore`
restores it within that period, `409` after it or for a project not deleted, and
`GET /api/projects/deleted` lists the deleted projects the person may still restore, the one
deleted last first (invariants 22 to 25).
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import ConfigDict
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from dd_app.project_service import TitleMismatchError
from dd_app.routes.common import (
    Deps,
    RequestBody,
    caused_by,
    in_project,
    parse_body,
    problem,
    project_deleted,
    project_refused,
    refused,
    signed_in,
)
from dd_harness.project_access import Action
from dd_harness.projects import ProjectDeletedError, ProjectError, RestoreRefusedError
from dd_harness.transport.paging import PagingError, page_params, page_response
from dd_sdk.contract.models import Principal

TITLE_REFUSED = "Data Director could not rename this project"
DELETE_REFUSED = "Data Director could not delete this project"
RESTORE_REFUSED = "Data Director could not restore this project"
CREATE_REFUSED = "Data Director could not create this project"


class CreateProject(RequestBody):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    field_refusals: ClassVar[dict[str, str]] = {
        "title": "`title` is the project's name, or left out."
    }

    title: str | None = None


class RenameProject(RequestBody):
    refusal: ClassVar[str] = "`title` is the project's new name."

    title: str


class DeleteProject(RequestBody):
    """The project's name as the person typed it, to show they mean to delete it."""

    refusal: ClassVar[str] = "`title` is the project's name, as the person typed it."

    title: str


def routes(deps: Deps) -> list[Route]:
    return [
        Route("/api/projects", signed_in(deps, list_projects), methods=["GET"]),
        Route("/api/projects", signed_in(deps, create_project), methods=["POST"]),
        Route("/api/projects/deleted", signed_in(deps, list_deleted_projects), methods=["GET"]),
        Route(
            "/api/projects/{project_id}",
            in_project(deps, Action.MANAGE, delete_project),
            methods=["DELETE"],
        ),
        Route(
            "/api/projects/{project_id}/restore",
            in_project(deps, Action.MANAGE, restore_project),
            methods=["POST"],
        ),
        Route(
            "/api/projects/{project_id}/title",
            in_project(deps, Action.CONTRIBUTE, rename_project),
            methods=["PUT"],
        ),
    ]


async def list_projects(request: Request, reader: Principal, deps: Deps) -> Response:
    try:
        paging = page_params(request)
    except PagingError as exc:
        return refused(str(exc), "Data Director could not list the projects")
    page = await run_in_threadpool(lambda: deps.governance.projects_for(reader, **paging))
    return page_response(request, page)


async def list_deleted_projects(request: Request, owner: Principal, deps: Deps) -> Response:
    try:
        paging = page_params(request)
    except PagingError as exc:
        return refused(str(exc), "Data Director could not list the deleted projects")
    page = await run_in_threadpool(lambda: deps.governance.deleted_projects_for(owner, **paging))
    return page_response(request, page)


async def create_project(request: Request, person: Principal, deps: Deps) -> Response:
    """A project of its own, with no conversation (docs/specs/app.md, rule 27). Whom it is
    created for is whom the authenticator names, never the body."""
    if not deps.projects.keeps_projects:
        return problem(
            404, "project-not-found", "No such project", "This server keeps no projects."
        )
    body = await parse_body(request, CreateProject, CREATE_REFUSED)
    if isinstance(body, Response):
        return body
    try:
        created = await run_in_threadpool(
            lambda: deps.projects.create(body.title, acted_for=person)
        )
    except ProjectError as exc:
        return refused(str(exc), CREATE_REFUSED)
    return JSONResponse(created, status_code=201)


async def delete_project(request: Request, person: Principal, deps: Deps) -> Response:
    """Delete the project once the person has typed its name (`ProjectService.delete`)."""
    project_id = request.path_params["project_id"]
    body = await parse_body(request, DeleteProject, DELETE_REFUSED)
    if isinstance(body, Response):
        return body
    try:
        deleted = await run_in_threadpool(
            lambda: deps.projects.delete(
                project_id, body.title, acted_for=person, caused_by=caused_by(request)
            )
        )
    except ProjectDeletedError:
        return project_deleted(project_id)
    except TitleMismatchError as exc:
        return refused(str(exc), DELETE_REFUSED)
    return JSONResponse(deleted)


async def restore_project(request: Request, person: Principal, deps: Deps) -> Response:
    """Restore a deleted project within its restore period: it is then as it was
    (docs/specs/projects.md, invariant 25). Answers with the project's summary."""
    project_id = request.path_params["project_id"]
    try:
        restored = await run_in_threadpool(
            lambda: deps.projects.restore(
                project_id, acted_for=person, caused_by=caused_by(request)
            )
        )
    except RestoreRefusedError as exc:
        return problem(409, "project-restore-refused", RESTORE_REFUSED, str(exc))
    return JSONResponse(restored)


async def rename_project(request: Request, person: Principal, deps: Deps) -> Response:
    """A person's name for the project, which a model's never replaces. Answers with the
    project's summary."""
    project_id = request.path_params["project_id"]
    body = await parse_body(request, RenameProject, TITLE_REFUSED)
    if isinstance(body, Response):
        return body
    try:
        renamed = await run_in_threadpool(
            lambda: deps.projects.rename(
                project_id, body.title, acted_for=person, caused_by=caused_by(request)
            )
        )
    except ProjectError as exc:
        return project_refused(exc, project_id, TITLE_REFUSED)
    return JSONResponse(renamed)
