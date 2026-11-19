"""The model seam's router (docs/specs/model-accounts.md, invariant 15 and The route; #843): each
run asks the broker once per declared model which provider and model serve it, sends its calls
there, and records the declared model on every call it routed and on no other."""

from __future__ import annotations

import json
from typing import Any, Literal

import httpx
import pytest

from dd_sdk import model_route, serve
from dd_sdk.agent import AgentResult, AgentSpec, ModelUse, RunContext
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
    GroundingMode,
    InvocationRequest,
    Message,
    Outcome,
    OutcomeStatus,
    ReasonCode,
)
from dd_sdk.model import ModelCallError, ModelRequest, ModelResponse, bind_grant, call, declared
from dd_sdk.model_anthropic import AnthropicModel
from dd_sdk.model_grant import HEADER_GRANT, HEADER_REASON, META_MODEL_GRANT
from dd_sdk.model_openai import OpenAIModel
from dd_sdk.model_provider import _routed_builder
from dd_sdk.model_route import RoutedModel
from dd_sdk.prompts import ModelCallLog
from dd_sdk.tracing import ATTR_MODEL_DECLARED, CHAT
from dd_sdk.wire import reply_from_document

BROKER = "http://broker.test:8300"
CREDENTIAL = "dd-broker-credential-route-0123"
DECLARED = "claude-declared"
SERVED = "gpt-served"


class Fake:
    """An adapter that answers every call, and counts them."""

    def __init__(self, provider: str, model_id: str, *, tool_use: bool = False) -> None:
        self.provider = provider
        self.model_id = model_id
        self.hosting: Literal["hosted", "local"] = "hosted"
        self.tool_use = tool_use
        self.sent: list[ModelRequest] = []

    def send(self, request: ModelRequest) -> ModelResponse:
        self.sent.append(request)
        return ModelResponse("ok", model_id=self.model_id)


class Broker:
    """The broker's `/route`: answers each request with `answer`, or refuses it with `refuse`."""

    def __init__(
        self, answer: tuple[str, str] = ("openai", SERVED), refuse: tuple[int, str] | None = None
    ) -> None:
        self.answer = answer
        self.refuse = refuse
        self.asked: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.asked.append(request)
        if self.refuse is not None:
            status, reason = self.refuse
            return httpx.Response(status, headers={HEADER_REASON: reason}, json={"error": reason})
        provider, model = self.answer
        return httpx.Response(200, json={"provider": provider, "model": model})


@pytest.fixture
def broker(monkeypatch: pytest.MonkeyPatch) -> Broker:
    stub = Broker()
    monkeypatch.setattr(
        model_route, "http_client", lambda: httpx.Client(transport=httpx.MockTransport(stub))
    )
    return stub


def routed(served: dict[tuple[str, str], Fake] | None = None) -> tuple[RoutedModel, Fake]:
    declared_model = Fake("anthropic", DECLARED, tool_use=True)
    built = served if served is not None else {}

    def build(provider: str, model: str) -> Fake:
        return built.setdefault((provider, model), Fake(provider, model))

    model = RoutedModel(declared_model, broker_url=BROKER, credential=CREDENTIAL, build=build)
    return model, declared_model


REQUEST = ModelRequest("Be brief.", ({"role": "user", "content": "hi"},))


def test_the_card_declares_the_declared_model() -> None:
    model, _ = routed()
    assert declared(model) == ModelUse("anthropic", DECLARED, "hosted", True)


def test_a_run_asks_once_and_sends_every_call_where_the_broker_said(broker: Broker) -> None:
    served: dict[tuple[str, str], Fake] = {}
    model, declared_model = routed(served)
    with bind_grant("grant-run-1"):
        model.send(REQUEST)
        model.send(REQUEST)
    assert len(broker.asked) == 1
    asked = broker.asked[0]
    assert str(asked.url) == BROKER + "/route"
    assert asked.headers["x-api-key"] == CREDENTIAL
    assert asked.headers[HEADER_GRANT] == "grant-run-1"
    assert json.loads(asked.content) == {"provider": "anthropic", "model": DECLARED}
    assert declared_model.sent == []
    assert len(served[("openai", SERVED)].sent) == 2


def test_each_run_asks_again(broker: Broker) -> None:
    model, declared_model = routed()
    with bind_grant("grant-run-1"):
        model.send(REQUEST)
    broker.answer = ("anthropic", DECLARED)
    with bind_grant("grant-run-2"):
        model.send(REQUEST)
    assert len(broker.asked) == 2
    assert len(declared_model.sent) == 1


