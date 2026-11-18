"""Conversations and their turns (docs/specs/orchestration.md, docs/specs/app.md).

`POST /api/conversations` starts a conversation, in the project it names or else a new one, and
`POST /api/conversations/{id}/turns` sends it one message, which may attach a `dd-inventory` file
and a supporting document's text for the project to keep, answered as a run is, or refused with
`409` unless it follows the latest turn. `POST /api/conversations/{id}/turns/stream` sends the same
turn as an AG-UI `RunAgentInput` and streams its run as it is made, and
`POST /api/conversations/{id}/turns/{run_id}/cancel` cancels it while its stream is open
(docs/specs/app.md, "Run events to the browser"). `GET /api/conversations` and
`GET /api/conversations/{id}` read them back as the harness derives them from the run store (#130).
Each person sees only their own conversations (#153); someone else's is answered with 404, as one
that does not exist.
"""

from __future__ import annotations

import logging
import time
from typing import Any, ClassVar, Self

from pydantic import ConfigDict, Field, model_validator
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from dd_app.documentation_check import DocumentationHeldError
from dd_app.governance import Governance, TurnConflictError, UnknownConversationError
from dd_app.routes.common import (
    RUN_REFUSED,
    Deps,
    RequestBody,
    no_conversation,
    no_project,
    parse_body,
    problem,
    project_deleted,
    refused,
    signed_in,
)
from dd_app.routes.runs import REFUSED_BEFORE_RUN
from dd_app.turn_body import DOCUMENTATION_REFUSAL, AttachedDocument, Turn, decoded
from dd_app.turn_stream import TurnStreams
from dd_harness.projects import ProjectDeletedError, UnknownProjectError
from dd_harness.transport.paging import PagingError, page_params, page_response
from dd_sdk.contract.models import Principal, ReplyAnswers

log = logging.getLogger(__name__)

_FORBIDS_EXTRA = ConfigDict(strict=True, extra="forbid", frozen=True)


class StartConversation(RequestBody):
    """`POST /api/conversations`: no body starts it in a new project; `{"project_id": …}` in
    that one."""

    model_config = _FORBIDS_EXTRA
    refusal: ClassVar[str] = "The body must be an object, with at most `project_id`."
    field_refusals: ClassVar[dict[str, str]] = {
        "project_id": "`project_id` must be a string, or null for a new project."
    }
    extra_refusal: ClassVar[str] = "A conversation takes only `project_id`, not {extra}."

    project_id: str | None = None


class AttachedDocumentBody(RequestBody):
    """A supporting document a turn attaches: its text, or for a Word document or PDF the file
    as base64 `data`, whose text the server reads."""

    model_config = _FORBIDS_EXTRA

    name: str
    media_type: str
    text: str | None = None
    data: str | None = None
    # The kinds of possible personal data or secrets the researcher confirmed it holds (#473).
    confirmed: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _text_or_file(self) -> Self:
        unreadable = self.data is not None and decoded(self.data) is None
        if (self.text is None) == (self.data is None) or unreadable:
            raise ValueError(DOCUMENTATION_REFUSAL)
        return self


class SendTurn(RequestBody):
    """`POST /api/conversations/{id}/turns`: one message, and what it attaches or answers. The
    turn names the turn it follows; the server, not the caller, builds the history."""

    model_config = _FORBIDS_EXTRA
    refusal: ClassVar[str] = (
        "The body must be an object with `agent_id`, `message_text` and `follows`."
    )
    field_refusals: ClassVar[dict[str, str]] = {
        **dict.fromkeys(
            ("agent_id", "message_text"),
            "The body must name `agent_id` and give `message_text`, as strings.",
        ),
        "follows": "The body must give `follows`: the `invocation_id` of the turn this one "
        "follows, or null for the first turn.",
        "inventory": "`inventory` must be the object `dd-inventory` wrote.",
        "documentation": DOCUMENTATION_REFUSAL,
        "reply_answers": "`reply_answers` must name the turn it answers (`answer_to`) and give "
        "`given_answers`: for each question answered, its `answered_key`, the `answer_values` "
        "chosen and optionally `answer_words`.",
    }
    extra_refusal: ClassVar[str] = (
        "A turn takes only `agent_id`, `message_text`, `follows`, `inventory`, "
        "`documentation` and `reply_answers`, not {extra}."
    )

    agent_id: str
    message_text: str
    # Required, and null only for the first turn.
    follows: str | None
    inventory: dict[str, Any] | None = None
    documentation: AttachedDocumentBody | None = None
    reply_answers: ReplyAnswers | None = None

    @model_validator(mode="before")
    @classmethod
    def _no_history(cls, data: Any) -> Any:
        if isinstance(data, dict) and "history" in data:
            raise ValueError(
                "A turn may not give a history: the server builds it from the stored turns."
            )
        return data

    @model_validator(mode="after")
    def _says_something(self) -> Self:
        if not self.message_text.strip() and self.inventory is None and self.documentation is None:
            raise ValueError("The message is empty.")
        return self

    def attached(self) -> AttachedDocument | None:
        d = self.documentation
        if d is None:
            return None
        data = None if d.data is None else decoded(d.data)
        return AttachedDocument(d.name, d.media_type, d.text or "", data, tuple(d.confirmed))

    def turn(self) -> Turn:
        return Turn(
            self.agent_id,
            self.message_text,
            self.follows,
            self.inventory,
            self.reply_answers,
            self.attached(),
        )


