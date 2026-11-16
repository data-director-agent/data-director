"""A project's documents, and a person's decisions on them and answers to their questions.

`GET /api/projects/{id}/documents` reads a project's documents, each version's state and the
rule for when a decision needs a reason; `POST /api/projects/{id}/documents/{document_id}/decisions`
approves or rejects the latest version, or approves an edit of it, for the person signed in, and
answers `409` if that version is no longer the latest or undecided (docs/specs/projects.md);
`POST /api/projects/{id}/documents/{document_id}/answers` records the person's answers to questions
the latest version asks, for the next draft to place as supplied, and answers `409` if that
version is no longer the latest or does not ask them (docs/specs/drafting.md). Who decided or
answered is whom the authenticator names, never the body.
"""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from dd_app import documents
from dd_app.routes.common import (
    Deps,
    caused_by,
    in_project,
    problem,
    project_refused,
    read_json,
    refused,
)
from dd_harness.project_access import Action
from dd_harness.projects import ChangeRefusedError, ProjectError, Refusal
from dd_sdk.contract.models import Principal

DECISION_REFUSED = "Data Director could not record this decision"
ANSWERS_REFUSED = "Data Director could not record these answers"


def routes(deps: Deps) -> list[Route]:
    document = "/api/projects/{project_id}/documents"
    return [
        Route(document, in_project(deps, Action.READ, get_documents), methods=["GET"]),
        Route(
            f"{document}/{{document_id}}/decisions",
            in_project(deps, Action.DECIDE, decide),
            methods=["POST"],
        ),
        Route(
            f"{document}/{{document_id}}/answers",
            in_project(deps, Action.CONTRIBUTE, answer),
            methods=["POST"],
        ),
    ]


async def get_documents(request: Request, _: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    return JSONResponse(await run_in_threadpool(deps.projects.documents, project_id))


async def decide(request: Request, decider: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    body = await read_json(request, DECISION_REFUSED)
    if isinstance(body, Response):
        return body
    try:
        decision = documents.parse_decision(request.path_params["document_id"], body)
    except documents.DecisionRequestError as exc:
        return refused(str(exc), DECISION_REFUSED)
    try:
        decided = await run_in_threadpool(
            lambda: deps.projects.decide(
                project_id, decision, acted_for=decider, caused_by=caused_by(request)
            )
        )
    except ProjectError as exc:
        return _change_refused(exc, project_id, DECISION_REFUSED)
    return JSONResponse(decided, status_code=201)


async def answer(request: Request, answerer: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    document_id = request.path_params["document_id"]
    body = await read_json(request, ANSWERS_REFUSED)
    if isinstance(body, Response):
        return body
    try:
        version, answers = documents.parse_answers(document_id, body)
    except documents.DecisionRequestError as exc:
        return refused(str(exc), ANSWERS_REFUSED)
    try:
        answered = await run_in_threadpool(
            lambda: deps.projects.answer(
                project_id,
                document_id,
                version,
                answers,
                acted_for=answerer,
                caused_by=caused_by(request),
            )
        )
    except ProjectError as exc:
        return _change_refused(exc, project_id, ANSWERS_REFUSED)
    return JSONResponse(answered, status_code=201)


def _change_refused(exc: ProjectError, project_id: str, title: str) -> Response:
    """`404` for a document that is not there, `409` for one that has moved on, and `400` for
    a decision or answers the project refuses."""
    if isinstance(exc, ChangeRefusedError):
        if exc.refusal is Refusal.NO_DOCUMENT:
            return problem(404, exc.refusal.value, "No such document", exc.detail)
        return problem(409, exc.refusal.value, "The document has moved on", exc.detail)
    return project_refused(exc, project_id, title)
