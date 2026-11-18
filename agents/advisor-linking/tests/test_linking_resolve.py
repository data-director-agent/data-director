"""advisor.linking's DOI lookups through the tool gateway, over the harness's in-memory fakes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from mcp.server import Server, ServerRequestContext
from mcp_types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)

from dd_agent_advisor_linking.agent import LinkingAdviser
from dd_agent_advisor_linking.classes import LinkCandidates, RelatedIdentifiers
from dd_agent_advisor_linking.resolve import DOI_TOOL
from dd_harness.gateway.config import ToolServer, tools_digest
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_harness.testing.tools import fake_gateway, tools_profile
from dd_sdk.contract.models import Envelope, OutcomeStatus
from dd_sdk.evidence import DOCUMENT_CANONICALISATION

KNOWN = "10.15497/RDA00157"
BROKEN = "10.1000/broken"
RECORDS: dict[str, dict[str, Any]] = {
    KNOWN: {"doi": KNOWN, "title": ["Data Director blueprint"], "type": "report"}
}
TOOL = Tool(
    name=DOI_TOOL,
    description="One DOI's record.",
    input_schema={"type": "object", "properties": {"doi": {"type": "string"}}},
    output_schema={
        "type": "object",
        "properties": {"doi": {"type": "string"}, "title": {}, "type": {"type": "string"}},
        "required": ["doi"],
    },
)


def doi_server() -> Server[Any]:
    async def list_tools(
        ctx: ServerRequestContext[Any, Any], params: PaginatedRequestParams | None
    ) -> ListToolsResult:
        return ListToolsResult(tools=[TOOL])

    async def call_tool(
        ctx: ServerRequestContext[Any, Any], params: CallToolRequestParams
    ) -> CallToolResult:
        doi = str((params.arguments or {}).get("doi"))
        if doi == BROKEN:
            return CallToolResult(content=[TextContent(type="text", text="boom")], is_error=True)
        if doi in RECORDS:
            return CallToolResult(content=[], structured_content=RECORDS[doi])
        return CallToolResult(content=[TextContent(type="text", text="no such DOI")])

    return Server("fake-doi", on_list_tools=list_tools, on_call_tool=call_tool)


def server(name: str) -> ToolServer:
    return ToolServer(
        name=name,
        url=f"http://127.0.0.1:8301/{name}",
        id_field="doi",
        canonicalisation=DOCUMENT_CANONICALISATION,
        tools_sha256=tools_digest([TOOL.model_dump(mode="json", by_alias=True, exclude_none=True)]),
        snapshot_ref=f"{name}:test",
    )


def run(tmp_path: Path, identifiers: list[str], *, granted: bool = True) -> Envelope:
    grants = {"advisor.linking": ["crossref"] if granted else []}
    conductor = make_conductor(
        tmp_path / "runs",
        LinkingAdviser(),
        profile=tools_profile(tmp_path, grants),
        gateway=fake_gateway(server("crossref"), serve=lambda _server: doi_server()),
    )
    env = conductor.invoke(
        request("advisor.linking", LinkCandidates(identifiers=identifiers)),
        acting_for=TEST_PRINCIPAL,
    )
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert conductor.grounding_reports[env.invocation_id].passed
    return env


def test_a_found_doi_carries_its_record_and_cites_it(tmp_path: Path) -> None:
    env = run(tmp_path, [KNOWN, f"https://doi.org/{KNOWN}"])
    payload = env.payload_as(RelatedIdentifiers)
    for link in payload.links:
        assert link.resolved is True
        assert link.title == "Data Director blueprint"
        assert link.resource_type == "report"
    # Both spellings name one record: it is cited once, as the conductor recorded it.
    assert [r.source_id for r in env.tool_retrievals] == [f"tool:crossref/{KNOWN}"] * 2
    assert [g.source_id for g in payload.grounded_on] == [f"tool:crossref/{KNOWN}"]
    assert [e.source_id for e in env.evidence] == [f"tool:crossref/{KNOWN}"]


@pytest.mark.parametrize("doi", ["10.1234/unknown", BROKEN])
def test_a_failed_lookup_is_recorded_on_the_link(tmp_path: Path, doi: str) -> None:
    env = run(tmp_path, [doi, KNOWN])
    failed, found = env.payload_as(RelatedIdentifiers).links
    assert failed.resolved is False
    assert failed.valid
    assert failed.message
    assert failed.title is None
    assert found.resolved is True


def test_only_a_well_formed_doi_is_looked_up(tmp_path: Path) -> None:
    env = run(tmp_path, ["0000-0002-1825-0097", "05krs5044", "EP/T012345/1", KNOWN])
    links = env.payload_as(RelatedIdentifiers).links
    assert [link.resolved for link in links] == [None, None, None, True]
    assert [r.tool_name for r in env.tool_retrievals] == [DOI_TOOL]


def test_without_a_grant_nothing_is_looked_up(tmp_path: Path) -> None:
    env = run(tmp_path, [KNOWN], granted=False)
    payload = env.payload_as(RelatedIdentifiers)
    assert env.tool_retrievals == []
    assert [link.resolved for link in payload.links] == [None]
    assert any("not resolved" in limitation for limitation in payload.limitations)
