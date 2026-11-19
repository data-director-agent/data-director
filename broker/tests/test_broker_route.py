"""The route: which provider and model serve a model an agent's card declares
(docs/specs/model-accounts.md, invariant 15 and The route; issue #843).

The broker answers from the grant and the person's account alone, names a provider and a model and
nothing about the account, and never calls a provider to answer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from broker_support import (
    AGENT_CREDENTIAL,
    MODEL,
    OTHER_AGENT,
    PSEUDONYM,
    FakeHarness,
    client,
    make_broker,
)

from dd_broker.app import ROUTE_PATH, Broker
from dd_sdk.model_grant import HEADER_GRANT, HEADER_REASON, Account

SERVED = "gpt-5.5"
MAP = {"openai": {MODEL: SERVED}}
OWN_KEY = "sk-proj-own-route-7777"


class NoProvider:
    """A provider transport that fails the test if the broker calls it."""

    def __init__(self) -> None:
        self.seen: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        return httpx.Response(500)


@pytest.fixture
def harness() -> FakeHarness:
    return FakeHarness()


@pytest.fixture
def provider() -> NoProvider:
    return NoProvider()


@pytest.fixture
def broker(harness: FakeHarness, tmp_path: Path, provider: NoProvider) -> Broker:
    return make_broker(
        harness, tmp_path / "broker.sqlite3", transport=httpx.MockTransport(provider)
    )


def own(broker: Broker, provider: str = "openai") -> None:
    broker.store.put(PSEUDONYM, provider, OWN_KEY, label="own")


def grant(harness: FakeHarness, account: Account = Account.OWN, **claims: Any) -> str:
    claims.setdefault("models", [MODEL])
    if account is not Account.DEPLOYMENT:
        claims.setdefault("providers", ["anthropic", "openai", "gemini"])
        claims.setdefault("model_map", MAP)
    return harness.grant(account=account, **claims)


def ask(
    broker: Broker,
    token: str | None,
    body: Any = None,
    *,
    credential: str | None = AGENT_CREDENTIAL,
) -> Any:
    headers: dict[str, str] = {}
    if credential is not None:
        headers["x-api-key"] = credential
    if token is not None:
        headers[HEADER_GRANT] = token
    payload = {"provider": "anthropic", "model": MODEL} if body is None else body
    return client(broker).post(ROUTE_PATH, headers=headers, json=payload)


@pytest.mark.parametrize("account", [Account.OWN, Account.OWN_OR_DEPLOYMENT])
def test_an_account_with_the_mapped_provider_is_routed_to_the_mapped_model(
    broker: Broker, harness: FakeHarness, provider: NoProvider, account: Account
) -> None:
    own(broker, "openai")
    response = ask(broker, grant(harness, account))
    assert response.status_code == 200
    # A provider and a model, and nothing about the account.
    assert response.json() == {"provider": "openai", "model": SERVED}
    assert OWN_KEY not in response.text and PSEUDONYM not in response.text
    assert provider.seen == []


@pytest.mark.parametrize(
    ("enrolled", "claims", "account"),
    [
        pytest.param(None, {}, Account.OWN, id="no-account"),
        pytest.param(None, {}, Account.OWN_OR_DEPLOYMENT, id="no-account-deployment-fallback"),
        pytest.param("gemini", {}, Account.OWN, id="a-provider-the-map-does-not-name"),
        pytest.param("anthropic", {}, Account.OWN, id="the-declared-provider"),
        pytest.param(
            "openai",
            {"providers": ["anthropic"], "model_map": {}},
            Account.OWN,
            id="a-provider-the-grant-does-not-allow",
        ),
        pytest.param(
            "openai",
            {"models": [MODEL, "claude-other"], "model_map": {"openai": {"claude-other": SERVED}}},
            Account.OWN,
            id="no-mapping-for-this-model",
        ),
        pytest.param("openai", {}, Account.DEPLOYMENT, id="a-grant-the-deployment-pays-for"),
    ],
)
def test_otherwise_the_declared_provider_and_model_serve(
    broker: Broker,
    harness: FakeHarness,
    provider: NoProvider,
    enrolled: str | None,
    claims: dict[str, Any],
    account: Account,
) -> None:
    if enrolled is not None:
        own(broker, enrolled)
    response = ask(broker, grant(harness, account, **claims))
    assert response.status_code == 200
    assert response.json() == {"provider": "anthropic", "model": MODEL}
    assert provider.seen == []


@pytest.mark.parametrize("model", ["claude-not-declared", SERVED])
def test_a_model_the_card_does_not_declare_has_no_route(
    broker: Broker, harness: FakeHarness, model: str
) -> None:
    """A served model is not a declared one: the route starts from the card."""
    own(broker, "openai")
    response = ask(broker, grant(harness), {"provider": "anthropic", "model": model})
    assert response.status_code == 403
    assert response.headers[HEADER_REASON] == "model-not-granted"


def test_an_agent_without_its_credential_is_refused(broker: Broker, harness: FakeHarness) -> None:
    response = ask(broker, grant(harness), credential=None)
    assert response.status_code == 401
    assert response.headers[HEADER_REASON] == "agent-unauthenticated"


def test_a_request_without_a_grant_is_refused(broker: Broker) -> None:
    response = ask(broker, None)
    assert response.status_code == 401
    assert response.headers[HEADER_REASON] == "grant-missing"


def test_another_agents_grant_is_refused(broker: Broker, harness: FakeHarness) -> None:
    response = ask(broker, grant(harness, agent=OTHER_AGENT))
    assert response.status_code == 403
    assert response.headers[HEADER_REASON] == "grant-agent-mismatch"


@pytest.mark.parametrize(
    "body",
    [
        ["anthropic", MODEL],
        {"model": MODEL},
        {"provider": "anthropic", "model": 5},
        {"provider": "nobody", "model": MODEL},
        {"provider": "anthropic", "model": MODEL, "account": "own"},
    ],
)
def test_a_malformed_request_is_refused(broker: Broker, harness: FakeHarness, body: Any) -> None:
    response = ask(broker, grant(harness), body)
    assert response.status_code == 400
    assert response.headers[HEADER_REASON] == "request-invalid"


def test_a_sealed_key_that_does_not_open_is_a_broker_error(
    harness: FakeHarness, tmp_path: Path
) -> None:
    path = tmp_path / "broker.sqlite3"
    sealed = make_broker(harness, path)
    own(sealed, "openai")
    reopened = make_broker(harness, path, kek=bytes(32))
    response = ask(reopened, grant(harness))
    assert response.status_code == 500
    assert response.headers[HEADER_REASON] == "broker-error"
