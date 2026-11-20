"""The tool gateway: the one way a persona reaches an MCP server (docs/specs/agents.md, Tools).

At start-up `connect` lists each server's tools and compares their digest with the pin the
deployment's list gives (`dd_harness.gateway.config`). A server that cannot be reached, or whose
tools have changed, is unavailable until an operator pins its list again, so a changed tool
description cannot reach a prompt unreviewed.

The conductor issues an invocation a `ToolGrant` when its profile grants the agent servers its
card declares (`granted`), as it issues a delegation grant: a random token the agent presents to
the gateway's endpoint (`dd_harness.gateway.endpoint`) while the invocation runs. A call is
refused unless the tool is on a server the grant covers, the card declares it and the server is
available. The gateway forwards the call and records each record of a structured result that its
tool's pinned output schema admits: its source id (`tool:<server>/<record id>`), its hash under
the canonicalisation the deployment names for the server, and when it was returned. Those records
are the conductor's observation, listed in the envelope's `tool_retrievals`, and are what the
linter grounds a tool source on (docs/specs/grounding.md, invariant 15). The gateway tells the
agent what it recorded in the result's `_meta` (`dd_sdk.tools.RECORDS_META`), overwriting
anything a server put there. Text a tool returns is passed on and recorded as nothing.

Each call is an `execute_tool` span in the invocation's trace, a child of its `invoke_agent` span.
A grant issued with the run's `Watch` also tells the run's observer each call as it starts and as
it finishes, by the tool's gateway name only, so that a person watching the run sees its tools
used while the agent works (docs/specs/app.md, "Run events to the browser").
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import threading
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from jsonschema import validators
from mcp_types import CallToolResult, TextContent
from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.trace import NonRecordingSpan, SpanContext, Tracer

from dd_harness.gateway.config import ToolServer, tools_digest
from dd_harness.gateway.upstream import Upstream
from dd_harness.observe import Watch
from dd_sdk.agent import AgentSpec
from dd_sdk.contract.models import ToolRetrieval, tool_source_id
from dd_sdk.evidence import content_hash
from dd_sdk.tools import RECORDS_META, gateway_name, split_name
from dd_sdk.tracing import execute_tool_span

log = logging.getLogger(__name__)


class ToolCallError(Exception):
    """The gateway will not run a call: an unknown or expired token, or a tool the grant does not
    cover. A caller error, answered as an MCP error."""


@dataclass(frozen=True)
class Pinned:
    """An available server and its tools as listed and pinned, by tool name."""

    server: ToolServer
    tools: Mapping[str, Mapping[str, Any]]


@dataclass
class ToolGrant:
    """One invocation's grant, live while it runs."""

    token: str
    agent_id: str
    # Server -> the tools on it the grant covers.
    servers: Mapping[str, frozenset[str]]
    tracer: Tracer
    parent: SpanContext | None
    records: list[ToolRetrieval] = field(default_factory=list)
    in_flight: int = 0
    # The run's watch, told each call by name; none for a run nobody watches.
    watch: Watch | None = None


