"""The orchestrator through the real Anthropic client, replayed from a cassette: the tool loop
delegates and replies, and the model key reaches no envelope, span, RO-Crate or manifest
(ADR-0026, #43)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dd_agent_hello.agent import HelloWorld
from dd_agent_orchestrator import factory
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.agent import describe
from dd_sdk.contract.models import Derivation, Message, OutcomeStatus, Reply

# Distinctive enough that finding it anywhere means it leaked.
SENTINEL = "sk-ant-sentinel-0c4e8b2a9f1d7365"


@pytest.fixture(scope="module")
def vcr_config(vcr_config: dict[str, Any]) -> dict[str, Any]:
    # The conductor and its agents are served in memory; only the model calls come from the
    # cassette.
    def model_calls_only(request: Any) -> Any:
        return None if request.host.endswith(".test") else request

    return {**vcr_config, "before_record_request": model_calls_only}


@pytest.mark.vcr
@pytest.mark.requirement("DD-DELEGATION")
def test_the_orchestrator_key_reaches_no_stored_record(runs_dir: Path) -> None:
    built = factory.build({"ANTHROPIC_API_KEY": SENTINEL})
    conductor = make_conductor(runs_dir, built, HelloWorld(), crate=True)

    env = conductor.invoke(
        request("orchestrator.model", Message(message_text="Please greet Ada")),
        acting_for=TEST_PRINCIPAL,
    )

    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    payload = env.payload_as(Reply)
    assert payload.reply_derivation == Derivation.MODEL
    assert payload.reply_text == "The greeting agent says: Hello, Ada!"
    assert [d.delegated_agent_id for d in env.delegations] == ["hello.world"]
    assert env.telemetry.model_id == "claude-fable-5-1"
    # Cached input counts as input read.
    assert env.telemetry.input_tokens == 900 + 600 + 80 + 600
    assert conductor.grounding_reports[env.invocation_id].passed

    stored = [p for p in runs_dir.rglob("*") if p.is_file()]
    assert any(p.name == "ro-crate-metadata.json" for p in stored)
    for path in stored:
        assert SENTINEL.encode() not in path.read_bytes(), f"the key is in {path}"
    assert SENTINEL not in json.dumps(env.to_document())
    assert SENTINEL not in json.dumps(describe(built.spec))