def test_a_call_with_no_grant_goes_as_declared_without_asking(broker: Broker) -> None:
    model, declared_model = routed()
    model.send(REQUEST)
    assert broker.asked == []
    assert len(declared_model.sent) == 1


@pytest.mark.parametrize(
    "document", [{"provider": "openai"}, {"provider": "", "model": "m"}, ["openai", "m"], "x"]
)
def test_an_answer_that_is_not_a_route_is_a_model_call_error(
    monkeypatch: pytest.MonkeyPatch, document: Any
) -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=document)

    monkeypatch.setattr(
        model_route, "http_client", lambda: httpx.Client(transport=httpx.MockTransport(answer))
    )
    model, _ = routed()
    with bind_grant("grant"), pytest.raises(ModelCallError):
        model.send(REQUEST)


# --- Through a run: what is recorded, and a refused route ---------------------------------------

SPEC = AgentSpec(
    agent_id="test.routed",
    version="0.0.0",
    description="An agent whose one model the broker may route.",
    action_class="advise",
    accepts=(ClassSchema.of(Message),),
    grounding_mode=GroundingMode.NONE,
    payload=None,
)


class Twice:
    spec = SPEC

    def __init__(self, model: RoutedModel) -> None:
        self.model = model

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        log = ModelCallLog(self.model.provider)
        for text in ("one", "two"):
            call(
                self.model,
                ctx,
                system="Be brief.",
                messages=[{"role": "user", "content": text}],
                calls=log,
            )
        return AgentResult(
            outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement="Done."),
            model_calls=log.calls,
            prompts=log.prompts,
        )


def run(model: RoutedModel) -> tuple[AgentResult, tuple[dict[str, Any], ...]]:
    request = InvocationRequest(agent_id=SPEC.agent_id, input=Message(message_text="Hello."))
    return reply_from_document(
        serve.run_traced(Twice(model), request, {META_MODEL_GRANT: "grant-run"})
    )


def test_a_routed_run_records_the_served_and_the_declared_model(broker: Broker) -> None:
    model, _ = routed()
    result, spans = run(model)
    assert [(c.model_id, c.model_declared) for c in result.model_calls] == [
        (SERVED, DECLARED),
        (SERVED, DECLARED),
    ]
    chats = [s["attributes"] for s in spans if s["name"] == CHAT]
    assert [a.get(ATTR_MODEL_DECLARED) for a in chats] == [DECLARED, DECLARED]


def test_an_unrouted_run_records_no_declared_model(broker: Broker) -> None:
    broker.answer = ("anthropic", DECLARED)
    model, _ = routed()
    result, spans = run(model)
    assert [c.model_declared for c in result.model_calls] == [None, None]
    assert all(ATTR_MODEL_DECLARED not in s["attributes"] for s in spans if s["name"] == CHAT)


def test_a_refused_route_ends_the_run_as_the_account_table_says(broker: Broker) -> None:
    broker.refuse = (403, "model-account-missing")
    model, _ = routed()
    result, _ = run(model)
    assert result.outcome.status is OutcomeStatus.ABSTAINED
    assert result.outcome.reason_code is ReasonCode.MODEL_ACCOUNT_MISSING
    assert result.model_calls == ()


# --- The adapter built for what the broker named ------------------------------------------------


def test_the_served_provider_is_called_through_the_broker_with_an_effort_it_accepts() -> None:
    build = _routed_builder(BROKER, CREDENTIAL, effort="xhigh", tool_use=True)

    openai = build("openai", SERVED)
    assert isinstance(openai, OpenAIModel)
    assert (openai.provider, openai.model_id, openai.effort, openai.tool_use) == (
        "openai",
        SERVED,
        None,  # OpenAI takes low, medium or high
        True,
    )
    claude = build("anthropic", "claude-other")
    assert isinstance(claude, AnthropicModel)
    assert claude.effort == "xhigh"

    medium = _routed_builder(BROKER, CREDENTIAL, effort="medium", tool_use=False)("gemini", "g")
    assert isinstance(medium, OpenAIModel) and medium.effort == "medium"


def test_a_provider_the_sdk_does_not_serve_is_a_model_call_error() -> None:
    with pytest.raises(ModelCallError):
        _routed_builder(BROKER, CREDENTIAL, effort=None, tool_use=False)("nobody", "m")
