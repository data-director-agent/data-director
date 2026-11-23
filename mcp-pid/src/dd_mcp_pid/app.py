"""The ASGI application: one MCP server per registry, each at its own path.

`/datacite/mcp`, `/crossref/mcp`, `/orcid/mcp`, `/ror/mcp` and `/journals/mcp` each serve one
registry's tools over MCP's streamable HTTP transport, statelessly and with JSON responses,
through the MCP SDK's public session manager (which answers both the initialize handshake and the
per-request revision). One server per registry, rather than one for all, because a client such as
the Data Director's tool gateway identifies a server's records by one field: `doi`, `orcid`, `id`
or `issn_l`. `/healthz` answers when the application is up.

Lookups block on the network or on disk, so each runs in a worker thread.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator, Sequence
from typing import Any

import anyio.to_thread
from mcp.server import Server, ServerRequestContext
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from mcp_types import CallToolRequestParams, CallToolResult, ListToolsResult, PaginatedRequestParams
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from dd_mcp_pid.tools import Registry

LOOPBACK = ("127.0.0.1", "localhost", "[::1]")


def mcp_server(registry: Registry) -> Server[Any]:
    """The MCP server answering `tools/list` and `tools/call` for one registry."""

    async def list_tools(
        ctx: ServerRequestContext[Any, Any], params: PaginatedRequestParams | None
    ) -> ListToolsResult:
        return ListToolsResult(tools=list(registry.tools))

    async def call_tool(
        ctx: ServerRequestContext[Any, Any], params: CallToolRequestParams
    ) -> CallToolResult:
        arguments = dict(params.arguments or {})
        return await anyio.to_thread.run_sync(registry.call, params.name, arguments)

    name = f"data-director-pid-{registry.name}"
    return Server(name, on_list_tools=list_tools, on_call_tool=call_tool)


def security(hosts: Sequence[str]) -> TransportSecuritySettings:
    """DNS-rebinding protection admitting only `hosts` (with any port) as the Host header."""
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[f"{h}:*" for h in hosts] + list(hosts),
        allowed_origins=[f"http://{h}:*" for h in hosts],
    )


class _Endpoint:
    def __init__(self, manager: StreamableHTTPSessionManager) -> None:
        self.manager = manager

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.manager.handle_request(scope, receive, send)


def create_app(registries: Sequence[Registry], hosts: Sequence[str] = LOOPBACK) -> Starlette:
    """The application serving each registry at `/<name>/mcp`. `hosts` are the names clients
    reach it by: loopback by default, plus a service name in a container network."""
    managers = {
        r.name: StreamableHTTPSessionManager(
            app=mcp_server(r), json_response=True, stateless=True, security_settings=security(hosts)
        )
        for r in registries
    }

    @contextlib.asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        async with contextlib.AsyncExitStack() as stack:
            for manager in managers.values():
                await stack.enter_async_context(manager.run())
            yield

    async def healthz(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "servers": sorted(managers)})

    routes = [Route("/healthz", healthz, methods=["GET"])]
    routes += [
        Route(f"/{name}/mcp", _Endpoint(m), methods=["GET", "POST", "DELETE"])
        for name, m in managers.items()
    ]
    return Starlette(routes=routes, lifespan=lifespan)