def routes(deps: Deps) -> list[Route]:
    streams = TurnStreams(deps.governance)
    return [
        Route("/api/conversations", signed_in(deps, start_conversation), methods=["POST"]),
        Route("/api/conversations", signed_in(deps, list_conversations), methods=["GET"]),
        Route(
            "/api/conversations/{conversation_id}",
            signed_in(deps, get_conversation),
            methods=["GET"],
        ),
        Route(
            "/api/conversations/{conversation_id}/turns",
            signed_in(deps, send_turn),
            methods=["POST"],
        ),
        Route(
            "/api/conversations/{conversation_id}/turns/stream",
            signed_in(deps, lambda request, principal, _deps: streams.stream(request, principal)),
            methods=["POST"],
        ),
        Route(
            "/api/conversations/{conversation_id}/turns/{run_id}/cancel",
            signed_in(deps, lambda request, principal, _deps: streams.cancel(request, principal)),
            methods=["POST"],
        ),
    ]


async def start_conversation(request: Request, acting_for: Principal, deps: Deps) -> Response:
    body = await parse_body(request, StartConversation, RUN_REFUSED, empty=True)
    if isinstance(body, Response):
        return body
    governance, project_id = deps.governance, body.project_id
    try:
        conversation_id = await run_in_threadpool(
            governance.start_conversation, acting_for, project_id
        )
    except UnknownProjectError:
        return no_project(str(project_id))
    except ProjectDeletedError:
        return project_deleted(str(project_id))
    found = governance.conversation(conversation_id, acting_for) or {}
    return JSONResponse(
        {"conversation_id": conversation_id, "project_id": found.get("project_id")},
        status_code=201,
        headers={"Location": f"/api/conversations/{conversation_id}"},
    )


async def send_turn(request: Request, acting_for: Principal, deps: Deps) -> Response:
    conversation_id = request.path_params["conversation_id"]
    body = await parse_body(request, SendTurn, RUN_REFUSED)
    if isinstance(body, Response):
        return body
    governance = deps.governance
    if await run_in_threadpool(governance.conversation, conversation_id, acting_for) is None:
        return no_conversation(conversation_id)
    started = time.monotonic()
    outcome = "failed or dropped"
    try:
        response, outcome = await _take_turn(governance, conversation_id, body, acting_for)
        return response
    finally:
        log.info(
            "data-director: turn %s %s in %.1f s",
            conversation_id,
            outcome,
            time.monotonic() - started,
        )


async def _take_turn(
    governance: Governance, conversation_id: str, body: SendTurn, acting_for: Principal
) -> tuple[Response, str]:
    """The answer to one turn sent as JSON, and the outcome to log: answered, or refused for
    why. Anything else, raised, has failed or been dropped."""
    try:
        envelope = await governance.turn(conversation_id, body.turn(), acting_for)
        checks = governance.checks(envelope.invocation_id)
        return JSONResponse({"envelope": envelope.to_document(), "checks": checks}), "answered"
    except UnknownConversationError:
        return no_conversation(conversation_id), "unknown conversation"
    except TurnConflictError as exc:
        conflict = problem(409, "turn-conflict", "The conversation has moved on", exc.detail)
        return conflict, "conflict"
    except ProjectDeletedError as exc:
        deleted = problem(409, "project-deleted", "This project is deleted", str(exc))
        return deleted, "project deleted"
    except DocumentationHeldError as exc:
        title = "This document needs your confirmation"
        return problem(409, "documentation-held", title, str(exc), kinds=exc.kinds), "held"
    # A `ProjectError` (an inventory or document the project refuses) is a `ValueError`.
    except REFUSED_BEFORE_RUN as exc:
        return refused(str(exc)), "refused"


async def list_conversations(request: Request, reader: Principal, deps: Deps) -> Response:
    try:
        paging = page_params(request)
    except PagingError as exc:
        return refused(str(exc), "Data Director could not list the conversations")
    page = await run_in_threadpool(lambda: deps.governance.conversations(reader, **paging))
    return page_response(request, page)


async def get_conversation(request: Request, reader: Principal, deps: Deps) -> Response:
    conversation_id = request.path_params["conversation_id"]
    found = await run_in_threadpool(deps.governance.conversation, conversation_id, reader)
    if found is None:
        return no_conversation(conversation_id)
    return JSONResponse(found)
