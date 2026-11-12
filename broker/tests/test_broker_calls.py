"""The broker makes a model call only for an agent with a valid grant, chooses whose account pays
from the grant alone, says who paid, and counts tokens (docs/specs/model-accounts.md, invariants 7,
10 and 14). Provider answers are replayed from hand-written cassettes."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic
import httpx
import pytest
from broker_support import (
    AGENT_CREDENTIAL,
    GATEWAY,
    MODEL,
    OTHER_CREDENTIAL,
    PSEUDONYM,
    FakeHarness,
    broker_calls_only,
    call_headers,
    client,
    make_broker,
    message_body,
)

from dd_broker import anthropic as broker_anthropic
from dd_broker.app import Broker
from dd_sdk.model_grant import (
    HEADER_ACCOUNT,
    HEADER_GRANT,
    HEADER_PROVIDER,
    HEADER_REASON,
    Account,
    Payer,
)

OWN_KEY = "sk-ant-own-test-1111"
MESSAGES = "/anthropic/v1/messages"


@pytest.fixture(scope="module")
def vcr_config(vcr_config: dict[str, Any]) -> dict[str, Any]:
    return {**vcr_config, "before_record_request": broker_calls_only}


@pytest.fixture
def harness() -> FakeHarness:
    return FakeHarness()


@pytest.fixture
def broker(harness: FakeHarness, tmp_path: Path) -> Broker:
    return make_broker(harness, tmp_path / "broker.sqlite3")


@dataclass(frozen=True)
class Sent:
    url: str
    key: str
    headers: dict[str, str]


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[Sent]:
    """What the broker sent to the provider: the cassette shows only what was recorded."""
    calls: list[Sent] = []
    original = broker_anthropic.send

    async def spy(client: Any, target: Any, key: str, body: Any, headers: Any) -> Any:
        calls.append(Sent(target.url, key, dict(headers)))
        return await original(client, target, key, body, headers)

    monkeypatch.setattr(broker_anthropic, "send", spy)
    return calls


def enrol(broker: Broker, key: str = OWN_KEY) -> None:
    broker.store.put(PSEUDONYM, "anthropic", key, label=f"anthropic …{key[-4:]}")


def reason(response: Any) -> str:
    return str(response.headers.get(HEADER_REASON))


@pytest.mark.vcr
def test_an_own_grant_is_paid_for_by_the_persons_key(
    harness: FakeHarness, broker: Broker, sent: list[Sent]
) -> None:
    enrol(broker)
    with client(broker) as http:
        response = http.post(MESSAGES, json=message_body(), headers=call_headers(harness.grant()))

    assert response.status_code == 200
    assert response.headers[HEADER_ACCOUNT] == "own"
    assert response.headers[HEADER_PROVIDER] == "anthropic"
    assert response.json()["model"] == MODEL
    assert [call.key for call in sent] == [OWN_KEY]
    usage = broker.store.usage(PSEUDONYM)
    assert [(u.payer.value, u.provider, u.model) for u in usage] == [("own", "anthropic", MODEL)]
    assert usage[0].input_tokens > 0 and usage[0].output_tokens > 0


@pytest.mark.vcr
def test_own_or_deployment_falls_back_to_the_deployment(
    harness: FakeHarness, broker: Broker, sent: list[Sent]
) -> None:
    grant = harness.grant(account=Account.OWN_OR_DEPLOYMENT)
    with client(broker) as http:
        response = http.post(MESSAGES, json=message_body(), headers=call_headers(grant))

    assert response.status_code == 200
    assert response.headers[HEADER_ACCOUNT] == "deployment"
    assert [call.key for call in sent] == [broker.deployment_key]
    assert [u.payer.value for u in broker.store.usage(PSEUDONYM)] == ["deployment"]


@pytest.mark.vcr
def test_a_deployment_grant_goes_through_the_gateway(
    harness: FakeHarness, tmp_path: Path, sent: list[Sent]
) -> None:
    broker = make_broker(harness, tmp_path / "broker.sqlite3", deployment_base_url=GATEWAY)
    enrol(broker)  # A deployment grant never uses the person's key, even when they have one.
    grant = harness.grant(account=Account.DEPLOYMENT)
    with client(broker) as http:
        response = http.post(MESSAGES, json=message_body(), headers=call_headers(grant))

    assert response.status_code == 200
    assert response.headers[HEADER_ACCOUNT] == "deployment"
    assert [(call.url, call.key) for call in sent] == [(GATEWAY, broker.deployment_key)]


def test_an_own_grant_without_an_account_ends_with_model_account_missing(
    harness: FakeHarness, broker: Broker
) -> None:
    with client(broker) as http:
        response = http.post(MESSAGES, json=message_body(), headers=call_headers(harness.grant()))

    assert response.status_code == 403
    assert reason(response) == "model-account-missing"


@pytest.mark.vcr
def test_a_rejected_own_key_ends_with_model_account_rejected(
    harness: FakeHarness, broker: Broker
) -> None:
    enrol(broker)
    grant = harness.grant(account=Account.OWN_OR_DEPLOYMENT)
    with client(broker) as http:
        response = http.post(MESSAGES, json=message_body(), headers=call_headers(grant))

    # Not paid for by the deployment instead: that would silently change who pays.
    assert response.status_code == 403
    assert reason(response) == "model-account-rejected"
    assert HEADER_ACCOUNT not in response.headers


@pytest.mark.vcr
def test_a_limited_own_key_ends_with_model_account_limit(
    harness: FakeHarness, broker: Broker
) -> None:
    enrol(broker)
    with client(broker) as http:
        response = http.post(MESSAGES, json=message_body(), headers=call_headers(harness.grant()))

    assert response.status_code == 429
    assert reason(response) == "model-account-limit"


def test_a_deployment_grant_without_a_deployment_key_is_refused(
    harness: FakeHarness, tmp_path: Path
) -> None:
    broker = make_broker(harness, tmp_path / "broker.sqlite3", deployment_key=None)
    grant = harness.grant(account=Account.DEPLOYMENT)
    with client(broker) as http:
        response = http.post(MESSAGES, json=message_body(), headers=call_headers(grant))

    assert response.status_code == 503
    assert reason(response) == "deployment-account-unavailable"


@pytest.mark.parametrize(
    ("headers", "status", "code"),
    [
        ({"x-api-key": "not-a-credential"}, 401, "agent-unauthenticated"),
        ({}, 401, "agent-unauthenticated"),
        ({"x-api-key": AGENT_CREDENTIAL}, 401, "grant-missing"),
        ({"x-api-key": AGENT_CREDENTIAL, HEADER_GRANT: "not.a.jwt"}, 401, "grant-invalid"),
    ],
)
def test_an_unauthenticated_or_ungranted_call_is_refused(
    broker: Broker, headers: dict[str, str], status: int, code: str
) -> None:
    with client(broker) as http:
        response = http.post(MESSAGES, json=message_body(), headers=headers)

    assert response.status_code == status
    assert reason(response) == code


def test_a_grant_presented_by_another_agent_is_refused(
    harness: FakeHarness, broker: Broker
) -> None:
    enrol(broker)
    with client(broker) as http:
        response = http.post(
            MESSAGES,
            json=message_body(),
            headers=call_headers(harness.grant(), credential=OTHER_CREDENTIAL),
        )

    assert response.status_code == 403
    assert reason(response) == "grant-agent-mismatch"


def test_a_model_the_grant_does_not_allow_is_refused(harness: FakeHarness, broker: Broker) -> None:
    enrol(broker)
    with client(broker) as http:
        response = http.post(
            MESSAGES,
            json=message_body(model="claude-opus-5-5"),
            headers=call_headers(harness.grant()),
        )

    assert response.status_code == 403
    assert reason(response) == "model-not-granted"


@pytest.mark.parametrize(
    ("body", "code"),
    [
        (message_body(stream=True), "streaming-unsupported"),
        ({"messages": []}, "request-invalid"),
    ],
)
def test_a_request_the_broker_does_not_serve_is_refused(
    harness: FakeHarness, broker: Broker, body: dict[str, Any], code: str
) -> None:
    enrol(broker)
    with client(broker) as http:
        response = http.post(MESSAGES, json=body, headers=call_headers(harness.grant()))

    assert response.status_code == 400
    assert reason(response) == code


def test_an_account_with_another_provider_is_never_substituted(
    harness: FakeHarness, broker: Broker
) -> None:
    broker.store.put(PSEUDONYM, "openai", "sk-openai-test", label="openai …test")
    with client(broker) as http:
        response = http.post(MESSAGES, json=message_body(), headers=call_headers(harness.grant()))

    assert response.status_code == 403
    assert reason(response) == "account-unsupported"


def test_a_base_url_off_the_allow_list_is_refused(harness: FakeHarness, broker: Broker) -> None:
    broker.store.put(
        PSEUDONYM, "anthropic", OWN_KEY, label="anthropic …1111", base_url="https://evil.example"
    )
    with client(broker) as http:
        response = http.post(MESSAGES, json=message_body(), headers=call_headers(harness.grant()))

    assert response.status_code == 403
    assert reason(response) == "base-url-refused"


@pytest.mark.vcr
def test_the_anthropic_client_works_through_the_broker(
    harness: FakeHarness, broker: Broker
) -> None:
    # What an agent's adapter will do (TODO(#808)): its usual client, with the broker's base URL,
    # its broker credential as the API key, and the grant as a header.
    enrol(broker)
    with client(broker) as http:
        model = anthropic.Anthropic(
            base_url=f"{http.base_url}/anthropic",
            api_key=AGENT_CREDENTIAL,
            default_headers={HEADER_GRANT: harness.grant()},
            http_client=http,
            max_retries=0,
        )
        reply = model.messages.create(
            model=MODEL, max_tokens=64, messages=[{"role": "user", "content": "Which standard?"}]
        )

    assert reply.model == MODEL
    assert reply.content[0].type == "text"


def test_the_store_holds_no_prompt_and_no_plain_key(harness: FakeHarness, broker: Broker) -> None:
    enrol(broker)
    broker.store.add_usage(
        PSEUDONYM,
        payer=Payer.OWN,
        provider="anthropic",
        model=MODEL,
        input_tokens=1,
        output_tokens=1,
    )
    with closing(sqlite3.connect(broker.store.path)) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(usage)")}
        columns |= {row[1] for row in db.execute("PRAGMA table_info(accounts)")}
    assert not columns & {"prompt", "messages", "reply", "content", "key"}
    assert OWN_KEY.encode() not in broker.store.path.read_bytes()


def test_the_health_check_answers(broker: Broker) -> None:
    with client(broker) as http:
        assert http.get("/healthz").status_code == 200


def test_only_the_paying_key_and_the_api_version_reach_the_provider(
    harness: FakeHarness, tmp_path: Path
) -> None:
    seen: list[httpx.Request] = []

    def provider(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"model": MODEL, "usage": {}})

    broker = make_broker(
        harness, tmp_path / "broker.sqlite3", transport=httpx.MockTransport(provider)
    )
    enrol(broker)
    grant = harness.grant()
    with client(broker) as http:
        http.post(MESSAGES, json=message_body(), headers=call_headers(grant))

    (request,) = seen
    assert request.headers["x-api-key"] == OWN_KEY
    assert "anthropic-version" in request.headers
    forwarded = " ".join(f"{name}: {value}" for name, value in request.headers.items())
    assert grant not in forwarded
    assert AGENT_CREDENTIAL not in forwarded
    assert HEADER_GRANT.lower() not in request.headers


def test_an_allowed_base_url_is_called_at_the_address_that_was_checked(
    harness: FakeHarness, tmp_path: Path
) -> None:
    seen: list[httpx.Request] = []

    def provider(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"model": MODEL, "usage": {}})

    broker = make_broker(
        harness,
        tmp_path / "broker.sqlite3",
        transport=httpx.MockTransport(provider),
        allowed=["https://models.example.ac.uk"],
    )
    broker.store.put(
        PSEUDONYM,
        "anthropic",
        OWN_KEY,
        label="anthropic …1111",
        base_url="https://models.example.ac.uk/proxy",
    )
    with client(broker) as http:
        response = http.post(MESSAGES, json=message_body(), headers=call_headers(harness.grant()))

    assert response.status_code == 200
    (request,) = seen
    assert request.url.host == "93.184.215.14"
    assert request.url.path == "/proxy/v1/messages"
    assert request.headers["host"] == "models.example.ac.uk"
    assert request.extensions["sni_hostname"] == "models.example.ac.uk"
