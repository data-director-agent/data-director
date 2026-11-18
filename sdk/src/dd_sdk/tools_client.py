"""The client an agent calls the harness's tool gateway with (docs/specs/agents.md, Tools).

The SDK's one importer of the MCP Python SDK (`mcp`, the `tools` extra; docs/specs/dependencies.md).
`dd_sdk.serve` builds a `HarnessTools` from the grant the harness sent and hands it to the agent as
`ctx.tools`. Each call opens a session with the gateway's MCP endpoint, presenting the grant's
token as a bearer token, and reads the records the gateway recorded from the result
(`dd_sdk.tools.records_from_result`). An agent's `run` is synchronous, so each call runs its own
event loop, as `dd_sdk.delegate` does.

The fallback, should `mcp` be dropped, is JSON-RPC 2.0 over `httpx`: the gateway answers each
request with one JSON response.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError
from mcp_types import CallToolResult, TextContent
from mcp_types.version import MODERN_PROTOCOL_VERSIONS

from dd_sdk.tools import ToolGatewayError, ToolOutcome, ToolsGrant, records_from_result, split_name

DEFAULT_TIMEOUT_S = 60.0
# The gateway speaks the stateless revision of the protocol only: one POST, one JSON response.
PROTOCOL_VERSION = MODERN_PROTOCOL_VERSIONS[0]

# The HTTP client a call is made with, given the grant; tests bind it to the harness in memory.
ClientFactory = Callable[[ToolsGrant, float], httpx2.AsyncClient]


def default_client(grant: ToolsGrant, timeout_s: float) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(headers={"Authorization": f"Bearer {grant.token}"}, timeout=timeout_s)


@dataclass
class HarnessTools:
    """The `Tools` `dd_sdk.serve` hands an agent, bound to one grant."""

    grant: ToolsGrant
    timeout_s: float = DEFAULT_TIMEOUT_S
    client_factory: ClientFactory = default_client
    _listed: list[dict[str, Any]] | None = field(default=None, init=False, repr=False)

    def listed(self) -> list[dict[str, Any]]:
        """The tools the gateway lists for this invocation, read once per grant."""
        if self._listed is None:
            self._listed = asyncio.run(self._list())
        return list(self._listed)

    def call(self, server: str, tool: str, arguments: Mapping[str, Any]) -> ToolOutcome:
        """Call `tool` on `server` through the gateway. A refusal, or a gateway that cannot be
        reached, is a `ToolGatewayError`."""
        result = asyncio.run(self._call(f"{server}.{tool}", dict(arguments)))
        text = "\n".join(c.text for c in result.content if isinstance(c, TextContent))
        structured = result.structured_content
        return ToolOutcome(
            records=() if result.is_error else records_from_result(structured, result.meta),
            text=text,
            is_error=bool(result.is_error),
            structured=structured,
        )

    async def _list(self) -> list[dict[str, Any]]:
        listed = await self._guarded("tools/list", lambda client: client.list_tools())
        return [
            {
                "name": t.name,
                "description": t.description or "",
                "input_schema": dict(t.input_schema),
            }
            for t in listed.tools
            if _named(t.name)
        ]

    async def _call(self, name: str, arguments: dict[str, Any]) -> CallToolResult:
        answered = await self._guarded(name, lambda client: client.call_tool(name, arguments))
        if not isinstance(answered, CallToolResult):
            raise ToolGatewayError(f"the tool gateway answered {name} with no tool result")
        return answered

    async def _guarded[T](self, what: str, op: Callable[[Client], Awaitable[T]]) -> T:
        """`op` in a session with the gateway; a refusal or an unreachable gateway is a
        `ToolGatewayError`."""
        try:
            http = self.client_factory(self.grant, self.timeout_s)
            async with Client(
                streamable_http_client(self.grant.url, http_client=http), mode=PROTOCOL_VERSION
            ) as client:
                return await op(client)
        except MCPError as exc:
            raise ToolGatewayError(f"the tool gateway refused {what}: {exc}") from exc
        except (httpx2.HTTPError, OSError, ExceptionGroup) as exc:
            raise ToolGatewayError(f"the tool gateway could not be reached: {exc}") from exc


def _named(name: str) -> bool:
    try:
        split_name(name)
    except ValueError:
        return False
    return True
