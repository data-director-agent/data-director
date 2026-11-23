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

from functools import partial
from typing import ClassVar, Literal

from pydantic import MISSING, StrictInt
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
    parse_body,
    problem,
    project_refused,
    respond,
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


# How far a step has gone, as the project log shows it; a step left out is open.
type StepState = Literal["started", "done", "skipped"]
# Whether the intake still has a question to ask, has none left, or was dismissed.
type IntakeState = Literal["pending", "complete", "dismissed"]


class StepReason(ResponseBody):
    """What decided a step's state: the log's work (`produced`), the researcher's mark
    (`marked`), or an intake answer that skipped it (`intake`)."""

    state: StepState
    source: Literal["produced", "marked", "intake"]
    event: str
    """The kind of the deciding event."""
    at: str | MISSING = MISSING
    """When the deciding event was recorded, where the log says."""
    document_id: str | MISSING = MISSING
    """The document whose work decided a document step."""
    document_kind: str | MISSING = MISSING
    question_id: str | MISSING = MISSING
    """The intake question whose answer skipped the step."""


class Decision(ResponseBody):
    """One of the intake's decision points (Blueprint §8's diamonds) with its current answer."""

    question_id: str
    prompt: str
    before: str
    """The step the decision sits before."""
    asked: bool
    """Whether it is asked from the project's entry point."""
    answer_values: list[str] | None
    answer_labels: list[str] | None


class ProjectProgress(ResponseBody):
    """Where a project is in the process flow, derived from its log on every read
    (`dd_harness.progress.describe`): the entry point, each step started, done or skipped, and
    the step to suggest next, which is never a gate."""

    entry: int | None
    entry_source: Literal["researcher", "model"] | None
    """Who recorded the entry point: the researcher, or Data Director from what they said."""
    steps: dict[str, StepState]
    suggested: str | None
    passed_over: list[str]
    """The steps before `suggested` in its phase that it passed over because no agent the
    deployment enables serves them (#1377), in order; empty when none was."""
    reasons: dict[str, StepReason]
    """Why each step in `steps` is in its state, keyed the same."""
    decisions: list[Decision]


class IntakeQuestion(ResponseBody):
    """One intake question asked from the project's entry point, with its current answer."""

    question_id: str
    """The intake's stable id, `intake.<name>`, which an answer is posted to."""
    question: contract.Question
    """The question as the contract's `Question` has it."""
    answer_values: list[str] | None
    """The values of the latest answer, or null while it has none."""
    notices: dict[str, str] | MISSING = MISSING
    """What an answer says to the researcher at once, by answer value; only for those that do."""


class ProjectIntake(ResponseBody):
    """Where a project's intake stands (`dd_harness.intake.describe`): the next question, every
    question asked from the entry point with its answer, and the project's progress."""

    state: IntakeState
    next: str | None
    questions: list[IntakeQuestion]
    progress: ProjectProgress


def routes(deps: Deps) -> list[Route]:
    read = partial(in_project, deps, Action.READ)
    contribute = partial(in_project, deps, Action.CONTRIBUTE)

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
    return respond(
        ProjectProgress, await run_in_threadpool(deps.projects.progress.progress, project_id)
    )


async def choose_entry(request: Request, person: Principal, deps: Deps) -> Response:
    """The entry point the researcher chose. Answers with the progress derived anew."""
    project_id = request.path_params["project_id"]
    body = await parse_body(request, ChooseEntry, PROGRESS_REFUSED)
    if isinstance(body, Response):
        return body
    try:
        progress = await run_in_threadpool(
            lambda: deps.projects.progress.choose_entry(
                project_id, body.entry, acted_for=person, caused_by=caused_by(request)
            )
        )
    except ProjectError as exc:
        return project_refused(exc, project_id, PROGRESS_REFUSED)
    return respond(ProjectProgress, progress, status_code=201)


async def mark_step(request: Request, person: Principal, deps: Deps) -> Response:
    """A step the researcher marked done, skipped or open again. Answers with the progress
    derived anew."""
    project_id, step_id = request.path_params["project_id"], request.path_params["step_id"]
    body = await parse_body(request, MarkStep, PROGRESS_REFUSED)
    if isinstance(body, Response):
        return body
    try:
        progress = await run_in_threadpool(
            lambda: deps.projects.progress.mark_step(
                project_id, step_id, body.mark, acted_for=person, caused_by=caused_by(request)
            )
        )
    except ProjectError as exc:
        return project_refused(exc, project_id, PROGRESS_REFUSED)
    return respond(ProjectProgress, progress, status_code=201)


async def get_intake(request: Request, _: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    return respond(
        ProjectIntake, await run_in_threadpool(deps.projects.progress.intake, project_id)
    )


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
            lambda: deps.projects.progress.answer_intake(
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
    return respond(ProjectIntake, intake, status_code=201)


async def dismiss_intake(request: Request, person: Principal, deps: Deps) -> Response:
    """The researcher passing the intake by; an answer recorded later opens it again. Answers
    with where the intake then stands."""
    project_id = request.path_params["project_id"]
    intake = await run_in_threadpool(
        lambda: deps.projects.progress.dismiss_intake(
            project_id, acted_for=person, caused_by=caused_by(request)
        )
    )
    return respond(ProjectIntake, intake, status_code=201)
