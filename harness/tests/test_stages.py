"""A run's `stages.jsonl`: what its watchers were told, kept in order (docs/specs/storage.md,
invariant 5; docs/specs/transport.md), so a stored run can be replayed and debugged as the person
watching it saw it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dd_harness.storage import STAGES, RunStorage
from dd_harness.testing import (
    TEST_PRINCIPAL,
    ScriptedAgent,
    make_conductor,
    message,
    record,
    reply_over,
    request,
    review_of_input,
)
from dd_harness.testing.tools import ToolsPersona, fake_gateway, tools_profile
from dd_sdk.agent import AgentResult, RunContext
from dd_sdk.contract.models import GroundingMode, InvocationRequest


def stages_of(store: RunStorage, invocation_id: str) -> list[dict[str, Any]]:
    data = store.get_artifact(invocation_id, STAGES)
    assert data is not None
    return [json.loads(line) for line in data.decode().splitlines() if line]


def steps(records: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return [(r["event"], r["step"]) for r in records if r["event"].startswith("step_")]


def test_a_run_keeps_its_plan_each_stage_in_order_and_the_checks_reports(runs_dir: Path) -> None:
    agent = ScriptedAgent(GroundingMode.NONE, review_of_input)
    conductor = make_conductor(runs_dir, agent)
    env = conductor.invoke(request(agent.spec.agent_id), acting_for=TEST_PRINCIPAL)
    records = stages_of(conductor.store, env.invocation_id)

    assert records[0]["event"] == "plan"
    planned = [s["id"] for s in records[0]["steps"]]
    ran = steps(records)
    assert [step for event, step in ran if event == "step_started"] == planned
    assert [step for event, step in ran if event == "step_finished"] == planned
    reports = {r["event"]: r["report"] for r in records if "report" in r}
    assert set(reports) == {"grounding", "sources"}
    assert all(isinstance(report["passed"], bool) for report in reports.values())
    assert all(r["at"].endswith("Z") for r in records)


def test_a_run_refused_before_its_agent_keeps_no_agent_stage(runs_dir: Path) -> None:
    # A delegation agent accepts a Message, so a record is refused by the input check.
    agent = ScriptedAgent(GroundingMode.DELEGATION, review_of_input)
    conductor = make_conductor(runs_dir, agent)
    env = conductor.invoke(request(agent.spec.agent_id), acting_for=TEST_PRINCIPAL)
    started = [step for event, step in steps(stages_of(conductor.store, env.invocation_id))]
    assert "agent" not in started and "input" in started


def test_a_delegation_run_keeps_its_children(runs_dir: Path) -> None:
    def behaviour(req: InvocationRequest, ctx: RunContext) -> AgentResult:
        assert ctx.delegate is not None
        return reply_over(ctx, ctx.delegate("fake.none", record()))

    child = ScriptedAgent(GroundingMode.NONE, review_of_input)
    conductor = make_conductor(runs_dir, ScriptedAgent(GroundingMode.DELEGATION, behaviour), child)
    env = conductor.invoke(request("fake.delegation", message()), acting_for=TEST_PRINCIPAL)
    records = stages_of(conductor.store, env.invocation_id)
    [delegation] = env.delegations
    children = [r for r in records if r["event"].startswith("child_")]
    assert [r["event"] for r in children] == ["child_started", "child_finished"]
    assert {r["invocation_id"] for r in children} == {delegation.delegated_invocation_id}
    assert children[-1]["status"] == delegation.delegated_status.value


def test_a_tool_call_is_kept_by_name_only(runs_dir: Path) -> None:
    profile = tools_profile(runs_dir.parent, {"fake.tools": ["spdx"]})
    conductor = make_conductor(runs_dir, ToolsPersona(), profile=profile, gateway=fake_gateway())
    env = conductor.invoke(request("fake.tools", message("CC-BY-4.0")), acting_for=TEST_PRINCIPAL)
    records = stages_of(conductor.store, env.invocation_id)
    tools = [r for r in records if r["event"].startswith("tool_")]
    assert [r["event"] for r in tools] == ["tool_started", "tool_finished"]
    assert {r["name"] for r in tools} == {"spdx.get_licence"}
    # Neither the call's arguments nor what it returned are kept.
    assert "CC-BY-4.0" not in json.dumps(tools)
