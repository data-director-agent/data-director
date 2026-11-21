"""The ASGI application: the FAIRsharing MCP server at `/fairsharing/mcp`, and `/healthz`.

The server speaks MCP's streamable HTTP transport statelessly with JSON responses, through the MCP
SDK's session manager. DNS-rebinding protection admits only the host names clients reach it by
(loopback, and any the deployment adds). Lookups block on the network, so each runs in a worker
thread.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import Any

import anyio.to_thread
import mcp_types as types
from mcp.server import Server, ServerRequestContext
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from dd_mcp_fairsharing.tools import Tools

LOOPBACK = ("127.0.0.1", "localhost", "[::1]")


class _Asgi:
    """Any ASGI callable as a route's endpoint: Starlette takes a bare function for a view."""

    def __init__(self, handle: Callable[[Scope, Receive, Send], Awaitable[None]]) -> None:
        self.handle = handle

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.handle(scope, receive, send)


def create_app(tools: Tools, hosts: Sequence[str] = LOOPBACK) -> Starlette:
    """The application serving `tools`, reached under any of `hosts`."""

    async def list_tools(
        _ctx: ServerRequestContext[Any, Any], _params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        return types.ListToolsResult(tools=list(tools.listed))

    async def call_tool(
        _ctx: ServerRequestContext[Any, Any], params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        return await anyio.to_thread.run_sync(tools.call, params.name, dict(params.arguments or {}))

    manager = StreamableHTTPSessionManager(
        app=Server(tools.name, on_list_tools=list_tools, on_call_tool=call_tool),
        json_response=True,
        stateless=True,
        security_settings=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[*hosts, *(f"{h}:*" for h in hosts)],
            allowed_origins=[f"http://{h}:*" for h in hosts],
        ),
    )

    async def healthz(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "server": tools.name})

    @contextlib.asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        async with manager.run():
            yield

    return Starlette(
        routes=[
            Route("/healthz", healthz, methods=["GET"]),
            Route(
                f"/{tools.name}/mcp",
                _Asgi(manager.handle_request),
                methods=["GET", "POST", "DELETE"],
            ),
        ],
        lifespan=lifespan,
    )
