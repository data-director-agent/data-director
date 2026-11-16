"""Where a project is (docs/specs/orchestration.md) and its intake (docs/specs/app.md, rule 25).

`GET /api/projects/{id}/progress` is the project's progress; `PUT …/progress/entry` records the
entry point the researcher chose and `PUT …/progress/steps/{step_id}` a step they marked done,
skipped or open again. `GET /api/projects/{id}/intake` says whether the project's intake is
pending, complete or dismissed, with its next question and each question asked from the project's
entry point and its current answer; `POST /api/projects/{id}/intake/{question_id}` records the
person's answer to one (`{"answer_values": […]}`), refused with `400` when malformed and `409` when
the harness rejects it, and `POST /api/projects/{id}/intake/dismiss` passes the intake by; both
answer with the intake read anew. Whom each acts for is whom the authenticator names, never the
body.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import StrictInt
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from dd_app.routes.common import (
    Deps,
    Endpoint,
    Handler,
    RequestBody,
    caused_by,
    in_project,
    parse_body,
    problem,
    project_refused,
)
from dd_harness.project_access import Action
from dd_harness.projects import ProjectError, UnknownProjectError
from dd_sdk.contract.models import Principal

PROGRESS_REFUSED = "Data Director could not record where the project is"
INTAKE_REFUSED = "Data Director could not record this answer"


class ChooseEntry(RequestBody):
    refusal: ClassVar[str] = "The body is not a JSON object."
    field_refusals: ClassVar[dict[str, str]] = {
        "entry": "`entry` is the entry point's number, 1, 2 or 3."
    }

    entry: StrictInt


class MarkStep(RequestBody):
    refusal: ClassVar[str] = "The body is not a JSON object."
    field_refusals: ClassVar[dict[str, str]] = {"mark": "`mark` is one of done, skipped or open."}

    mark: str


class IntakeAnswer(RequestBody):
    refusal: ClassVar[str] = (
        "The body is an object whose `answer_values` is a list of option values."
    )

    answer_values: list[str]


def routes(deps: Deps) -> list[Route]:
    def read(handler: Handler) -> Endpoint:
        return in_project(deps, Action.READ, handler)

    def contribute(handler: Handler) -> Endpoint:
        return in_project(deps, Action.CONTRIBUTE, handler)

    project = "/api/projects/{project_id}"
    return [
        Route(f"{project}/progress", read(get_progress), methods=["GET"]),
        Route(f"{project}/progress/entry", contribute(choose_entry), methods=["PUT"]),
        Route(f"{project}/progress/steps/{{step_id}}", contribute(mark_step), methods=["PUT"]),
        Route(f"{project}/intake", read(get_intake), methods=["GET"]),
        # Before the route below, which would read `dismiss` as a question.
        Route(f"{project}/intake/dismiss", contribute(dismiss_intake), methods=["POST"]),
        Route(f"{project}/intake/{{question_id}}", contribute(answer_intake), methods=["POST"]),
    ]


async def get_progress(request: Request, _: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    return JSONResponse(await run_in_threadpool(deps.projects.progress, project_id))


async def choose_entry(request: Request, person: Principal, deps: Deps) -> Response:
    """The entry point the researcher chose. Answers with the progress derived anew."""
    project_id = request.path_params["project_id"]
    body = await parse_body(request, ChooseEntry, PROGRESS_REFUSED)
    if isinstance(body, Response):
        return body
    try:
        progress = await run_in_threadpool(
            lambda: deps.projects.choose_entry(
                project_id, body.entry, acted_for=person, caused_by=caused_by(request)
            )
        )
    except ProjectError as exc:
        return project_refused(exc, project_id, PROGRESS_REFUSED)
    return JSONResponse(progress, status_code=201)


async def mark_step(request: Request, person: Principal, deps: Deps) -> Response:
    """A step the researcher marked done, skipped or open again. Answers with the progress
    derived anew."""
    project_id, step_id = request.path_params["project_id"], request.path_params["step_id"]
    body = await parse_body(request, MarkStep, PROGRESS_REFUSED)
    if isinstance(body, Response):
        return body
    try:
        progress = await run_in_threadpool(
            lambda: deps.projects.mark_step(
                project_id, step_id, body.mark, acted_for=person, caused_by=caused_by(request)
            )
        )
    except ProjectError as exc:
        return project_refused(exc, project_id, PROGRESS_REFUSED)
    return JSONResponse(progress, status_code=201)


async def get_intake(request: Request, _: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    return JSONResponse(await run_in_threadpool(deps.projects.intake, project_id))


async def answer_intake(request: Request, person: Principal, deps: Deps) -> Response:
    """The researcher's answer to one intake question. An answer the harness rejects is refused
    with `409`, recording nothing; otherwise the server answers with where the intake then
    stands: the next question, or the progress the card names once it is complete."""
    project_id = request.path_params["project_id"]
    question_id = request.path_params["question_id"]
    body = await parse_body(request, IntakeAnswer, INTAKE_REFUSED)
    if isinstance(body, Response):
        return body
    try:
        intake = await run_in_threadpool(
            lambda: deps.projects.answer_intake(
                project_id,
                question_id,
                body.answer_values,
                acted_for=person,
                caused_by=caused_by(request),
            )
        )
    except UnknownProjectError:
        raise
    except ProjectError as exc:
        return problem(409, "intake-answer-refused", INTAKE_REFUSED, str(exc))
    return JSONResponse(intake, status_code=201)


async def dismiss_intake(request: Request, person: Principal, deps: Deps) -> Response:
    """The researcher passing the intake by; an answer recorded later opens it again. Answers
    with where the intake then stands."""
    project_id = request.path_params["project_id"]
    intake = await run_in_threadpool(
        lambda: deps.projects.dismiss_intake(
            project_id, acted_for=person, caused_by=caused_by(request)
        )
    )
    return JSONResponse(intake, status_code=201)
