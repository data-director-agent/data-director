"""Conversations and their turns (docs/specs/orchestration.md, docs/specs/app.md).

`POST /api/conversations` starts a conversation, in the project it names or else a new one, and
`POST /api/conversations/{id}/turns` sends it one message, which may attach a `dd-inventory` file
and a supporting document's text for the project to keep, answered as a run is, or refused with
`409` unless it follows the latest turn. `GET /api/conversations` and `GET /api/conversations/{id}`
read them back as the harness derives them from the run store (#130). Each person sees only their
own conversations (#153); someone else's is answered with 404, as one that does not exist.
"""

from __future__ import annotations

import logging
import time
from typing import Any, ClassVar, Self

from pydantic import ConfigDict, model_validator
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from dd_app.governance import AttachedDocument, TurnConflictError, UnknownConversationError
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
    """A supporting document a turn attaches, its text with it."""

    model_config = _FORBIDS_EXTRA

    name: str
    media_type: str
    text: str


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
        "documentation": "`documentation` must be an object giving the document's `name`, "
        "`media_type` and `text`, as strings.",
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
        return None if d is None else AttachedDocument(d.name, d.media_type, d.text)


def routes(deps: Deps) -> list[Route]:
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
    outcome = "answered"
    try:
        return JSONResponse(
            await governance.turn(
                conversation_id,
                body.agent_id,
                body.message_text,
                body.follows,
                acting_for,
                body.inventory,
                body.reply_answers,
                body.attached(),
            )
        )
    except UnknownConversationError:
        outcome = "unknown conversation"
        return no_conversation(conversation_id)
    except TurnConflictError as exc:
        outcome = "conflict"
        return problem(409, "turn-conflict", "The conversation has moved on", exc.detail)
    except ProjectDeletedError as exc:
        outcome = "project deleted"
        return problem(409, "project-deleted", "This project is deleted", str(exc))
    # A `ProjectError` (an inventory or document the project refuses) is a `ValueError`.
    except REFUSED_BEFORE_RUN as exc:
        outcome = "refused"
        return refused(str(exc))
    except BaseException:
        outcome = "failed or dropped"
        raise
    finally:
        log.info(
            "data-director: turn %s %s in %.1f s",
            conversation_id,
            outcome,
            time.monotonic() - started,
        )


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
