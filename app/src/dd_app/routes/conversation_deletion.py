"""Deleting and restoring a conversation (docs/specs/app.md, rule 31).

`DELETE /api/conversations/{id}` deletes a conversation, which hides it from every list and
removes nothing, and answers with until when it may be restored. `POST
/api/conversations/{id}/restore` restores it within that period, and `GET
/api/conversations/deleted` lists those the person may still restore. Whoever started a
conversation may delete and restore it, and so may the project's owner
(`dd_app.conversation_deletion`). One the person may not read is answered with 404, as one that
does not exist; one they may read but not delete with 403.
"""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from dd_app.conversation_deletion import ConversationDeletion, MayNotDeleteError
from dd_app.governance import UnknownConversationError
from dd_app.routes.common import (
    Deps,
    caused_by,
    no_conversation,
    problem,
    refused,
    signed_in,
)
from dd_harness.projects import (
    ConversationDeletedError,
    ProjectDeletedError,
    ProjectError,
    RestoreRefusedError,
)
from dd_harness.transport.paging import PagingError, page_params, page_response
from dd_sdk.contract.models import Principal

RESTORE_REFUSED = "Data Director could not restore this conversation"


def routes(deps: Deps) -> list[Route]:
    # Before `GET /api/conversations/{conversation_id}`, which would otherwise take `deleted`.
    return [
        Route("/api/conversations/deleted", signed_in(deps, list_deleted), methods=["GET"]),
        Route(
            "/api/conversations/{conversation_id}",
            signed_in(deps, delete_conversation),
            methods=["DELETE"],
        ),
        Route(
            "/api/conversations/{conversation_id}/restore",
            signed_in(deps, restore_conversation),
            methods=["POST"],
        ),
    ]


async def list_deleted(request: Request, person: Principal, deps: Deps) -> Response:
    try:
        paging = page_params(request)
    except PagingError as exc:
        return refused(str(exc), "Data Director could not list the deleted conversations")
    deletion = ConversationDeletion(deps.governance)
    page = await run_in_threadpool(lambda: deletion.deleted_for(person, **paging))
    return page_response(request, page)


async def delete_conversation(request: Request, person: Principal, deps: Deps) -> Response:
    conversation_id = request.path_params["conversation_id"]
    deletion = ConversationDeletion(deps.governance)
    try:
        deleted = await run_in_threadpool(
            lambda: deletion.delete(conversation_id, acted_for=person, caused_by=caused_by(request))
        )
    except ConversationDeletedError as exc:
        return problem(409, "conversation-deleted", "This conversation is deleted", str(exc))
    except (UnknownConversationError, MayNotDeleteError, ProjectError) as exc:
        return _refusal(exc, conversation_id)
    return JSONResponse(deleted)


async def restore_conversation(request: Request, person: Principal, deps: Deps) -> Response:
    conversation_id = request.path_params["conversation_id"]
    deletion = ConversationDeletion(deps.governance)
    try:
        await run_in_threadpool(
            lambda: deletion.restore(
                conversation_id, acted_for=person, caused_by=caused_by(request)
            )
        )
    except RestoreRefusedError as exc:
        return problem(409, "conversation-restore-refused", RESTORE_REFUSED, str(exc))
    except (UnknownConversationError, MayNotDeleteError, ProjectError) as exc:
        return _refusal(exc, conversation_id)
    return Response(status_code=204)


def _refusal(exc: Exception, conversation_id: str) -> Response:
    """404 for a conversation the person may not see, 403 for one they may not delete, 409 in
    a deleted project, and 400 for anything else the project refuses."""
    if isinstance(exc, MayNotDeleteError):
        return problem(
            403,
            "conversation-action-forbidden",
            "Not yours to delete",
            "Only whoever started a conversation, or its project's owner, may delete it.",
        )
    if isinstance(exc, ProjectDeletedError):
        return problem(409, "project-deleted", "This project is deleted", str(exc))
    if isinstance(exc, UnknownConversationError):
        return no_conversation(conversation_id)
    return refused(str(exc), "Data Director could not change this conversation")
