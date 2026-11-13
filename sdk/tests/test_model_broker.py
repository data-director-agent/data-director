"""An agent calls models through the broker with its own credential, read once at start-up, and
the model grant the conductor sent with the run (docs/specs/model-accounts.md)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx2 as httpx
import pytest

from dd_sdk import serve
from dd_sdk.agent import AgentResult, AgentSpec, RunContext
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
    GroundingMode,
    InvocationRequest,
    Message,
    Outcome,
    OutcomeStatus,
)
from dd_sdk.credentials import (
    BROKER_CREDENTIAL,
    BROKER_URL,
    PROVIDER_KEY,
    ConfigError,
    ModelEndpoint,
    model_endpoint,
)
from dd_sdk.model import bind_grant, current_grant
from dd_sdk.model_anthropic import anthropic_client
from dd_sdk.model_grant import HEADER_GRANT, META_MODEL_GRANT

CREDENTIAL = "dd-broker-credential-0123456789"
PROVIDER = "sk-ant-test-0123456789"
BROKER = "http://broker.test:8790"
GRANT = "eyJhbGciOiJSUzI1NiJ9.grant.signature"


# --- Where an agent's calls go ---------------------------------------------------------------


def test_without_a_broker_the_agent_calls_the_provider() -> None:
    endpoint = model_endpoint({PROVIDER_KEY: PROVIDER})
    assert endpoint == ModelEndpoint(PROVIDER)
    assert not endpoint.brokered


def test_with_a_broker_the_agent_calls_it_with_its_own_credential() -> None:
    endpoint = model_endpoint({BROKER_URL: BROKER + "/", BROKER_CREDENTIAL: CREDENTIAL})
    assert endpoint.brokered
    assert endpoint.api_key == CREDENTIAL
    assert endpoint.base_url is not None and endpoint.base_url.startswith(BROKER)


def test_the_credential_may_be_a_systemd_credential(tmp_path: Path) -> None:
    (tmp_path / "broker-credential").write_text(CREDENTIAL + "\n")
    env = {
        BROKER_URL: BROKER,
        f"{BROKER_CREDENTIAL}_FILE": "broker-credential",
        "CREDENTIALS_DIRECTORY": str(tmp_path),
    }
    assert model_endpoint(env).api_key == CREDENTIAL


@pytest.mark.parametrize(
    "env",
    [
        {BROKER_URL: BROKER},
        {BROKER_URL: BROKER, BROKER_CREDENTIAL: " "},
        {BROKER_URL: BROKER, BROKER_CREDENTIAL: CREDENTIAL, PROVIDER_KEY: PROVIDER},
        {BROKER_URL: BROKER, BROKER_CREDENTIAL: CREDENTIAL, f"{PROVIDER_KEY}_FILE": "/k"},
        {BROKER_URL: "broker.test", BROKER_CREDENTIAL: CREDENTIAL},
        {BROKER_URL: BROKER, f"{BROKER_CREDENTIAL}_FILE": "/nonexistent/credential"},
    ],
)
def test_an_unusable_broker_configuration_is_one_line_naming_no_secret(
    env: dict[str, str],
) -> None:
    with pytest.raises(ConfigError) as caught:
        model_endpoint(env)
    message = str(caught.value)
    assert "\n" not in message
    assert CREDENTIAL not in message and PROVIDER not in message


def test_the_endpoint_never_shows_its_credential() -> None:
    assert CREDENTIAL not in repr(ModelEndpoint(CREDENTIAL, BROKER))


def test_a_missing_credential_stops_the_agent_at_start_up(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(BROKER_URL, BROKER)
    monkeypatch.delenv(BROKER_CREDENTIAL, raising=False)
    monkeypatch.delenv(f"{BROKER_CREDENTIAL}_FILE", raising=False)
    monkeypatch.delenv(PROVIDER_KEY, raising=False)
    monkeypatch.delenv(f"{PROVIDER_KEY}_FILE", raising=False)

    def build() -> Echo:
        model_endpoint(os.environ)
        return Echo()

    assert serve.main(build, ["serve", "--port", "8199"]) == serve.EXIT_CONFIG
    assert len(capsys.readouterr().err.strip().splitlines()) == 1


# --- The grant travels with each call ----------------------------------------------------------


class Broker:
    """Answers the Messages API as the broker would, and keeps the headers of each request."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": "claude-test",
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 3, "output_tokens": 1},
            },
        )


def via(broker: Broker) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(broker))


def ask(client: Any) -> None:
    client.messages.create(
        model="claude-test", max_tokens=16, messages=[{"role": "user", "content": "hi"}]
    )


def test_a_brokered_client_sends_the_runs_grant_and_its_credential() -> None:
    broker = Broker()
    client = anthropic_client(
        ModelEndpoint(CREDENTIAL, BROKER + "/anthropic"),
        http_client=via(broker),
    )
    with bind_grant(GRANT):
        ask(client)
    ask(client)  # outside a run: no grant

    first, second = broker.requests
    assert first.url.path == "/anthropic/v1/messages"
    assert first.headers[HEADER_GRANT] == GRANT
    # The client sends a key as `x-api-key` or as a bearer token; the broker takes either.
    assert CREDENTIAL in (
        first.headers.get("x-api-key"),
        first.headers.get("authorization", "").removeprefix("Bearer "),
    )
    assert HEADER_GRANT not in second.headers
    assert current_grant() is None


def test_a_client_that_calls_the_provider_never_sends_a_grant() -> None:
    provider = Broker()
    client = anthropic_client(ModelEndpoint(PROVIDER), http_client=via(provider))
    with bind_grant(GRANT):
        ask(client)
    [request] = provider.requests
    assert HEADER_GRANT not in request.headers


# --- The agent server binds the grant the harness sent -----------------------------------------


class Echo:
    """Calls the broker once with an SDK client, and keeps the context it was given."""

    spec = AgentSpec(
        agent_id="test.brokered",
        version="0.0.0",
        description="An agent that calls a model through the broker.",
        action_class="advise",
        accepts=(ClassSchema.of(Message),),
        grounding_mode=GroundingMode.NONE,
        payload=None,
    )

    def __init__(self) -> None:
        self.broker = Broker()
        self.client = anthropic_client(
            ModelEndpoint(CREDENTIAL, BROKER + "/anthropic"),
            http_client=via(self.broker),
        )
        self.contexts: list[RunContext] = []

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        self.contexts.append(ctx)
        ask(self.client)
        return AgentResult(outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement="Done."))


def request() -> InvocationRequest:
    return InvocationRequest(agent_id=Echo.spec.agent_id, input=Message(message_text="Hello."))


def test_the_server_gives_the_agent_the_grant_and_its_clients_send_it() -> None:
    agent = Echo()
    body = serve.run_traced(agent, request(), {META_MODEL_GRANT: GRANT})

    [ctx] = agent.contexts
    assert ctx.model_grant == GRANT
    [sent] = agent.broker.requests
    assert sent.headers[HEADER_GRANT] == GRANT
    # The grant goes to the broker and nowhere else: not into the reply or its spans.
    assert GRANT not in json.dumps(body)
    assert current_grant() is None


def test_without_a_grant_the_agent_is_given_none() -> None:
    agent = Echo()
    serve.run_traced(agent, request(), {})
    [ctx] = agent.contexts
    assert ctx.model_grant is None
    [sent] = agent.broker.requests
    assert HEADER_GRANT not in sent.headers
