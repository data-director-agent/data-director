"""advisor.rights retrieves its licences through the tool gateway (docs/specs/agents.md, Tools;
#877): the closed set the interpreter chooses from is what the gateway returned, the payload cites
the records the conductor recorded, and with no grant the packaged table stands, said so. Every
model is a `FakeModel` and the gateway is the harness's in-memory fake; no network, no key."""

from __future__ import annotations

from dataclasses import replace
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
)

from dd_agent_advisor_rights.agent import RightsAdviser, load_table
from dd_agent_advisor_rights.classes import RightsContext, RightsOptions
from dd_agent_advisor_rights.interpret import ModelInterpreter
from dd_agent_advisor_rights.retrieval import PACKAGED, TABLE_SOURCE
from dd_agent_advisor_rights.testing import rights_reply
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_harness.testing.tools import LICENCES, TOOLS, fake_gateway, tools_profile
from dd_sdk.contract.models import Envelope, GroundingMode, OutcomeStatus
from dd_sdk.model import declared
from dd_sdk.testing import FakeModel

TABLE_IDS = {row["spdx_id"] for row in load_table()["licences"]}
SERVED = set(LICENCES) & TABLE_IDS  # the fake server holds two of the table's five
GRANTED = {"advisor.rights": ["spdx"]}
NOT_SELL = "Anyone may use it, but not to sell it."


def run(
    tmp_path: Path,
    asked: RightsContext,
    agent: RightsAdviser | None = None,
    *,
    grant: bool = True,
    serve: Server[Any] | None = None,
) -> tuple[Envelope, bool]:
    agent = agent or RightsAdviser()
    conductor = make_conductor(
        tmp_path / "runs",
        agent,
        profile=tools_profile(tmp_path, GRANTED if grant else {}),
        gateway=fake_gateway(serve=(lambda _s: serve) if serve is not None else None),
    )
    env = conductor.invoke(request("advisor.rights", asked), acting_for=TEST_PRINCIPAL)
    return env, conductor.grounding_reports[env.invocation_id].passed


def offered(env: Envelope) -> list[str]:
    return [lic.spdx_id for lic in env.payload_as(RightsOptions).licences]


@pytest.mark.requirement("DD-TOOL-GATEWAY", "DD-GROUNDING-MODE")
def test_the_licences_offered_are_the_ones_the_gateway_returned_and_are_cited(
    tmp_path: Path,
) -> None:
    env, passed = run(tmp_path, RightsContext(reuse_wanted="any"))
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.grounding_mode == GroundingMode.RETRIEVAL
    assert passed
    assert offered(env) and set(offered(env)) <= SERVED
    kept = {r.source_id for r in env.tool_retrievals}
    assert kept == {f"tool:spdx/{i}" for i in SERVED}
    cited = {ref.source_id for ref in env.payload_as(RightsOptions).grounded_on}
    assert cited == {f"tool:spdx/{i}" for i in offered(env)}
    assert {ev.source_id for ev in env.evidence} == cited


@pytest.mark.requirement("DD-TOOL-GATEWAY")
def test_a_licence_the_gateway_did_not_return_is_left_out_and_recorded(tmp_path: Path) -> None:
    env, passed = run(tmp_path, RightsContext(reuse_wanted="any"))
    assert passed
    payload = env.payload_as(RightsOptions)
    missing = TABLE_IDS - SERVED
    assert missing and not missing & set(offered(env))
    assert any(all(i in text for i in missing) for text in payload.limitations)


@pytest.mark.requirement("DD-TOOL-GATEWAY", "DD-GROUNDING-MODE")
def test_a_model_chooses_only_from_what_the_gateway_returned(tmp_path: Path) -> None:
    # CC-BY-NC-4.0 is in the table but not served: the closed set no longer holds it.
    model = FakeModel([rights_reply(["non-commercial"], ["CC-BY-NC-4.0"])], model_id="fake-model")
    agent = RightsAdviser(interpreter=ModelInterpreter(model))
    agent.spec = replace(agent.spec, models=(declared(model),))
    env, passed = run(tmp_path, RightsContext(reuse_wanted=NOT_SELL), agent)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert passed
    assert "CC-BY-NC-4.0" not in offered(env)
    assert set(offered(env)) <= SERVED
    assert env.payload_as(RightsOptions).dropped


@pytest.mark.requirement("DD-TOOL-GATEWAY", "DD-GROUNDING-MODE")
def test_with_no_grant_the_packaged_table_stands_and_the_payload_says_so(tmp_path: Path) -> None:
    env, passed = run(tmp_path, RightsContext(reuse_wanted="any"), grant=False)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert passed
    assert env.tool_retrievals == []
    payload = env.payload_as(RightsOptions)
    assert set(offered(env)) == {
        r["spdx_id"] for r in load_table()["licences"] if "any" in r["fits"]
    }
    assert PACKAGED in payload.limitations
    assert [ref.source_id for ref in payload.grounded_on] == [TABLE_SOURCE]


def failing_server() -> Server[Any]:
    """A server that lists the fake's tools, as pinned, and reports an error from each call."""

    async def list_tools(
        ctx: ServerRequestContext[Any, Any], params: PaginatedRequestParams | None
    ) -> ListToolsResult:
        return ListToolsResult(tools=list(TOOLS))

    async def call_tool(
        ctx: ServerRequestContext[Any, Any], params: CallToolRequestParams
    ) -> CallToolResult:
        return CallToolResult(content=[TextContent(type="text", text="down")], is_error=True)

    return Server("failing-spdx", on_list_tools=list_tools, on_call_tool=call_tool)


@pytest.mark.requirement("DD-TOOL-GATEWAY")
def test_a_server_that_errors_leaves_the_packaged_table_not_an_exception(tmp_path: Path) -> None:
    env, passed = run(tmp_path, RightsContext(reuse_wanted="any"), serve=failing_server())
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert passed
    assert env.tool_retrievals == []
    payload = env.payload_as(RightsOptions)
    assert offered(env)
    assert [ref.source_id for ref in payload.grounded_on] == [TABLE_SOURCE]
    assert PACKAGED not in payload.limitations and payload.limitations[0]


@pytest.mark.requirement("DD-TOOL-GATEWAY")
def test_a_mandated_licence_outside_the_table_is_retrieved_and_cited(tmp_path: Path) -> None:
    env, passed = run(tmp_path, RightsContext(mandated_licence="MIT"))
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert passed
    assert offered(env) == ["MIT"]
    assert [ref.source_id for ref in env.payload_as(RightsOptions).grounded_on] == ["tool:spdx/MIT"]
