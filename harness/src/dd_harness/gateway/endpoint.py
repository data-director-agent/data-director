"""The tool gateway's MCP endpoint, the one agents call (docs/specs/agents.md, Tools).

One of the harness's two importers of the MCP Python SDK (docs/specs/dependencies.md). The endpoint
speaks the stateless revision of MCP's streamable HTTP transport (2026-07-28): each request is one
POST answered with one JSON response, so the endpoint keeps no session and needs no task group of
its own, and it can be mounted in any Starlette application (the harness's, the workbench's and
the app's) beside the delegation callback. The SDK handles the protocol; this module answers
`tools/list` and `tools/call` from the `Gateway`, taking the grant's token from the request's
bearer token. A refused call is an MCP error, never a tool result.

`handle_modern_request` is the SDK's per-request entry, in a private module; the SDK is pinned to
a minor version for that reason, and `harness/tests/test_gateway.py` exercises it.
"""

from __future__ import annotations

from typing import Any

from mcp.server import Server, ServerRequestContext
from mcp.server._streamable_http_modern import handle_modern_request
from mcp.shared.exceptions import MCPError
from mcp_types import (
    INVALID_PARAMS,
    INVALID_REQUEST,
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    Tool,
)
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from dd_harness.gateway.core import Gateway, ToolCallError
from dd_sdk.wire import GATEWAY_PATH


def _token(ctx: ServerRequestContext[Any, Any]) -> str:
    request = ctx.request
    header = request.headers.get("authorization", "") if request is not None else ""
    scheme, _, token = str(header).partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise MCPError(code=INVALID_REQUEST, message="a tools grant's bearer token is required")
    return token


def mcp_server(gateway: Gateway) -> Server[Any]:
    """The MCP server the endpoint serves: `tools/list` and `tools/call` under a grant."""

    async def list_tools(
        ctx: ServerRequestContext[Any, Any], params: PaginatedRequestParams | None
    ) -> ListToolsResult:
        try:
            listed = gateway.listed(_token(ctx))
        except ToolCallError as exc:
            raise MCPError(code=INVALID_REQUEST, message=str(exc)) from None
        return ListToolsResult(tools=[Tool.model_validate(t) for t in listed])

    async def call_tool(
        ctx: ServerRequestContext[Any, Any], params: CallToolRequestParams
    ) -> CallToolResult:
        try:
            return await gateway.call(_token(ctx), params.name, params.arguments or {})
        except ToolCallError as exc:
            raise MCPError(code=INVALID_PARAMS, message=str(exc)) from None

    return Server("data-director-tool-gateway", on_list_tools=list_tools, on_call_tool=call_tool)


class GatewayEndpoint:
    """The ASGI application at `GATEWAY_PATH`."""

    def __init__(self, gateway: Gateway) -> None:
        self.server = mcp_server(gateway)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await handle_modern_request(
            self.server,
            None,
            json_response=True,
            lifespan_state={},
            scope=scope,
            receive=receive,
            send=send,
        )


def gateway_routes(gateway: Gateway) -> list[Route]:
    """The gateway's route (`dd_harness.gateway.routes` is how a way in mounts it)."""
    return [Route(GATEWAY_PATH, endpoint=GatewayEndpoint(gateway), methods=["POST"])]