@dataclass
class Gateway:
    servers: Sequence[ToolServer]
    upstream: Upstream = field(default_factory=Upstream)
    available: dict[str, Pinned] = field(default_factory=dict)
    # Server -> why it is unavailable.
    unavailable: dict[str, str] = field(default_factory=dict)
    _grants: dict[str, ToolGrant] = field(default_factory=dict, repr=False)
    _lock: threading.Condition = field(default_factory=threading.Condition, repr=False)

    def server(self, name: str) -> ToolServer | None:
        return next((s for s in self.servers if s.name == name), None)

    def connect(self) -> None:
        """List each server's tools and keep those whose digest matches its pin. Run once, at
        start-up."""
        for server, tools in zip(self.servers, self.list_all(), strict=True):
            if isinstance(tools, BaseException):
                self._unavailable(server, f"its tools could not be listed: {tools}")
            elif (digest := tools_digest(tools)) != server.tools_sha256:
                self._unavailable(
                    server,
                    f"its tools have changed (digest {digest}, pinned {server.tools_sha256}); "
                    "review them and pin the new list (`dd-harness tools pins`)",
                )
            else:
                self.available[server.name] = Pinned(server, {str(t["name"]): t for t in tools})

    def list_all(self) -> list[list[dict[str, Any]] | BaseException]:
        """Each server's tools, or why they could not be listed, in the list's order. Run in a
        thread of its own, so that it may be called from async code too."""

        async def every() -> list[list[dict[str, Any]] | BaseException]:
            return await asyncio.gather(
                *(self.upstream.list_tools(s) for s in self.servers), return_exceptions=True
            )

        with ThreadPoolExecutor(max_workers=1) as one:
            return one.submit(asyncio.run, every()).result()

    def _unavailable(self, server: ToolServer, why: str) -> None:
        self.unavailable[server.name] = why
        log.warning("MCP server %r is unavailable: %s", server.name, why)

    def granted(self, spec: AgentSpec, grants: Sequence[str]) -> dict[str, frozenset[str]]:
        """Of the servers the profile `grants` the agent, those its card declares and that are
        available, each with the declared tools the server lists."""
        out: dict[str, frozenset[str]] = {}
        for use in spec.tools:
            pinned = self.available.get(use.server)
            if (
                use.server in grants
                and pinned is not None
                and (tools := frozenset(use.tools) & set(pinned.tools))
            ):
                out[use.server] = tools
        return out

    def remote(self, spec: AgentSpec, grants: Sequence[str]) -> bool:
        """Whether a server the profile grants the agent, and its card declares, is `remote`,
        available or not (docs/specs/policy-and-identity.md)."""
        return any(
            (server := self.server(use.server)) is not None
            and use.server in grants
            and server.locality == "remote"
            for use in spec.tools
        )

    def issue(
        self,
        agent_id: str,
        servers: Mapping[str, frozenset[str]],
        tracer: Tracer,
        parent: SpanContext | None,
        watch: Watch | None = None,
    ) -> ToolGrant:
        grant = ToolGrant(
            secrets.token_urlsafe(32), agent_id, dict(servers), tracer, parent, watch=watch
        )
        with self._lock:
            self._grants[grant.token] = grant
        return grant

    def revoke(self, grant: ToolGrant) -> list[ToolRetrieval]:
        """Refuse further calls, wait for those under way, and return what was recorded."""
        with self._lock:
            self._grants.pop(grant.token, None)
            self._lock.wait_for(lambda: grant.in_flight == 0)
            return list(grant.records)

    def listed(self, token: str) -> list[dict[str, Any]]:
        """The tools `token` may call, under their gateway names, as their pinned entries."""
        grant = self._grant(token)
        return [
            {**self.available[server].tools[tool], "name": gateway_name(server, tool)}
            for server, tools in sorted(grant.servers.items())
            for tool in sorted(tools)
        ]

    async def call(self, token: str, name: str, arguments: Mapping[str, Any]) -> CallToolResult:
        with self._lock:
            grant = self._grant(token)
            try:
                server_name, tool = split_name(name)
            except ValueError as exc:
                raise ToolCallError(str(exc)) from None
            if tool not in grant.servers.get(server_name, frozenset()):
                raise ToolCallError(f"{name} is not a tool this invocation may call")
            grant.in_flight += 1
        try:
            return await self._forward(grant, self.available[server_name], tool, arguments)
        finally:
            with self._lock:
                grant.in_flight -= 1
                self._lock.notify_all()

    def _grant(self, token: str) -> ToolGrant:
        grant = self._grants.get(token)
        if grant is None:
            raise ToolCallError("unknown or expired tools token")
        return grant

    async def _forward(
        self, grant: ToolGrant, pinned: Pinned, tool: str, arguments: Mapping[str, Any]
    ) -> CallToolResult:
        name = gateway_name(pinned.server.name, tool)
        call_id = secrets.token_hex(8)
        if grant.watch is not None:
            grant.watch.tool_started(call_id, name)
        ok = False
        try:
            result = await self._answered(grant, pinned, tool, arguments)
            ok = not result.is_error
            return result
        finally:
            if grant.watch is not None:
                grant.watch.tool_finished(call_id, name, ok=ok)

    async def _answered(
        self, grant: ToolGrant, pinned: Pinned, tool: str, arguments: Mapping[str, Any]
    ) -> CallToolResult:
        parent = otel_context.attach(
            trace.set_span_in_context(NonRecordingSpan(grant.parent))
            if grant.parent is not None
            else otel_context.get_current()
        )
        try:
            with execute_tool_span(grant.tracer, gateway_name(pinned.server.name, tool)):
                try:
                    result = await self.upstream.call_tool(pinned.server, tool, arguments)
                except Exception as exc:  # noqa: BLE001 — a server's failure is the tool's error
                    return _error(f"{pinned.server.name} could not answer {tool}: {exc}")
        finally:
            otel_context.detach(parent)
        records = (
            []
            if result.is_error
            else recorded(pinned, tool, result.structured_content, datetime.now(UTC))
        )
        with self._lock:
            grant.records.extend(records)
        meta = {k: v for k, v in (result.meta or {}).items() if k != RECORDS_META}
        if records:
            meta[RECORDS_META] = [r.model_dump(mode="json") for r in records]
        return result.model_copy(update={"meta": meta or None})


def recorded(
    pinned: Pinned, tool: str, structured: Mapping[str, Any] | None, now: datetime
) -> list[ToolRetrieval]:
    """The records of a structured result, if the tool's pinned output schema admits it and each
    record carries its identifier; otherwise none. A structured result holding several records
    lists them under `records`; any other is one record."""
    schema = pinned.tools[tool].get("outputSchema")
    if structured is None or not isinstance(schema, dict):
        return []
    if next(validators.validator_for(schema)(schema).iter_errors(structured), None) is not None:
        return []
    items = structured.get("records") if "records" in structured else [structured]
    server = pinned.server
    if not isinstance(items, list) or not all(_identified(i, server.id_field) for i in items):
        return []
    return [
        ToolRetrieval(
            tool_server=server.name,
            tool_name=tool,
            source_id=tool_source_id(server.name, str(item[server.id_field])),
            canonicalisation=server.canonicalisation,
            content_hash=content_hash(item, server.canonicalisation),
            retrieved_at=now,
        )
        for item in items
    ]


def _identified(item: Any, id_field: str) -> bool:
    value = item.get(id_field) if isinstance(item, dict) else None
    return isinstance(value, str | int) and not isinstance(value, bool) and str(value) != ""


def _error(text: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=text)], is_error=True)
