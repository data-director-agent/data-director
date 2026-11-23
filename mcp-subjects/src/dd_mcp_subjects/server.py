"""The MCP server over the subjects tools, for any transport (`app.py` serves it over HTTP)."""

from __future__ import annotations

from typing import Any

from mcp.server import Server, ServerRequestContext
from mcp_types import CallToolRequestParams, CallToolResult, ListToolsResult, PaginatedRequestParams

from dd_mcp_subjects.tools import Tools


def server(tools: Tools) -> Server[Any]:
    """The MCP server that lists `tools` and answers their calls."""

    async def listed(
        _ctx: ServerRequestContext[Any, Any], _params: PaginatedRequestParams | None
    ) -> ListToolsResult:
        return ListToolsResult(tools=list(tools.listed))

    async def called(
        _ctx: ServerRequestContext[Any, Any], params: CallToolRequestParams
    ) -> CallToolResult:
        return tools.call(params.name, dict(params.arguments or {}))

    return Server(tools.name, on_list_tools=listed, on_call_tool=called)
