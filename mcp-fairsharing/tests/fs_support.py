"""Test doubles: FAIRsharing served from small files shaped like its answers, never the network.

The files in `data/` are made up, in the shape of FAIRsharing's public record route and its
authenticated search answer, so the tests need no account. They are not recordings.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx

from dd_mcp_fairsharing.client import Fairsharing
from dd_mcp_fairsharing.http import Http
from dd_mcp_fairsharing.tools import Registry, fairsharing_registry

DATA = Path(__file__).with_name("data")
RECORD_ID = "FAIRsharing.abc123"
LOGIN = ("someone@example.org", "not-a-real-password")
seen: list[httpx.Request] = []


def served(request: httpx.Request) -> httpx.Response:
    seen.append(request)
    path = request.url.path
    if request.url.host == "fairsharing.org":
        if path.lstrip("/") in {RECORD_ID, "1234"}:
            return httpx.Response(
                200,
                content=(DATA / "public-record.json").read_bytes(),
                headers={"content-type": "application/json"},
            )
        return httpx.Response(200, text="<html></html>", headers={"content-type": "text/html"})
    if path == "/users/sign_in":
        return httpx.Response(200, json={"jwt": "token"})
    if path == "/search/fairsharing_records":
        if request.headers.get("authorization") != "Bearer token":
            return httpx.Response(401)
        return httpx.Response(
            200,
            content=(DATA / "search.json").read_bytes(),
            headers={"content-type": "application/json"},
        )
    return httpx.Response(404)


def client(
    handler: Callable[[httpx.Request], httpx.Response] = served, *, account: bool = True
) -> Fairsharing:
    http = Http(
        "FAIRsharing",
        headers={"Accept": "application/json"},
        transport=httpx.MockTransport(handler),
        sleep=lambda _s: None,
    )
    return Fairsharing(http, *(LOGIN if account else ("", "")))


def registry(*, account: bool = True) -> Registry:
    return fairsharing_registry(client(account=account))
