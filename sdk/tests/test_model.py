"""The model seam: one call opens the `chat` span, records its tokens and prompt, reports a
refusal and parses a structured reply, whoever serves the model (docs/specs/agents.md)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import BaseModel

from dd_sdk.agent import RunContext
from dd_sdk.model import ModelOutputError, Usage, call
from dd_sdk.model_anthropic import AnthropicModel
from dd_sdk.prompts import ModelCallLog, prompt_digest
from dd_sdk.testing import FakeModel
from dd_sdk.tracing import ATTR_INPUT_TOKENS, ATTR_MODEL_ID, ATTR_OUTPUT_TOKENS, CHAT

SYSTEM = "Answer briefly."
MESSAGES = [{"role": "user", "content": "What is the dataset?"}]


class Answer(BaseModel):
    summary: str
    files: int


@pytest.fixture
def exporter() -> InMemorySpanExporter:
    return InMemorySpanExporter()


@pytest.fixture
def ctx(exporter: InMemorySpanExporter) -> RunContext:
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return RunContext(tracer=provider.get_tracer("test"), input_ref="ref", input_hash="hash")


def chat_spans(exporter: InMemorySpanExporter) -> list[ReadableSpan]:
    return [s for s in exporter.get_finished_spans() if s.name == CHAT]


def test_a_call_returns_the_reply_and_records_it(
    ctx: RunContext, exporter: InMemorySpanExporter
) -> None:
    model = FakeModel("A soil survey.", answered_by="fake-model-2026")
    reply = call(model, ctx, system=SYSTEM, messages=MESSAGES)

    assert reply.text == "A soil survey."
    assert not reply.refused
    assert reply.parsed is None
    assert reply.model_id == "fake-model-2026"
    assert reply.usage == Usage(100, 40)

    [span] = chat_spans(exporter)
    assert span.attributes is not None
    assert span.attributes[ATTR_MODEL_ID] == "fake-model-2026"
    assert span.attributes[ATTR_INPUT_TOKENS] == 100
    assert span.attributes[ATTR_OUTPUT_TOKENS] == 40

    sent = {"system": SYSTEM, "messages": MESSAGES}
    [logged] = reply.calls.calls
    assert logged.model_provider == "fake"
    assert logged.model_id == "fake-model-2026"
    assert logged.prompt_digest == prompt_digest(sent)
    assert reply.calls.prompts == {prompt_digest(sent): sent}


def test_calls_in_one_run_share_a_log(ctx: RunContext) -> None:
    model = FakeModel(["first", "second"])
    log = ModelCallLog(model.provider)
    first = call(model, ctx, system=SYSTEM, messages=MESSAGES, calls=log)
    second = call(model, ctx, system=SYSTEM, messages=MESSAGES, calls=log)

    assert (first.text, second.text) == ("first", "second")
    assert first.calls is second.calls is log
    assert len(log.calls) == 2


def test_a_refusal_is_reported_and_not_parsed(ctx: RunContext) -> None:
    reply = call(FakeModel(refuse=True), ctx, system=SYSTEM, messages=MESSAGES, schema=Answer)

    assert reply.refused
    assert reply.parsed is None
    assert len(reply.calls.calls) == 1


def test_a_structured_reply_is_parsed(ctx: RunContext) -> None:
    model = FakeModel('{"summary": "A soil survey.", "files": 5}')
    reply = call(model, ctx, system=SYSTEM, messages=MESSAGES, schema=Answer)

    assert reply.parsed == Answer(summary="A soil survey.", files=5)
    assert model.sent[0].schema is Answer


def test_a_reply_that_is_not_the_schema_is_an_error_and_still_recorded(ctx: RunContext) -> None:
    with pytest.raises(ModelOutputError) as raised:
        call(FakeModel("not JSON"), ctx, system=SYSTEM, messages=MESSAGES, schema=Answer)

    assert raised.value.reply.text == "not JSON"
    assert len(raised.value.reply.calls.calls) == 1


class StubClient:
    """An Anthropic client that replies with `reply` and keeps what it was sent."""

    def __init__(self, reply: str, stop_reason: str = "end_turn", model: str | None = None):
        self.reply = reply
        self.stop_reason = stop_reason
        self.model = model
        self.sent: list[dict[str, Any]] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs: Any) -> SimpleNamespace:
        self.sent.append(kwargs)
        return SimpleNamespace(
            content=[
                SimpleNamespace(type="thinking", thinking="..."),
                SimpleNamespace(type="text", text=self.reply),
            ],
            stop_reason=self.stop_reason,
            usage=SimpleNamespace(input_tokens=12, output_tokens=3),
            model=self.model,
        )


def anthropic_model(client: StubClient) -> AnthropicModel:
    return AnthropicModel("claude-test", client=client)  # type: ignore[arg-type]


def test_the_anthropic_adapter_sends_the_messages_api_request(ctx: RunContext) -> None:
    client = StubClient("A soil survey.", model="claude-test-20261101")
    reply = call(anthropic_model(client), ctx, system=SYSTEM, messages=MESSAGES, max_tokens=512)

    [sent] = client.sent
    assert sent == {
        "model": "claude-test",
        "max_tokens": 512,
        "system": SYSTEM,
        "messages": MESSAGES,
    }
    assert reply.text == "A soil survey."
    assert reply.model_id == "claude-test-20261101"
    assert reply.usage == Usage(12, 3)
    assert reply.calls.calls[0].model_provider == "anthropic"


def test_the_anthropic_adapter_falls_back_to_the_model_asked_for(ctx: RunContext) -> None:
    reply = call(anthropic_model(StubClient("ok")), ctx, system=SYSTEM, messages=MESSAGES)
    assert reply.model_id == "claude-test"


def test_the_anthropic_adapter_asks_for_structured_output(ctx: RunContext) -> None:
    client = StubClient('{"summary": "A soil survey.", "files": 5}')
    reply = call(anthropic_model(client), ctx, system=SYSTEM, messages=MESSAGES, schema=Answer)

    output_format = client.sent[0]["output_config"]["format"]
    assert output_format["type"] == "json_schema"
    assert set(output_format["schema"]["properties"]) == {"summary", "files"}
    assert output_format["schema"]["additionalProperties"] is False
    assert reply.parsed == Answer(summary="A soil survey.", files=5)


def test_the_anthropic_adapter_reports_a_refusal(ctx: RunContext) -> None:
    client = StubClient("", stop_reason="refusal")
    reply = call(anthropic_model(client), ctx, system=SYSTEM, messages=MESSAGES)
    assert reply.refused


def test_the_anthropic_adapter_needs_a_key_or_a_client() -> None:
    with pytest.raises(ValueError, match="api_key"):
        AnthropicModel("claude-test")
