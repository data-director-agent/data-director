"""The ASGI application: the SPDX MCP server at `/spdx/mcp`, and `/healthz`.

The server speaks MCP's streamable HTTP transport statelessly with JSON responses, through the MCP
SDK's session manager. DNS-rebinding protection admits only the host names clients reach it by
(loopback, and any the deployment adds). A lookup reads the packaged release in memory, so it is
answered on the event loop. `/healthz` also names the release served. The application is a plain
ASGI callable: two paths need no router.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import mcp_types as types
from mcp.server import Server, ServerRequestContext
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.types import Receive, Scope, Send

from dd_mcp_spdx.tools import Tools

LOOPBACK = ("127.0.0.1", "localhost", "[::1]")


class SpdxApp:
    """The server for `tools`, reached under any of `hosts`."""

    def __init__(self, tools: Tools, hosts: Sequence[str]) -> None:
        self.tools = tools
        self.path = f"/{tools.name}/mcp"
        security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[*hosts, *(f"{h}:*" for h in hosts)],
            allowed_origins=[f"http://{h}:*" for h in hosts],
        )
        server = Server(tools.name, on_list_tools=self._list, on_call_tool=self._call)
        self.manager = StreamableHTTPSessionManager(
            app=server, json_response=True, stateless=True, security_settings=security
        )

    async def _list(
        self, _ctx: ServerRequestContext[Any, Any], _params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        return types.ListToolsResult(tools=list(self.tools.listed))

    async def _call(
        self, _ctx: ServerRequestContext[Any, Any], params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        return self.tools.call(params.name, dict(params.arguments or {}))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self._lifespan(receive, send)
        elif scope["path"] == self.path:
            await self.manager.handle_request(scope, receive, send)
        elif scope["path"] == "/healthz" and scope["type"] == "http":
            health = {
                "status": "ok",
                "server": self.tools.name,
                "snapshot_ref": self.tools.release.snapshot_ref,
            }
            await JSONResponse(health)(scope, receive, send)
        else:
            await PlainTextResponse("Not Found", status_code=404)(scope, receive, send)

    async def _lifespan(self, receive: Receive, send: Send) -> None:
        """Run the session manager from start-up to shutdown."""
        await receive()  # lifespan.startup
        async with self.manager.run():
            await send({"type": "lifespan.startup.complete"})
            await receive()  # lifespan.shutdown
        await send({"type": "lifespan.shutdown.complete"})


def create_app(tools: Tools | None = None, hosts: Sequence[str] = LOOPBACK) -> SpdxApp:
    """The application serving `tools` (the packaged release by default), reached under any of
    `hosts`."""
    return SpdxApp(tools or Tools(), hosts)
