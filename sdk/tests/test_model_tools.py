"""Tool calling through the model seam: each adapter translates the SDK's tool types to its
provider's format and back, sends back what its provider requires unchanged, and reports why the
model stopped; a provider's failure is a `ModelCallError` (#831, docs/specs/orchestration.md)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import httpx2 as httpx
import pytest
from opentelemetry.sdk.trace import TracerProvider

from dd_sdk.agent import RunContext
from dd_sdk.model import (
    AssistantMessage,
    CallOptions,
    ModelCallError,
    ModelMessage,
    Replay,
    ToolCall,
    ToolResult,
    ToolResults,
    ToolSpec,
    call,
)
from dd_sdk.model_anthropic import FALLBACK_BETA, AnthropicModel, ToolLoopOptions
from dd_sdk.model_openai import OpenAIModel, OpenAIOptions, openai_client

BASE = "http://endpoint.test/v1"
GREET = ToolSpec(
    "greet",
    "Greet someone.",
    {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
)


@pytest.fixture
def ctx() -> RunContext:
    return RunContext(tracer=TracerProvider().get_tracer("test"), input_ref="r", input_hash="h")


def conversation(replay: Replay | None = None) -> list[ModelMessage]:
    """A user message, a turn that called `greet`, and its result."""
    made = ToolCall("call_1", "greet", {"name": "Ada"})
    return [
        {"role": "user", "content": "Greet Ada"},
        AssistantMessage("Asking.", (made,), replay),
        ToolResults((ToolResult("call_1", "Hello, Ada!"), ToolResult("call_2", "no", True))),
    ]


# --- Anthropic ---------------------------------------------------------------------------------


class Block(SimpleNamespace):
    def model_dump(self, **_: Any) -> dict[str, Any]:
        return {k: v for k, v in vars(self).items() if v is not None}


class Claude:
    """Stands in for `anthropic.Anthropic`, answering with `content` and keeping each request."""

    def __init__(self, content: list[Block], stop_reason: str = "end_turn") -> None:
        self.content = content
        self.stop_reason = stop_reason
        self.requests: list[dict[str, Any]] = []
        self.messages = SimpleNamespace(create=self._create)
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs: Any) -> SimpleNamespace:
        self.requests.append(kwargs)
        usage = SimpleNamespace(
            input_tokens=10,
            output_tokens=4,
            cache_read_input_tokens=100,
            cache_creation_input_tokens=5,
        )
        return SimpleNamespace(
            content=self.content,
            stop_reason=self.stop_reason,
            stop_details=None,
            model="claude-test",
            usage=usage,
        )


def test_claude_is_sent_tools_results_and_its_own_turn_back(ctx: RunContext) -> None:
    thinking = {"type": "thinking", "thinking": "...", "signature": "sig"}
    client = Claude([Block(type="text", text="Hello, Ada!")])
    model = AnthropicModel(
        "claude-test",
        client=client,  # type: ignore[arg-type]
        options=ToolLoopOptions(effort="high", fallback=True),
    )

    replay = Replay("anthropic", (thinking, {"type": "tool_use", "id": "call_1"}))
    reply = call(
        model,
        ctx,
        system="s",
        messages=conversation(replay),
        options=CallOptions(tools=[GREET], tool_choice="none"),
    )

    [sent] = client.requests
    assert sent["tools"] == [GREET.to_json()]
    assert sent["tool_choice"] == {"type": "none"}
    assert sent["output_config"] == {"effort": "high"}
    assert sent["betas"] == [FALLBACK_BETA] and sent["fallbacks"] == "default"
    _user, assistant, results = sent["messages"]
    # The turn goes back as Claude returned it, thinking included.
    assert assistant == {"role": "assistant", "content": [thinking, replay.content[1]]}
    assert results["role"] == "user"
    assert [(r["type"], r["tool_use_id"], r["is_error"]) for r in results["content"]] == [
        ("tool_result", "call_1", False),
        ("tool_result", "call_2", True),
    ]
    assert reply.stop == "end_turn" and reply.text == "Hello, Ada!"
    # Cached input is input the model read.
    assert reply.usage.input_tokens == 115


def test_claude_is_sent_a_turn_from_another_provider_rebuilt(ctx: RunContext) -> None:
    client = Claude([Block(type="text", text="Done.")])
    model = AnthropicModel("claude-test", client=client)  # type: ignore[arg-type]
    call(
        model,
        ctx,
        system="s",
        messages=conversation(Replay("openai", {})),
        options=CallOptions(tools=[GREET]),
    )
    _, assistant, _ = client.requests[0]["messages"]
    assert assistant["content"] == [
        {"type": "text", "text": "Asking."},
        {"type": "tool_use", "id": "call_1", "name": "greet", "input": {"name": "Ada"}},
    ]


def test_claudes_tool_calls_are_read_and_its_turn_kept(ctx: RunContext) -> None:
    blocks = [
        Block(type="thinking", thinking="...", signature="sig"),
        Block(type="tool_use", id="toolu_1", name="greet", input={"name": "Ada"}),
    ]
    model = AnthropicModel("claude-test", client=Claude(blocks, "tool_use"))  # type: ignore[arg-type]
    reply = call(
        model, ctx, system="s", messages=conversation()[:1], options=CallOptions(tools=[GREET])
    )
    assert reply.stop == "tool_use"
    assert reply.tool_calls == (ToolCall("toolu_1", "greet", {"name": "Ada"}),)
    assert reply.message.replay is not None and reply.message.replay.provider == "anthropic"
    assert [b["type"] for b in reply.message.replay.content] == ["thinking", "tool_use"]


def test_a_plain_claude_call_is_unchanged(ctx: RunContext) -> None:
    client = Claude([Block(type="text", text="Hi")])
    model = AnthropicModel("claude-test", client=client)  # type: ignore[arg-type]
    call(model, ctx, system="s", messages=[{"role": "user", "content": "x"}])
    [sent] = client.requests
    assert set(sent) == {"model", "max_tokens", "system", "messages"}


def test_claudes_failure_is_a_model_call_error(ctx: RunContext) -> None:
    anthropic = pytest.importorskip("anthropic")

    class Failing(Claude):
        def _create(self, **kwargs: Any) -> SimpleNamespace:
            request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
            raise anthropic.APIConnectionError(request=request)

    model = AnthropicModel("claude-test", client=Failing([]))  # type: ignore[arg-type]
    with pytest.raises(ModelCallError, match="could not be reached"):
        call(model, ctx, system="s", messages=[{"role": "user", "content": "x"}])


# --- OpenAI-compatible -------------------------------------------------------------------------


def completion(message: dict[str, Any], finish_reason: str = "stop") -> dict[str, Any]:
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 0,
        "model": "model-2026-11",
        "choices": [{"index": 0, "finish_reason": finish_reason, "message": message}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17},
    }


class Endpoint:
    """A Chat Completions endpoint that answers with `answer` (or `status`) and keeps each body."""

    def __init__(self, answer: dict[str, Any], status: int = 200) -> None:
        self.answer = answer
        self.status = status
        self.bodies: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.bodies.append(json.loads(request.content))
        return httpx.Response(self.status, json=self.answer)

    def model(self, **options: Any) -> OpenAIModel:
        import openai

        http_client = openai.DefaultHttpxClient(transport=httpx.MockTransport(self))
        client = openai_client(BASE, "key", http_client=http_client)
        return OpenAIModel("model", provider="gemini", hosting="hosted", client=client, **options)


def tool_call(arguments: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": "call_9",
        "type": "function",
        "function": {"name": "greet", "arguments": arguments},
        **extra,
    }


def test_an_endpoint_is_sent_function_tools_results_and_a_rebuilt_turn(ctx: RunContext) -> None:
    pytest.importorskip("openai")
    endpoint = Endpoint(completion({"role": "assistant", "content": "Hello, Ada!"}))
    reply = call(
        endpoint.model(options=OpenAIOptions(effort="low")),
        ctx,
        system="s",
        messages=conversation(),
        options=CallOptions(tools=[GREET], tool_choice="auto"),
    )
    [body] = endpoint.bodies
    assert body["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "greet",
                "description": "Greet someone.",
                "parameters": dict(GREET.input_schema),
            },
        }
    ]
    assert body["tool_choice"] == "auto"
    assert body["reasoning_effort"] == "low"
    system, _user, assistant, first, second = body["messages"]
    assert system == {"role": "system", "content": "s"}
    assert assistant["tool_calls"] == [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "greet", "arguments": json.dumps({"name": "Ada"})},
        }
    ]
    assert first == {"role": "tool", "tool_call_id": "call_1", "content": "Hello, Ada!"}
    # The format has no error flag; the content says so.
    assert second["tool_call_id"] == "call_2" and second["content"].startswith("Error: ")
    assert reply.stop == "end_turn" and reply.text == "Hello, Ada!"


def test_an_endpoints_tool_calls_are_read_and_its_signatures_sent_back(ctx: RunContext) -> None:
    pytest.importorskip("openai")
    signed = tool_call('{"name": "Ada"}', extra_content={"google": {"thought_signature": "s1"}})
    answer = completion(
        {"role": "assistant", "content": None, "tool_calls": [signed]}, "tool_calls"
    )
    endpoint = Endpoint(answer)
    model = endpoint.model()
    reply = call(
        model, ctx, system="s", messages=conversation()[:1], options=CallOptions(tools=[GREET])
    )
    assert reply.stop == "tool_use"
    assert reply.tool_calls == (ToolCall("call_9", "greet", {"name": "Ada"}),)

    # The next call sends the turn back with the field the server added.
    endpoint.answer = completion({"role": "assistant", "content": "Done."})
    call(
        model,
        ctx,
        system="s",
        messages=[*conversation()[:1], reply.message],
        options=CallOptions(tools=[GREET]),
    )
    sent = endpoint.bodies[-1]["messages"][-1]
    assert sent["tool_calls"] == [signed]


def test_tool_calls_ended_with_stop_are_still_tool_calls(ctx: RunContext) -> None:
    pytest.importorskip("openai")
    answer = completion({"role": "assistant", "content": None, "tool_calls": [tool_call("{}")]})
    reply = call(
        Endpoint(answer).model(),
        ctx,
        system="s",
        messages=conversation()[:1],
        options=CallOptions(tools=[GREET]),
    )
    assert reply.stop == "tool_use"


@pytest.mark.parametrize("arguments", ["{not json", "[1, 2]", '"Ada"'])
def test_arguments_that_are_not_an_object_are_a_problem_not_a_crash(
    ctx: RunContext, arguments: str
) -> None:
    pytest.importorskip("openai")
    answer = completion(
        {"role": "assistant", "content": None, "tool_calls": [tool_call(arguments)]}, "tool_calls"
    )
    reply = call(
        Endpoint(answer).model(),
        ctx,
        system="s",
        messages=conversation()[:1],
        options=CallOptions(tools=[GREET]),
    )
    [made] = reply.tool_calls
    assert made.input == {} and made.problem


@pytest.mark.parametrize(
    ("finish_reason", "stop"), [("length", "max_tokens"), ("content_filter", "refusal")]
)
def test_why_an_endpoint_stopped_is_reported(
    ctx: RunContext, finish_reason: str, stop: str
) -> None:
    pytest.importorskip("openai")
    answer = completion({"role": "assistant", "content": "Part"}, finish_reason)
    reply = call(
        Endpoint(answer).model(),
        ctx,
        system="s",
        messages=conversation()[:1],
        options=CallOptions(tools=[GREET]),
    )
    assert reply.stop == stop


def test_an_endpoints_failure_is_a_model_call_error(ctx: RunContext) -> None:
    pytest.importorskip("openai")
    endpoint = Endpoint({"error": {"message": "tools are not supported"}}, status=400)
    with pytest.raises(ModelCallError, match="400"):
        call(
            endpoint.model(),
            ctx,
            system="s",
            messages=conversation()[:1],
            options=CallOptions(tools=[GREET]),
        )


def test_the_record_holds_the_neutral_conversation_and_the_tools(ctx: RunContext) -> None:
    pytest.importorskip("openai")
    endpoint = Endpoint(completion({"role": "assistant", "content": "Hi"}))
    reply = call(
        endpoint.model(),
        ctx,
        system="s",
        messages=conversation(),
        options=CallOptions(tools=[GREET]),
    )
    [prompt] = reply.calls.prompts.values()
    assert prompt["tools"] == [GREET.to_json()] and prompt["tool_choice"] == "auto"
    assert prompt["messages"][1]["tool_calls"] == [
        {"id": "call_1", "name": "greet", "input": {"name": "Ada"}}
    ]
    assert prompt["messages"][2]["role"] == "tool"
