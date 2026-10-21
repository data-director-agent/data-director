"""The Data Director app against a scripted model: its reference configuration, one governed
tool call to R3 through the conductor, history, and start-up.

An alpha substantiates no requirement, so these tests carry no requirement marker.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai import models
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from dd_app.agent import R3_AGENT_ID, TOOL_NAME, Governance, build_agent, respond, to_history
from dd_app.config import settings_from_env
from dd_harness.identity import IdentityError
from dd_harness.testing import RESTRICTIVE, TEST_PRINCIPAL

models.ALLOW_MODEL_REQUESTS = False

SAMPLE = Path(__file__).resolve().parents[2] / "workbench/samples/soil-chemistry.profile.json"
PATH_VARIABLES = ("DD_PROFILE", "DD_AGENTS_CONFIG", "DD_SOURCES_CONFIG")


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """The app's reference set, a principal, and runs written under `tmp_path`."""
    for variable in PATH_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    for variable in ("DD_R3_RETRIEVAL", "DD_R3_EXPLAINER", "DD_SNAPSHOT_PATH"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("DD_PRINCIPAL_ID", TEST_PRINCIPAL.principal_id)
    monkeypatch.setenv("DD_PRINCIPAL_NAME", TEST_PRINCIPAL.name)
    monkeypatch.setenv("DD_RUNS_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def governance(env: Path) -> Iterator[Governance]:
    governance = Governance.create(settings_from_env())
    yield governance
    governance.worker.shutdown()


def recommending(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """Describe the sample dataset to the tool once, then cite the first record it returned."""
    returns = [
        p
        for m in messages
        if isinstance(m, ModelRequest)
        for p in m.parts
        if isinstance(p, ToolReturnPart)
    ]
    if not returns:
        profile = json.loads(SAMPLE.read_text(encoding="utf-8"))
        del profile["schema_class"]
        return ModelResponse(parts=[ToolCallPart(TOOL_NAME, profile)])
    result = returns[0].content
    assert isinstance(result, dict)
    if result["status"] != "succeeded":
        return ModelResponse(parts=[TextPart(f"Not available: {result['statement']}")])
    record = result["recommendations"][0]["records"][0]
    return ModelResponse(parts=[TextPart(f"See {record['name']}, {record['url']}")])


def test_the_reference_set_registers_r3_alone(governance: Governance):
    conductor = governance.conductor
    assert conductor.registry.ids() == [R3_AGENT_ID]
    assert conductor.profile.profile_id == "data-director-app"
    assert governance.acting_for == TEST_PRINCIPAL


def test_a_turn_calls_r3_through_the_conductor_and_records_the_run(
    governance: Governance, env: Path
):
    agent = build_agent(governance, FunctionModel(recommending))
    turn = asyncio.run(respond(agent, "Standards for my soil survey?", []))

    assert [c.tool_name for c in turn.tool_calls] == [TOOL_NAME]
    assert turn.answer.startswith("See ") and "https://fairsharing.org/" in turn.answer
    (invocation_id,) = turn.runs.values()
    stored = governance.conductor.store.get(invocation_id)
    assert stored is not None
    assert stored["agent_id"] == R3_AGENT_ID
    assert stored["outcome"]["status"] == "succeeded"
    assert stored["acting_for"]["principal_id"] == TEST_PRINCIPAL.principal_id
    assert governance.conductor.grounding_reports[invocation_id].passed
    assert (env / invocation_id).is_dir()


def test_a_profile_without_r3_refuses_and_the_model_is_told(
    env: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("DD_PROFILE", str(RESTRICTIVE))
    governance = Governance.create(settings_from_env())
    try:
        agent = build_agent(governance, FunctionModel(recommending))
        turn = asyncio.run(respond(agent, "Standards for my soil survey?", []))
    finally:
        governance.worker.shutdown()
    assert turn.answer.startswith("Not available: ")
    (invocation_id,) = turn.runs.values()
    stored: dict[str, Any] | None = governance.conductor.store.get(invocation_id)
    assert stored is not None and stored["outcome"]["status"] != "succeeded"


def test_no_principal_stops_start_up(env: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DD_PRINCIPAL_ID")
    with pytest.raises(IdentityError, match="DD_PRINCIPAL_ID"):
        Governance.create(settings_from_env())


def test_history_keeps_turns_and_drops_tool_notes():
    history = to_history(
        [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "`{}`", "metadata": {"title": "Tool: x"}},
            {"role": "assistant", "content": [{"type": "text", "text": "Hi"}]},
        ]
    )
    assert [type(m) for m in history] == [ModelRequest, ModelResponse]
    assert history[1].parts == [TextPart(content="Hi")]


def test_default_model_needs_a_key(governance: Governance, monkeypatch: pytest.MonkeyPatch):
    from pydantic_ai.exceptions import UserError

    monkeypatch.delenv("DD_CHAT_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(UserError):
        build_agent(governance)
