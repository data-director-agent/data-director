"""The broker's deployment-paid calls reach a real LiteLLM gateway and come back counted
(deploy/llm-gateway/README.md, "With the model broker"). Both of the broker's formats are sent:
Anthropic Messages and OpenAI Chat Completions.

Skipped unless `DD_TEST_GATEWAY` names a running gateway and `DD_TEST_GATEWAY_KEY` holds one of its
virtual keys. CI starts the test stack, whose fake provider bills nothing, and sets both
(deploy/llm-gateway/scripts/testing/broker_e2e.sh). The other broker tests stand in for the gateway
with recorded or mocked answers; this one checks that what the broker sends is what LiteLLM
serves."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from broker_support import (
    AGENT_CREDENTIAL,
    PSEUDONYM,
    FakeHarness,
    call_headers,
    client,
    make_broker,
    message_body,
)

from dd_broker.app import Broker
from dd_sdk.model_grant import HEADER_ACCOUNT, HEADER_GRANT, HEADER_PROVIDER, Account

GATEWAY = os.environ.get("DD_TEST_GATEWAY", "").rstrip("/")
GATEWAY_KEY = os.environ.get("DD_TEST_GATEWAY_KEY", "")

# Model names in deploy/llm-gateway/config.test.yaml, each served by the fake provider.
CLAUDE = "claude-sonnet-5-5"
GPT = "test-gpt"

pytestmark = [
    pytest.mark.gateway,
    pytest.mark.skipif(
        not (GATEWAY and GATEWAY_KEY),
        reason="no gateway: DD_TEST_GATEWAY or DD_TEST_GATEWAY_KEY is unset",
    ),
]


@pytest.fixture
def harness() -> FakeHarness:
    return FakeHarness()


@pytest.fixture
def broker(harness: FakeHarness, tmp_path: Path) -> Broker:
    return make_broker(
        harness,
        tmp_path / "broker.sqlite3",
        deployment_keys={"anthropic": GATEWAY_KEY, "openai": GATEWAY_KEY},
        deployment_base_url=GATEWAY,
    )


def test_an_anthropic_call_paid_by_the_deployment_goes_through_the_gateway(
    harness: FakeHarness, broker: Broker
) -> None:
    grant = harness.grant(account=Account.DEPLOYMENT, models=[CLAUDE])
    with client(broker) as http:
        response = http.post(
            "/anthropic/v1/messages", json=message_body(CLAUDE), headers=call_headers(grant)
        )

    assert response.status_code == 200, response.text
    assert response.headers[HEADER_ACCOUNT] == "deployment"
    assert response.json()["type"] == "message"
    (usage,) = broker.store.usage(PSEUDONYM)
    assert usage.payer.value == "deployment"
    assert usage.provider == "anthropic"
    assert usage.output_tokens > 0


def test_a_chat_completions_call_paid_by_the_deployment_goes_through_the_gateway(
    harness: FakeHarness, broker: Broker
) -> None:
    grant = harness.grant(account=Account.DEPLOYMENT, models=[GPT])
    body = {
        "model": GPT,
        "max_completion_tokens": 64,
        "messages": [{"role": "user", "content": "Which standard fits?"}],
    }
    headers = {"authorization": f"Bearer {AGENT_CREDENTIAL}", HEADER_GRANT: grant}
    with client(broker) as http:
        response = http.post("/openai/chat/completions", json=body, headers=headers)

    assert response.status_code == 200, response.text
    assert response.headers[HEADER_ACCOUNT] == "deployment"
    assert response.headers[HEADER_PROVIDER] == "openai"
    assert response.json()["object"] == "chat.completion"
    (usage,) = broker.store.usage(PSEUDONYM)
    assert usage.payer.value == "deployment"
    assert usage.provider == "openai"
    assert usage.output_tokens > 0
