"""Paging a listing over HTTP (docs/specs/storage.md, "Listing").

A listing endpoint takes `?limit=` (how many items, at most `PAGE_SIZE_MAX`, `PAGE_SIZE` unless
given) and `?before=` (the cursor of the page before). Its body is the page's items, a JSON list;
when there is a next page, a `Link` header names it with `rel="next"` (RFC 8288), keeping the
request's other parameters. A cursor is opaque to the client.
"""

from __future__ import annotations

import re
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from dd_harness.listing import Page

PAGE_SIZE = 50
PAGE_SIZE_MAX = 200
_LIMIT = re.compile(r"[0-9]{1,4}")


class PagingError(ValueError):
    """A `limit` that is not a whole number from 1 to `PAGE_SIZE_MAX`."""


def page_params(request: Request) -> dict[str, Any]:
    """The `limit` and `before` a request asks for, as keyword arguments to a listing. Raises
    `PagingError` for a malformed `limit`; a malformed `before` names an empty page."""
    given = request.query_params.get("limit")
    limit = PAGE_SIZE
    if given is not None:
        if not _LIMIT.fullmatch(given) or not 1 <= int(given) <= PAGE_SIZE_MAX:
            raise PagingError(f"limit is a whole number from 1 to {PAGE_SIZE_MAX}, not {given!r}")
        limit = int(given)
    return {"limit": limit, "before": request.query_params.get("before")}


def page_response(request: Request, page: Page) -> JSONResponse:
    """The page's items, with a `Link` to the next page if there is one."""
    headers = {}
    if page.next is not None:
        following = request.url.include_query_params(before=page.next)
        headers["Link"] = f'<{following}>; rel="next"'
    return JSONResponse(page.items, headers=headers)
