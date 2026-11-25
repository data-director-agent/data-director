"""The ASGI application: the Open Policy Finder MCP server at `/opf/mcp`, and `/healthz`.

The server speaks MCP's streamable HTTP transport statelessly with JSON responses. DNS-rebinding
protection admits only the host names clients reach it by (loopback, and any the deployment adds).
Open Policy Finder is asked over the network, so a call is made in a worker thread.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import Any

import anyio.to_thread
import mcp_types as types
from mcp.server import Server, ServerRequestContext, streamable_http_manager, transport_security
from starlette import applications, requests, responses, routing
from starlette.types import Receive, Scope, Send

from dd_mcp_opf.tools import Tools

LOOPBACK = ("127.0.0.1", "localhost", "[::1]")


class _Relay:
    """Passes a request on to an ASGI callable. Starlette would take a bare function for a view
    that answers a `Request`, and a session manager wants the raw scope."""

    def __init__(self, target: Callable[[Scope, Receive, Send], Awaitable[None]]) -> None:
        self._target = target

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        return await self._target(scope, receive, send)


def create_app(
    tools: Tools | None = None, hosts: Sequence[str] = LOOPBACK
) -> applications.Starlette:
    """The application serving `tools` (without an API key by default, so each call says one is
    needed), reached under any of `hosts`."""
    served = tools or Tools()

    async def listing(
        _ctx: ServerRequestContext[Any, Any], _params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        return types.ListToolsResult(tools=list(served.listed))

    async def calling(
        _ctx: ServerRequestContext[Any, Any], params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        return await anyio.to_thread.run_sync(
            served.call, params.name, dict(params.arguments or {})
        )

    guard = transport_security.TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[*hosts, *(f"{h}:*" for h in hosts)],
        allowed_origins=[f"http://{h}:*" for h in hosts],
    )
    sessions = streamable_http_manager.StreamableHTTPSessionManager(
        app=Server(served.name, on_list_tools=listing, on_call_tool=calling),
        json_response=True,
        stateless=True,
        security_settings=guard,
    )

    @contextlib.asynccontextmanager
    async def lifespan(_app: applications.Starlette) -> AsyncIterator[None]:
        async with sessions.run():
            yield

    async def health(_request: requests.Request) -> responses.JSONResponse:
        return responses.JSONResponse({"status": "ok", "server": served.name})

    return applications.Starlette(
        routes=[
            routing.Route("/healthz", health, methods=["GET"]),
            routing.Route(
                f"/{served.name}/mcp",
                _Relay(sessions.handle_request),
                methods=["GET", "POST", "DELETE"],
            ),
        ],
        lifespan=lifespan,
    )
