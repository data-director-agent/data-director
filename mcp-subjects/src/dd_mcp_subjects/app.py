"""The ASGI application: the subjects MCP server at `/subjects/mcp`, and `/healthz`.

The server speaks MCP's streamable HTTP transport statelessly with JSON responses, through the MCP
SDK's session manager. DNS-rebinding protection admits only the host names clients reach it by
(loopback, and any the deployment adds). A call reads the packaged schemes in memory, so it is
answered on the event loop. `/healthz` also names the schemes served, with their versions.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator, Sequence

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from dd_mcp_subjects.server import server
from dd_mcp_subjects.tools import Tools
from dd_subjects import SCHEMES, scheme

LOOPBACK = ("127.0.0.1", "localhost", "[::1]")


class _Endpoint:
    """The session manager's handler as a plain ASGI app, which Starlette serves as one rather
    than treating it as a view."""

    def __init__(self, handle: ASGIApp) -> None:
        self.handle = handle

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.handle(scope, receive, send)


def create_app(tools: Tools | None = None, hosts: Sequence[str] = LOOPBACK) -> Starlette:
    """The application serving `tools` (the packaged schemes by default), reached under any of
    `hosts`."""
    served = tools or Tools()
    admitted = [*hosts, *(f"{h}:*" for h in hosts)]
    manager = StreamableHTTPSessionManager(
        app=server(served),
        json_response=True,
        stateless=True,
        security_settings=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=admitted,
            allowed_origins=[f"http://{h}:*" for h in hosts],
        ),
    )

    async def health(_request: Request) -> JSONResponse:
        versions = {s: scheme(s).version for s in SCHEMES}
        return JSONResponse({"status": "ok", "server": served.name, "schemes": versions})

    @contextlib.asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        async with manager.run():
            yield

    mcp = Route(f"/{served.name}/mcp", _Endpoint(manager.handle_request), methods=["GET", "POST"])
    return Starlette(routes=[Route("/healthz", health, methods=["GET"]), mcp], lifespan=lifespan)
