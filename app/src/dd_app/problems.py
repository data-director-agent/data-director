"""The RFC 9457 problems the app's routes answer with (docs/specs/app.md)."""

from __future__ import annotations

from typing import Any

from starlette.responses import JSONResponse, Response

from dd_sdk.contract.problem import PROBLEM_BASE


def problem(status: int, slug: str, title: str, detail: str, **extra: Any) -> Response:
    """An RFC 9457 problem; `extra` are its extension members."""
    return JSONResponse(
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
