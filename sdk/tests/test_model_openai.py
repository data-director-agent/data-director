"""The adapter for OpenAI-compatible endpoints: what it sends, what it reads back, and that only the
key it was given ever leaves the process (docs/specs/policy-and-identity.md)."""

from __future__ import annotations

import json
from typing import Any

import httpx2 as httpx
import pytest
from opentelemetry.sdk.trace import TracerProvider
from pydantic import BaseModel

from dd_sdk.agent import RunContext
from dd_sdk.model import ModelOutputError, Usage, call
from dd_sdk.model_openai import OpenAIModel, openai_client

pytest.importorskip("openai")

BASE = "http://endpoint.test/v1"
SENTINEL = "sentinel-must-not-be-sent"
# Everything the `openai` package would read from the environment if it were let.
AMBIENT = {
    "OPENAI_API_KEY": SENTINEL,
    "OPENAI_ADMIN_KEY": SENTINEL,
    "OPENAI_ORG_ID": SENTINEL,
    "OPENAI_PROJECT_ID": SENTINEL,
    "OPENAI_BASE_URL": f"http://{SENTINEL}.test/v1",
    "OPENAI_CUSTOM_HEADERS": f"X-Ambient: {SENTINEL}\nAuthorization: Bearer {SENTINEL}",
}


class Answer(BaseModel):
    summary: str
    files: int


@pytest.fixture
def ctx() -> RunContext:
    return RunContext(tracer=TracerProvider().get_tracer("test"), input_ref="r", input_hash="h")


def completion(
    content: str | None = "A soil survey.", refusal: str | None = None
) -> dict[str, Any]:
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 0,
        "model": "model-2026-11",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": content, "refusal": refusal},
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17},
    }


class Endpoint:
    """A Chat Completions endpoint that answers with `answer` and keeps every request."""

    def __init__(self, answer: dict[str, Any]) -> None:
        self.answer = answer
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(200, json=self.answer)

    def model(self, api_key: str | None = "explicit-key", **options: Any) -> OpenAIModel:
        import openai

        http_client = openai.DefaultHttpxClient(transport=httpx.MockTransport(self))
        options.setdefault("provider", "openai")
        options.setdefault("hosting", "hosted")
        return OpenAIModel(
            "model", client=openai_client(BASE, api_key, http_client=http_client), **options
        )

    @property
    def body(self) -> dict[str, Any]:
        body: dict[str, Any] = json.loads(self.requests[-1].content)
        return body


def test_the_request_is_a_chat_completion_with_the_system_prompt_first(ctx: RunContext) -> None:
    endpoint = Endpoint(completion())
    model = endpoint.model(max_tokens_field="max_completion_tokens")
    reply = call(model, ctx, system="Be brief.", messages=[{"role": "user", "content": "Hi"}])

    assert str(endpoint.requests[-1].url) == f"{BASE}/chat/completions"
    body = endpoint.body
    assert body["model"] == "model"
    assert body["messages"] == [
        {"role": "system", "content": "Be brief."},
        {"role": "user", "content": "Hi"},
    ]
    assert body["max_completion_tokens"] > 0
    assert "max_tokens" not in body
    assert reply.text == "A soil survey."
    assert reply.model_id == "model-2026-11"
    assert reply.usage == Usage(12, 5)
    assert not reply.refused


def test_a_refusal_is_reported(ctx: RunContext) -> None:
    endpoint = Endpoint(completion(content=None, refusal="I can't help with that."))
    reply = call(endpoint.model(), ctx, system="s", messages=[{"role": "user", "content": "x"}])
    assert reply.refused
    assert reply.text == ""


def test_structured_output_asks_for_a_strict_schema_and_is_parsed(ctx: RunContext) -> None:
    endpoint = Endpoint(completion(content='{"summary": "soil", "files": 3}'))
    reply = call(
        endpoint.model(),
        ctx,
        system="s",
        messages=[{"role": "user", "content": "x"}],
        schema=Answer,
    )
    response_format = endpoint.body["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert reply.parsed == Answer(summary="soil", files=3)


def test_a_reply_that_is_not_the_schema_is_recorded_then_refused(ctx: RunContext) -> None:
    endpoint = Endpoint(completion(content="not JSON"))
    with pytest.raises(ModelOutputError) as caught:
        call(
            endpoint.model(),
            ctx,
            system="s",
            messages=[{"role": "user", "content": "x"}],
            schema=Answer,
        )
    assert caught.value.reply.calls.calls


def test_only_text_messages_are_sent(ctx: RunContext) -> None:
    endpoint = Endpoint(completion())
    with pytest.raises(TypeError):
        call(
            endpoint.model(),
            ctx,
            system="s",
            messages=[{"role": "user", "content": [{"type": "text", "text": "x"}]}],
        )


def test_only_the_explicit_key_is_sent(ctx: RunContext, monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in AMBIENT.items():
        monkeypatch.setenv(name, value)
    endpoint = Endpoint(completion())
    call(endpoint.model(), ctx, system="s", messages=[{"role": "user", "content": "x"}])

    request = endpoint.requests[-1]
    assert request.url.host == "endpoint.test"
    assert request.headers["authorization"] == "Bearer explicit-key"
    assert SENTINEL not in str(request.url)
    assert all(SENTINEL not in value for value in request.headers.values())
    assert SENTINEL.encode() not in request.content


def test_a_local_endpoint_without_a_key_is_sent_no_authorization(
    ctx: RunContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name, value in AMBIENT.items():
        monkeypatch.setenv(name, value)
    endpoint = Endpoint(completion())
    model = endpoint.model(api_key=None, provider="localhost:11434", hosting="local")
    call(model, ctx, system="s", messages=[{"role": "user", "content": "x"}])

    request = endpoint.requests[-1]
    assert "authorization" not in request.headers
    assert all(SENTINEL not in value for value in request.headers.values())


def test_the_adapter_needs_a_client_or_a_base_url() -> None:
    with pytest.raises(ValueError):
        OpenAIModel("m", provider="openai", hosting="hosted")
