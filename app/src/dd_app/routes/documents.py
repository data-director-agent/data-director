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

from typing import Literal

from pydantic import MISSING
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from dd_app import contract_shapes as contract
from dd_app import documents
from dd_app.routes.common import (
    Deps,
    ResponseBody,
    caused_by,
    in_project,
    problem,
    project_refused,
    read_json,
    refused,
    respond,
)
from dd_harness.project_access import Action
from dd_harness.projects import ChangeRefusedError, ProjectError, Refusal
from dd_sdk.contract.models import Principal

DECISION_REFUSED = "Data Director could not record this decision"
ANSWERS_REFUSED = "Data Director could not record these answers"


class DocumentDraftedBy(ResponseBody):
    """The run that drafted a version."""

    agent_id: str
    agent_version: str
    invocation_id: str
    document_derivation: str
    """How the drafter made the text, such as `model` or `template`."""


class VersionDecision(ResponseBody):
    """A person's decision on a version."""

    reason: str | None
    decided_by: contract.Principal
    decided_at: str


class DocumentVersion(ResponseBody):
    """One version of a project document, with its text and its state."""

    document_id: str
    document_kind: str
    version: int
    digest: str
    """The SHA-256 of the text as UTF-8, which a decision names as the text shown."""
    media_type: str
    document_title: str | None
    conforms_to: str | None
    revises: contract.DocumentVersionRef | None
    drafted_by: DocumentDraftedBy | None
    """The run that drafted it; null for a person's edit."""
    questions: list[contract.DocumentQuestion]
    """What the version asks the researcher, one question per gap."""
    added_by: contract.Principal
    added_at: str
    state: Literal["proposed", "approved", "rejected"]
    decision: VersionDecision | None
    text: str


class RecordedAnswer(ResponseBody):
    """A person's answer to one question, as the project log records it: the latest stands."""

    question_id: str
    answer_text: str
    version: int
    """The version whose question it answered."""
    answered_by: contract.Principal
    answered_at: str


class ProjectDocument(ResponseBody):
    """One of a project's documents, with every version oldest first."""

    document_id: str
    document_kind: str
    document_title: str | None
    versions: list[DocumentVersion]
    answers: list[RecordedAnswer]
    """The answers given to its questions, which the next draft places as supplied."""


class ReasonRequired(ResponseBody):
    """Whether each kind of decision needs a reason."""

    approved: bool
    edited_and_approved: bool
    rejected: bool


class ReviewRules(ResponseBody):
    """The harness's rule for when a decision needs a reason, which the form states."""

    reason_required: ReasonRequired
    reason_max_length: int


class ProjectDocuments(ResponseBody):
    """A project's documents and the rules a decision or answer form states."""

    project_id: str
    documents: list[ProjectDocument]
    review: ReviewRules
    answer_max_length: int
    """The longest answer the harness keeps, in characters."""
    decided: contract.DocumentVersionRef | MISSING = MISSING
    """After a decision: the version it decided."""
    answered: contract.DocumentVersionRef | MISSING = MISSING
    """After answers: the version whose questions they answered."""


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
    return respond(ProjectDocuments, await run_in_threadpool(deps.projects.documents, project_id))


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
    return respond(ProjectDocuments, decided, status_code=201)


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
    return respond(ProjectDocuments, answered, status_code=201)


def _change_refused(exc: ProjectError, project_id: str, title: str) -> Response:
    """`404` for a document that is not there, `409` for one that has moved on, and `400` for
    a decision or answers the project refuses."""
    if isinstance(exc, ChangeRefusedError):
        if exc.refusal is Refusal.NO_DOCUMENT:
            return problem(404, exc.refusal.value, "No such document", exc.detail)
        return problem(409, exc.refusal.value, "The document has moved on", exc.detail)
    return project_refused(exc, project_id, title)
