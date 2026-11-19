"""The orchestrator through the real Anthropic client, replayed from a cassette: the tool loop
delegates and replies, and the model key reaches no envelope, span, RO-Crate or manifest
(docs/specs/policy-and-identity.md, #43)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dd_agent_example_hello.agent import HelloWorld
from dd_agent_orchestrator_model import factory
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

    # The query is not matched: anthropic 2.3 stopped sending `?beta=true`, and the body is what
    # the test is about.
    return {
        **vcr_config,
        "before_record_request": model_calls_only,
        "match_on": ["method", "scheme", "host", "port", "path"],
    }


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
    assert [d.delegated_agent_id for d in env.delegations] == ["example.hello"]
    assert env.telemetry.model_id == "claude-sonnet-5-5"
    # The first turn is titled by the title model, its quotes and full stop removed.
    assert payload.conversation_title == "Greeting Ada"
    assert [c.model_id for c in env.telemetry.model_calls] == [
        "claude-sonnet-5-5",
        "claude-sonnet-5-5",
        "claude-haiku-5-5",
    ]
    # Cached input counts as input read; the title call's tokens count too.
    assert env.telemetry.input_tokens == 900 + 600 + 80 + 600 + 120
    assert conductor.grounding_reports[env.invocation_id].passed

    stored = [p for p in runs_dir.rglob("*") if p.is_file()]
    assert any(p.name == "ro-crate-metadata.json" for p in stored)
    for path in stored:
        assert SENTINEL.encode() not in path.read_bytes(), f"the key is in {path}"
    assert SENTINEL not in json.dumps(env.to_document())
    assert SENTINEL not in json.dumps(describe(built.spec))


# The `openai` package reads these from the process environment; none may reach a request.
AMBIENT_SENTINEL = "ambient-sentinel-5d1f0e9a"
AMBIENT = {
    "OPENAI_ADMIN_KEY": AMBIENT_SENTINEL,
    "OPENAI_ORG_ID": AMBIENT_SENTINEL,
    "OPENAI_PROJECT_ID": AMBIENT_SENTINEL,
    "OPENAI_BASE_URL": f"http://{AMBIENT_SENTINEL}.test/v1",
    "OPENAI_CUSTOM_HEADERS": f"Authorization: Bearer {AMBIENT_SENTINEL}",
}


def _completion(message: dict[str, Any], finish_reason: str) -> dict[str, Any]:
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 0,
        "model": "gpt-test-2026-11",
        "choices": [{"index": 0, "finish_reason": finish_reason, "message": message}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 5, "total_tokens": 55},
    }


@pytest.mark.requirement("DD-DELEGATION")
def test_on_openai_the_key_reaches_only_the_endpoint(
    runs_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same round trip on another provider (#831), its endpoint played by a mock transport:
    no real endpoint is called."""
    openai = pytest.importorskip("openai")
    import httpx2 as httpx

    greet = {
        "id": "call_1",
        "type": "function",
        "function": {"name": "example_hello", "arguments": json.dumps({"greeted_name": "Ada"})},
    }
    answers = [
        _completion({"role": "assistant", "content": None, "tool_calls": [greet]}, "tool_calls"),
        _completion(
            {"role": "assistant", "content": "The greeting agent says: Hello, Ada!"}, "stop"
        ),
        _completion({"role": "assistant", "content": "Greeting Ada"}, "stop"),
    ]
    requests: list[httpx.Request] = []

    def endpoint(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=answers.pop(0))

    original = openai.DefaultHttpxClient
    monkeypatch.setattr(
        openai, "DefaultHttpxClient", lambda: original(transport=httpx.MockTransport(endpoint))
    )
    for name, value in AMBIENT.items():
        monkeypatch.setenv(name, value)

    built = factory.build(
        {"DD_MODEL_PROVIDER": "openai", "DD_MODEL_ID": "gpt-test", "OPENAI_API_KEY": SENTINEL}
    )
    conductor = make_conductor(runs_dir, built, HelloWorld(), crate=True)
    env = conductor.invoke(
        request("orchestrator.model", Message(message_text="Please greet Ada")),
        acting_for=TEST_PRINCIPAL,
    )

    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    payload = env.payload_as(Reply)
    assert payload.reply_text == "The greeting agent says: Hello, Ada!"
    assert payload.conversation_title == "Greeting Ada"
    assert [d.delegated_agent_id for d in env.delegations] == ["example.hello"]
    assert [c.model_provider for c in env.telemetry.model_calls] == ["openai"] * 3
    assert conductor.grounding_reports[env.invocation_id].passed

    assert len(requests) == 3
    for sent in requests:
        assert sent.url.host == "api.openai.com"
        assert sent.headers["authorization"] == f"Bearer {SENTINEL}"
        assert AMBIENT_SENTINEL not in str(sent.headers)
    stored = [p for p in runs_dir.rglob("*") if p.is_file()]
    for path in stored:
        assert SENTINEL.encode() not in path.read_bytes(), f"the key is in {path}"
    assert SENTINEL not in json.dumps(env.to_document())
    assert SENTINEL not in json.dumps(describe(built.spec))
