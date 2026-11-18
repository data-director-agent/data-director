"""The MCP servers the tool gateway calls (docs/specs/agents.md, Tools).

One of the harness's two importers of the MCP Python SDK (`mcp`, the `gateway` extra;
docs/specs/dependencies.md); the other is `dd_harness.gateway.endpoint`. Each call opens a client
session with the server, in the caller's event loop, and closes it, so the gateway holds no
connection between calls. `connect` says what to connect to: the server's URL by default, or, in
tests, an in-process `mcp.server.Server` (`dd_harness.testing`).

The fallback, should `mcp` be dropped, is JSON-RPC 2.0 over `httpx` to each server's endpoint.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from mcp import Client
from mcp.client import Transport
from mcp.server import Server
from mcp_types import CallToolResult

from dd_harness.gateway.config import ToolServer

DEFAULT_TIMEOUT_S = 60.0

# What `mcp.Client` connects to for a server: its URL, or an in-process server in tests.
type Target = str | Server[Any] | Transport
type Connect = Callable[[ToolServer], Target]


class UpstreamError(Exception):
    """A server could not be reached, or answered with something other than a tool result."""


def by_url(server: ToolServer) -> Target:
    return server.url


@dataclass(frozen=True)
class Upstream:
    connect: Connect = by_url
    timeout_s: float = DEFAULT_TIMEOUT_S

    async def list_tools(self, server: ToolServer) -> list[dict[str, Any]]:
        """The server's tools, each as its tools/list entry in the protocol's JSON form."""
        async with self._client(server) as client:
            listed = await client.list_tools()
        return [t.model_dump(mode="json", by_alias=True, exclude_none=True) for t in listed.tools]

    async def call_tool(
        self, server: ToolServer, tool: str, arguments: Mapping[str, Any]
    ) -> CallToolResult:
        async with self._client(server) as client:
            answered = await client.call_tool(tool, dict(arguments))
        if not isinstance(answered, CallToolResult):
            raise UpstreamError(f"{server.name} answered {tool} with no tool result")
        return answered

    def _client(self, server: ToolServer) -> Client:
        return Client(self.connect(server), read_timeout_seconds=self.timeout_s, cache=None)
