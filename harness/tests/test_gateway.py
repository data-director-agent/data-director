"""The tool gateway (docs/specs/agents.md, Tools; docs/specs/grounding.md, invariant 15): a persona
reaches an MCP server only through the harness, over the in-memory MCP wire, and the conductor
records what the tools returned.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from dd_harness import grounding
from dd_harness import sources as source_check
from dd_harness.conductor import Conductor
from dd_harness.gateway.config import ToolConfigError, load_servers
from dd_harness.gateway.core import ToolCallError
from dd_harness.policy import PolicyError, load_profile, withheld
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, message
from dd_harness.testing.tools import (
    LICENCES,
    ToolsPersona,
    cite,
    fake_gateway,
    read_licence,
    spdx_server,
    tools_profile,
)
from dd_sdk.agent import AgentResult, RunContext
from dd_sdk.contract.models import Envelope, InvocationRequest, OutcomeStatus
from dd_sdk.evidence import DOCUMENT_CANONICALISATION, content_hash
from dd_sdk.tools import ToolGatewayError, ToolUse
from dd_sdk.tracing import EXECUTE_TOOL, INVOKE_AGENT, chat_span, records_from_jsonl, retrieval_span

pytestmark = pytest.mark.requirement("DD-TOOL-GATEWAY")

GRANTED = {"fake.tools": ["spdx"]}


def conductor(
    tmp_path: Path, persona: ToolsPersona, grants: dict[str, list[str]] = GRANTED
) -> Conductor:
    return make_conductor(
        tmp_path / "runs", persona, profile=tools_profile(tmp_path, grants), gateway=fake_gateway()
    )


def run(c: Conductor, text: str = "CC-BY-4.0") -> Envelope:
    request = InvocationRequest(agent_id="fake.tools", input=message(text))
    return c.invoke(request, acting_for=TEST_PRINCIPAL)


def stored(tmp_path: Path, envelope: Envelope) -> tuple[dict[str, object], list[dict[str, object]]]:
    run_dir = tmp_path / "runs" / envelope.invocation_id
    spans = [json.loads(line) for line in (run_dir / "spans.jsonl").read_text().splitlines()]
    return json.loads((run_dir / "envelope.json").read_text()), spans


def test_a_persona_retrieves_through_the_gateway_and_is_grounded_on_its_record(
    tmp_path: Path,
) -> None:
    envelope = run(conductor(tmp_path, ToolsPersona()))
    assert envelope.outcome.status == OutcomeStatus.SUCCEEDED
    (kept,) = envelope.tool_retrievals
    assert kept.source_id == "tool:spdx/CC-BY-4.0"
    assert kept.content_hash == content_hash(LICENCES["CC-BY-4.0"], DOCUMENT_CANONICALISATION)
    assert [ev.source_id for ev in envelope.evidence] == [kept.source_id]

    document, spans = stored(tmp_path, envelope)
    records = records_from_jsonl(spans)
    assert grounding.lint(records, document).passed
    # The call is the conductor's span, a child of the invocation's root.
    root = next(r for r in records if r.name == INVOKE_AGENT)
    calls = [r for r in records if r.name == EXECUTE_TOOL]
    assert calls and all(r.parent_id == root.span_id for r in calls)
    # The conductor's record is not looked up again in a pinned copy.
    assert source_check.check(document, source_check.Sources.none()).unresolved == []


def test_each_record_of_a_listed_result_is_recorded(tmp_path: Path) -> None:
    def search(request: InvocationRequest, ctx: RunContext) -> AgentResult:
        assert ctx.tools is not None
        found = ctx.tools.call("spdx", "search_licences", {"text": "i"})
        return cite(found.records, "searched")

    envelope = run(conductor(tmp_path, ToolsPersona(search)))
    assert envelope.outcome.status == OutcomeStatus.SUCCEEDED
    assert {r.source_id for r in envelope.tool_retrievals} == {
        f"tool:spdx/{licence}" for licence in LICENCES
    }


def test_text_from_a_tool_grounds_nothing(tmp_path: Path) -> None:
    def describe(request: InvocationRequest, ctx: RunContext) -> AgentResult:
        assert ctx.tools is not None
        said = ctx.tools.call("spdx", "describe", {"id": "MIT"})
        assert said.text and not said.records
        return cite(said.records, said.text)

    envelope = run(conductor(tmp_path, ToolsPersona(describe)))
    assert envelope.tool_retrievals == []
    assert envelope.outcome.status == OutcomeStatus.FAILED  # G2: rests on nothing


def test_a_tool_the_card_does_not_declare_is_refused(tmp_path: Path) -> None:
    def search(request: InvocationRequest, ctx: RunContext) -> AgentResult:
        assert ctx.tools is not None
        assert [t["name"] for t in ctx.tools.listed()] == ["spdx.get_licence"]
        with pytest.raises(ToolGatewayError):
            ctx.tools.call("spdx", "search_licences", {"text": "MIT"})
        return read_licence(request, ctx)

    persona = ToolsPersona(search, tools=(ToolUse("spdx", ("get_licence",)),))
    envelope = run(conductor(tmp_path, persona))
    assert envelope.outcome.status == OutcomeStatus.SUCCEEDED
    assert [r.tool_name for r in envelope.tool_retrievals] == ["get_licence"]


def test_an_agent_the_profile_grants_no_server_gets_no_tools(tmp_path: Path) -> None:
    seen: list[object] = []

    def look(request: InvocationRequest, ctx: RunContext) -> AgentResult:
        seen.append(ctx.tools)
        return cite((), "nothing")

    run(conductor(tmp_path, ToolsPersona(look), grants={}))
    assert seen == [None]


def test_a_server_whose_tools_changed_is_unavailable(tmp_path: Path) -> None:
    changed = spdx_server(pin="0" * 64)
    gateway = fake_gateway(changed)
    assert "spdx" not in gateway.available
    assert "changed" in gateway.unavailable["spdx"]
    seen: list[object] = []

    def look(request: InvocationRequest, ctx: RunContext) -> AgentResult:
        seen.append(ctx.tools)
        return cite((), "nothing")

    c = make_conductor(
        tmp_path / "runs",
        ToolsPersona(look),
        profile=tools_profile(tmp_path, GRANTED),
        gateway=gateway,
    )
    run(c)
    assert seen == [None]


def test_a_grant_expires_with_its_invocation(tmp_path: Path) -> None:
    tokens: list[str] = []

    def keep(request: InvocationRequest, ctx: RunContext) -> AgentResult:
        assert ctx.tools is not None
        tokens.append(ctx.tools.grant.token)  # type: ignore[attr-defined]
        return read_licence(request, ctx)

    c = conductor(tmp_path, ToolsPersona(keep))
    run(c)
    assert c.gateway is not None
    with pytest.raises(ToolCallError, match="expired"):
        asyncio.run(c.gateway.call(tokens[0], "spdx.get_licence", {"id": "MIT"}))


def test_an_agents_own_span_for_a_tool_source_counts_for_nothing(tmp_path: Path) -> None:
    record = LICENCES["MIT"]
    digest = content_hash(record, DOCUMENT_CANONICALISATION)

    def forge(request: InvocationRequest, ctx: RunContext) -> AgentResult:
        with retrieval_span(ctx.tracer, "tool:spdx/MIT", digest):
            pass
        assert ctx.tools is not None
        real = ctx.tools.call("spdx", "get_licence", {"id": "CC-BY-4.0"}).records[0]
        forged = type(real)("tool:spdx/MIT", DOCUMENT_CANONICALISATION, digest, record)
        return cite((forged,), "forged")

    c = conductor(tmp_path, ToolsPersona(forge))
    envelope = run(c)
    assert envelope.outcome.status == OutcomeStatus.FAILED
    violations = c.grounding_reports[envelope.invocation_id].violations
    assert any(v.startswith("G2") for v in violations)


def test_a_model_call_before_the_first_tool_record_breaks_g1(tmp_path: Path) -> None:
    def hasty(request: InvocationRequest, ctx: RunContext) -> AgentResult:
        with chat_span(ctx.tracer, "fake-model"):
            pass
        return read_licence(request, ctx)

    c = conductor(tmp_path, ToolsPersona(hasty))
    envelope = run(c)
    assert envelope.outcome.status == OutcomeStatus.FAILED
    assert any(v.startswith("G1") for v in c.grounding_reports[envelope.invocation_id].violations)


def test_records_are_kept_when_the_run_fails(tmp_path: Path) -> None:
    def fail(request: InvocationRequest, ctx: RunContext) -> AgentResult:
        read_licence(request, ctx)
        raise RuntimeError("after the call")

    envelope = run(conductor(tmp_path, ToolsPersona(fail)))
    assert envelope.outcome.status == OutcomeStatus.FAILED
    assert [r.source_id for r in envelope.tool_retrievals] == ["tool:spdx/CC-BY-4.0"]


def test_a_profile_granting_a_server_the_deployment_does_not_list_is_refused(
    tmp_path: Path,
) -> None:
    with pytest.raises(PolicyError, match="does not list"):
        make_conductor(
            tmp_path / "runs",
            ToolsPersona(),
            profile=tools_profile(tmp_path, {"fake.tools": ["orcid"]}),
            gateway=fake_gateway(),
        )


def test_a_profile_granting_servers_to_an_agent_it_does_not_enable_is_refused(
    tmp_path: Path,
) -> None:
    with pytest.raises(PolicyError, match="does not enable"):
        load_profile(tools_profile(tmp_path, {"advisor.unknown": ["spdx"]}))


def test_a_remote_server_withholds_what_the_profile_keeps_from_it(tmp_path: Path) -> None:
    profile = load_profile(tools_profile(tmp_path, GRANTED, remote_tool_content=["inventory"]))
    given = ["inventory", "researcher", "documentation"]
    assert withheld(profile, [], given, remote_tools=True) == ["documentation", "researcher"]
    assert withheld(profile, [], given) == []
    spec = ToolsPersona().spec
    assert fake_gateway(spdx_server(remote=True)).remote(spec, ["spdx"])
    assert not fake_gateway().remote(spec, ["spdx"])
    default = load_profile(tools_profile(tmp_path, GRANTED))
    assert withheld(default, [], given, remote_tools=True) == ["researcher"]


@pytest.mark.parametrize(
    "servers",
    [
        "servers: {}",
        "servers:\n  - {name: spdx, url: http://127.0.0.1/mcp}",
        "servers:\n  - {name: spdx, url: u, id_field: id, canonicalisation: nope, "
        f"tools_sha256: {'0' * 64}}}",
        "servers:\n"
        + "\n".join(
            f"  - {{name: spdx, url: u, id_field: id, canonicalisation: "
            f"{DOCUMENT_CANONICALISATION}, tools_sha256: {'0' * 64}}}"
            for _ in range(2)
        ),
    ],
    ids=["not-a-list", "missing-keys", "unregistered-canonicalisation", "name-twice"],
)
def test_a_malformed_list_of_servers_is_refused(tmp_path: Path, servers: str) -> None:
    path = tmp_path / "tools.yaml"
    path.write_text(servers, encoding="utf-8")
    with pytest.raises(ToolConfigError):
        load_servers(path)
