"""Test doubles for the tool gateway (docs/specs/agents.md, Tools): a fake MCP server, a gateway
over it, a profile that grants it and a persona that reads records through it.

Imported on its own, never from `dd_harness.testing`, since it needs the harness's `gateway` extra.
`make_conductor(..., gateway=fake_gateway())` serves the gateway in memory beside the delegation
callback, so a persona's calls cross the real MCP wire as they do in production.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml
from mcp.server import Server, ServerRequestContext
from mcp_types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)

from dd_harness.gateway.config import ToolServer, tools_digest
from dd_harness.gateway.core import Gateway
from dd_harness.gateway.upstream import Upstream
from dd_harness.testing.fixtures import PERMISSIVE
from dd_sdk.agent import AgentResult, AgentSpec, RunContext
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
    Derivation,
    GroundingMode,
    InvocationRequest,
    Message,
    Outcome,
    OutcomeStatus,
    Reply,
)
from dd_sdk.evidence import DOCUMENT_CANONICALISATION
from dd_sdk.tools import ToolUse

LICENCES: dict[str, dict[str, Any]] = {
    "CC-BY-4.0": {"licenseId": "CC-BY-4.0", "name": "Creative Commons Attribution 4.0"},
    "MIT": {"licenseId": "MIT", "name": "MIT License"},
}
_LICENCE = {
    "type": "object",
    "properties": {"licenseId": {"type": "string"}, "name": {"type": "string"}},
    "required": ["licenseId", "name"],
}
TOOLS = (
    Tool(
        name="get_licence",
        description="One licence by its SPDX identifier.",
        input_schema={"type": "object", "properties": {"id": {"type": "string"}}},
        output_schema=_LICENCE,
    ),
    Tool(
        name="search_licences",
        description="Licences whose name contains the text.",
        input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
        output_schema={
            "type": "object",
            "properties": {"records": {"type": "array", "items": _LICENCE}},
            "required": ["records"],
        },
    ),
    Tool(
        name="describe",
        description="A licence in words: text only.",
        input_schema={"type": "object", "properties": {"id": {"type": "string"}}},
    ),
)


def fake_server(tools: Sequence[Tool] = TOOLS) -> Server[Any]:
    """An in-process MCP server serving `LICENCES`. A server given other `tools` lists them, as
    a server whose tools have changed since they were pinned does."""

    async def list_tools(
        ctx: ServerRequestContext[Any, Any], params: PaginatedRequestParams | None
    ) -> ListToolsResult:
        return ListToolsResult(tools=list(tools))

    async def call_tool(
        ctx: ServerRequestContext[Any, Any], params: CallToolRequestParams
    ) -> CallToolResult:
        args = params.arguments or {}
        if params.name == "get_licence":
            record = LICENCES.get(str(args.get("id")))
            if record is None:
                return CallToolResult(content=[TextContent(type="text", text="no such licence")])
            return CallToolResult(content=[], structured_content=record)
        if params.name == "search_licences":
            text = str(args.get("text", "")).lower()
            found = [r for r in LICENCES.values() if text in r["name"].lower()]
            return CallToolResult(content=[], structured_content={"records": found})
        return CallToolResult(
            content=[TextContent(type="text", text=f"{args.get('id')} is a licence")]
        )

    return Server("fake-spdx", on_list_tools=list_tools, on_call_tool=call_tool)


def fake_tools_digest() -> str:
    """The pin of the fake server's tools."""
    return tools_digest(t.model_dump(mode="json", by_alias=True, exclude_none=True) for t in TOOLS)


def spdx_server(*, remote: bool = False, pin: str | None = None) -> ToolServer:
    """The fake server as the deployment lists it: on loopback, or `remote`."""
    return ToolServer(
        name="spdx",
        url="https://spdx.example.org/mcp" if remote else "http://127.0.0.1:8300/mcp",
        id_field="licenseId",
        canonicalisation=DOCUMENT_CANONICALISATION,
        tools_sha256=pin or fake_tools_digest(),
        snapshot_ref="spdx:test",
    )


def fake_gateway(
    *servers: ToolServer, serve: Callable[[ToolServer], Server[Any]] | None = None
) -> Gateway:
    """A gateway over `servers` (the fake SPDX server by default), each served in process by
    `serve` (`fake_server` by default), connected and pinned."""
    gateway = Gateway(
        servers or (spdx_server(),),
        Upstream(connect=serve or (lambda _server: fake_server())),
    )
    gateway.connect()
    return gateway


def tools_profile(
    directory: Path,
    grants: Mapping[str, Sequence[str]],
    remote_tool_content: Sequence[str] | None = None,
) -> Path:
    """The permissive test profile with `tool_servers` set to `grants`, written in `directory`."""
    data = yaml.safe_load(PERMISSIVE.read_text(encoding="utf-8"))
    data["tool_servers"] = {agent: list(servers) for agent, servers in grants.items()}
    if remote_tool_content is not None:
        data["remote_tool_content"] = list(remote_tool_content)
    path = directory / "tools-profile.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


Script = Callable[[InvocationRequest, RunContext], AgentResult]


def read_licence(request: InvocationRequest, ctx: RunContext) -> AgentResult:
    """Read the licence the message names through the gateway and cite it."""
    assert ctx.tools is not None, "the harness sent no tools grant"
    licence = getattr(request.input, "message_text", "")
    outcome = ctx.tools.call("spdx", "get_licence", {"id": licence})
    return cite(outcome.records, f"{licence} read through the gateway.")


def cite(records: Sequence[Any], text: str) -> AgentResult:
    """A succeeded reply grounded on `records` (`dd_sdk.tools.ToolRecord`)."""
    return AgentResult(
        outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement=text),
        payload=Reply(
            reply_text=text,
            reply_derivation=Derivation.TEMPLATE,
            grounded_on=[r.ref() for r in records],
        ),
        evidence=[r.evidence() for r in records],
    )


class ToolsPersona:
    """A retrieval-mode persona whose card declares the fake server's tools, and whose run is
    `script` (`read_licence` by default)."""

    def __init__(
        self,
        script: Script = read_licence,
        tools: Sequence[ToolUse] = (
            ToolUse("spdx", ("get_licence", "search_licences", "describe")),
        ),
    ) -> None:
        self.script = script
        self.spec = AgentSpec(
            agent_id="fake.tools",
            version="0",
            description="Reads licences through the tool gateway.",
            action_class="advise",
            accepts=(ClassSchema.of(Message),),
            grounding_mode=GroundingMode.RETRIEVAL,
            payload=ClassSchema.of(Reply),
            tools=tuple(tools),
        )

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        return self.script(request, ctx)
