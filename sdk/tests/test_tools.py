"""What the card, the wire and an agent share about the tool gateway (`dd_sdk.tools`,
docs/specs/agents.md)."""

from __future__ import annotations

from typing import Any

import pytest

from dd_sdk.agent import AgentSpec, SpecError, describe, spec_from_description
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import GroundingMode, Message, Reply, tool_source_id
from dd_sdk.evidence import DOCUMENT_CANONICALISATION, content_hash
from dd_sdk.tools import (
    RECORDS_META,
    ToolGatewayError,
    ToolsGrant,
    ToolUse,
    records_from_result,
    split_name,
    tools_from_description,
)

pytestmark = pytest.mark.requirement("DD-TOOL-GATEWAY")


def _spec(*tools: ToolUse) -> AgentSpec:
    return AgentSpec(
        agent_id="fake.tools",
        version="0.1.0",
        description="Reads records through the tool gateway.",
        action_class="advise",
        accepts=(ClassSchema.of(Message),),
        grounding_mode=GroundingMode.RETRIEVAL,
        payload=ClassSchema.of(Reply),
        tools=tools,
    )


def test_a_card_carries_its_tools_and_reads_them_back() -> None:
    spec = _spec(ToolUse("spdx", ("get_licence", "search")))
    entry = describe(spec)
    assert entry["tools"] == [{"server": "spdx", "tools": ["get_licence", "search"]}]
    assert spec_from_description(entry).tools == spec.tools


def test_a_card_written_before_the_gateway_declares_no_tools() -> None:
    entry = describe(_spec())
    del entry["tools"]
    assert spec_from_description(entry).tools == ()


@pytest.mark.parametrize(
    "declared",
    [
        [{"server": "Bad Name", "tools": ["x"]}],
        [{"server": "spdx", "tools": []}],
        [{"server": "spdx", "tools": ["a.b"]}],
        [{"server": "spdx"}],
        [{"server": "spdx", "tools": ["x"]}, {"server": "spdx", "tools": ["y"]}],
    ],
)
def test_a_malformed_tools_declaration_is_refused(declared: list[dict[str, Any]]) -> None:
    with pytest.raises(ValueError, match=r"fake\.tools"):
        tools_from_description("fake.tools", {"tools": declared})
    entry = {**describe(_spec()), "tools": declared}
    with pytest.raises(SpecError):
        spec_from_description(entry)


def test_a_grant_travels_in_metadata_and_needs_both_parts() -> None:
    grant = ToolsGrant(url="http://harness.test/mcp", token="t")
    assert ToolsGrant.from_metadata(grant.metadata()) == grant
    assert ToolsGrant.from_metadata({"dd.tools_url": "http://harness.test/mcp"}) is None


def test_a_gateway_name_is_server_and_tool() -> None:
    assert split_name("spdx.get_licence") == ("spdx", "get_licence")
    with pytest.raises(ValueError):
        split_name("get_licence")


RECORD = {"licenseId": "CC-BY-4.0", "name": "Creative Commons Attribution 4.0"}


def _recorded(record: dict[str, Any], digest: str | None = None) -> dict[str, Any]:
    return {
        "source_id": tool_source_id("spdx", record["licenseId"]),
        "canonicalisation": DOCUMENT_CANONICALISATION,
        "content_hash": digest or content_hash(record, DOCUMENT_CANONICALISATION),
        "retrieved_at": "2026-11-18T12:00:00+00:00",
    }


def test_records_cite_what_the_gateway_recorded() -> None:
    (record,) = records_from_result(RECORD, {RECORDS_META: [_recorded(RECORD)]})
    assert record.ref().source_id == record.evidence().source_id == "tool:spdx/CC-BY-4.0"
    assert record.evidence().content == RECORD
    listed = {"records": [RECORD, {**RECORD, "licenseId": "MIT"}]}
    recorded = [_recorded(r) for r in listed["records"]]
    assert len(records_from_result(listed, {RECORDS_META: recorded})) == 2


def test_text_or_an_unrecorded_result_grounds_nothing() -> None:
    assert records_from_result(None, {RECORDS_META: [_recorded(RECORD)]}) == ()
    assert records_from_result(RECORD, None) == ()


def test_a_record_that_disagrees_with_the_gateway_is_refused() -> None:
    with pytest.raises(ToolGatewayError, match="hash"):
        records_from_result(RECORD, {RECORDS_META: [_recorded(RECORD, "0" * 64)]})
    with pytest.raises(ToolGatewayError, match="do not match"):
        records_from_result({"records": [RECORD]}, {RECORDS_META: [_recorded(RECORD)] * 2})
