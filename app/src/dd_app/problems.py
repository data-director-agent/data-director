"""The RFC 9457 problems the app's routes answer with (docs/specs/app.md)."""

from __future__ import annotations

from typing import Any

from pydantic import ConfigDict
from starlette.responses import Response

from dd_app.responses import ResponseBody, respond
from dd_sdk.contract.problem import PROBLEM_BASE


class ProblemDetails(ResponseBody):
    """An RFC 9457 problem, which every refusal and failure is answered with.

    Open, as RFC 9457 lets a problem carry extension members; a problem whose members are known
    is described by a subclass that names them (and closes it again with `extra="forbid"`).
    """

    model_config = ConfigDict(extra="allow")

    type: str
    """The problem's kind: a URI under the deployment's problem base, ending in its slug."""
    title: str
    status: int
    detail: str


def problem(status: int, slug: str, title: str, detail: str, **extra: Any) -> Response:
    """An RFC 9457 problem; `extra` are its extension members."""
    return respond(
        ProblemDetails,
        {"type": PROBLEM_BASE + slug, "title": title, "status": status, "detail": detail, **extra},
        status_code=status,
        media_type="application/problem+json",
    )


def no_conversation(conversation_id: str) -> Response:
    return problem(
        404,
        "conversation-not-found",
        "No such conversation",
        f"No conversation {conversation_id!r}.",
    )


def refused(detail: str, title: str = "Data Director could not start this run") -> Response:
    return problem(400, "request-refused", title, detail)
