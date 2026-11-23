"""A run's `withheld.json`: what the agent answered when a check withheld it (docs/specs/storage.md,
invariant 5). It is kept for operators and reaches no envelope or crate.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dd_harness.storage import CRATE, WITHHELD, RunStorage
from dd_harness.testing import (
    TEST_PRINCIPAL,
    Chat,
    ScriptedAgent,
    make_conductor,
    request,
    review_of_input,
)
from dd_sdk.agent import AgentResult, RunContext
from dd_sdk.contract.models import GroundingMode, InvocationRequest, OutcomeStatus


def withheld_of(store: RunStorage, invocation_id: str) -> dict[str, Any]:
    data = store.get_artifact(invocation_id, WITHHELD)
    assert data is not None
    found: dict[str, Any] = json.loads(data)
    return found


def _unregistered_canonicalisation(req: InvocationRequest, ctx: RunContext) -> AgentResult:
    result = review_of_input(req, ctx)
    evidence = [e.model_copy(update={"canonicalisation": "unregistered"}) for e in result.evidence]
    return AgentResult(outcome=result.outcome, payload=result.payload, evidence=evidence)


@pytest.mark.parametrize(
    ("agent", "problem"),
    [
        # A `none` agent that calls a model: the grounding linter withholds its result.
        (ScriptedAgent(GroundingMode.NONE, review_of_input, steps=[Chat()]), "grounding-violation"),
        # Evidence under a canonicalisation nobody registered: the contract check fails it.
        (ScriptedAgent(GroundingMode.NONE, _unregistered_canonicalisation), "agent-error"),
    ],
    ids=["grounding", "contract"],
)
def test_a_withheld_result_is_kept_for_operators_and_nowhere_else(
    runs_dir: Path, agent: ScriptedAgent, problem: str
) -> None:
    conductor = make_conductor(runs_dir, agent, crate=True)
    env = conductor.invoke(request(agent.spec.agent_id), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.FAILED
    assert env.problem is not None and env.problem.type.endswith(f"/{problem}")

    kept = withheld_of(conductor.store, env.invocation_id)
    assert kept["outcome"]["status"] == "succeeded"
    assert kept["payload"] is not None and kept["evidence"]
    assert kept["invocation_id"] == env.invocation_id

    # The record a researcher reads carries none of it.
    stored = conductor.store.get(env.invocation_id)
    assert stored is not None
    assert stored.get("payload") is None and not stored.get("evidence")
    payload = json.dumps(kept["payload"], sort_keys=True)
    run_dir = runs_dir / env.invocation_id
    for path in (run_dir / CRATE).rglob("*"):
        if path.is_file():
            assert "withheld" not in path.name
            assert payload not in path.read_text(encoding="utf-8", errors="replace"), path


def test_a_result_that_passes_keeps_nothing_withheld(runs_dir: Path) -> None:
    agent = ScriptedAgent(GroundingMode.NONE, review_of_input)
    conductor = make_conductor(runs_dir, agent)
    env = conductor.invoke(request(agent.spec.agent_id), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED
    assert conductor.store.get_artifact(env.invocation_id, WITHHELD) is None
