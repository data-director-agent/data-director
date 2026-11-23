"""The ASGI application: the DOAJ MCP server at `/doaj/mcp`, and `/healthz`.

The server speaks MCP's streamable HTTP transport statelessly with JSON responses, through the MCP
SDK's session manager. DNS-rebinding protection admits only the host names clients reach it by
(loopback, and any the deployment adds). A lookup asks DOAJ over the network, so each call runs in
a worker thread, off the event loop.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from functools import partial
from typing import Any

import mcp_types as mcp
from anyio import to_thread
from mcp.server import Server, ServerRequestContext
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from dd_mcp_doaj.tools import Tools

LOOPBACK = ("127.0.0.1", "localhost", "[::1]")


def admitted(hosts: Sequence[str]) -> TransportSecuritySettings:
    """The protection that admits a request only from `hosts`, on any port."""
    names = list(hosts)
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=names + [name + ":*" for name in names],
        allowed_origins=["http://" + name + ":*" for name in names],
    )


async def _listed(
    tools: Tools, _ctx: ServerRequestContext[Any, Any], _page: mcp.PaginatedRequestParams | None
) -> mcp.ListToolsResult:
    return mcp.ListToolsResult(tools=[*tools.listed])


async def _answered(
    tools: Tools, _ctx: ServerRequestContext[Any, Any], request: mcp.CallToolRequestParams
) -> mcp.CallToolResult:
    arguments = dict(request.arguments or {})
    return await to_thread.run_sync(tools.call, request.name, arguments)


@dataclass(frozen=True)
class _Mcp:
    """The session manager as a plain ASGI app: Starlette would treat a bound method as a view."""

    manager: StreamableHTTPSessionManager

    async def __call__(self, *asgi: Any) -> None:
        await self.manager.handle_request(*asgi)


def create_app(tools: Tools | None = None, hosts: Sequence[str] = LOOPBACK) -> Starlette:
    """The application serving `tools` (DOAJ's live API by default), reached under any of
    `hosts`."""
    served = tools or Tools()
    server = Server(
        served.name,
        on_list_tools=partial(_listed, served),
        on_call_tool=partial(_answered, served),
    )
    manager = StreamableHTTPSessionManager(
        app=server, json_response=True, stateless=True, security_settings=admitted(hosts)
    )

    @contextlib.asynccontextmanager
    async def running(_app: Starlette) -> AsyncIterator[None]:
        async with manager.run():
            yield

    async def health(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "server": served.name})

    mcp_path = "/" + served.name + "/mcp"
    routes = [
        Route("/healthz", health, methods=["GET"]),
        Route(mcp_path, _Mcp(manager), methods=["GET", "POST", "DELETE"]),
    ]
    return Starlette(routes=routes, lifespan=running)
