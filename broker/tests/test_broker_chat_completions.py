"""The broker forwards the OpenAI Chat Completions format for `openai`, `gemini` and
`openai-compatible` (docs/specs/model-accounts.md, The broker's interface for agents): it serves
the provider the path names or refuses, chooses whose account pays from the grant alone, says who
paid, and counts tokens. The provider is a `MockTransport`, so nothing leaves the test."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import httpx
import openai
import pytest
from broker_support import (
    AGENT,
    AGENT_CREDENTIAL,
    GATEWAY,
    PSEUDONYM,
    FakeHarness,
    client,
    make_broker,
)

from dd_broker.app import Broker
from dd_broker.gateway import TAGS_HEADER as GATEWAY_TAGS_HEADER
from dd_sdk.model_grant import (
    HEADER_ACCOUNT,
    HEADER_GRANT,
    HEADER_PROVIDER,
    HEADER_REASON,
    Account,
)

MODEL = "gpt-5.5"
OWN_KEY = "sk-proj-own-test-2222"
DEPLOYMENT_OPENAI = "sk-proj-deployment-test-3333"
DEPLOYMENT_GEMINI = "gemini-deployment-test-4444"
GATEWAY_KEY = "sk-gateway-test-5555"
ENDPOINT = "https://llm.example.ac.uk"


def completions(provider: str = "openai") -> str:
    return f"/{provider}/chat/completions"


def body(model: str = MODEL, **extra: Any) -> dict[str, Any]:
    return {
        "model": model,
        "max_completion_tokens": 64,
        "messages": [{"role": "user", "content": "Which standard fits?"}],
        **extra,
    }


def headers(grant: str | None) -> dict[str, str]:
    sent = {"authorization": f"Bearer {AGENT_CREDENTIAL}", "openai-organization": "org-ambient"}
    if grant is not None:
        sent[HEADER_GRANT] = grant
    return sent


def answer(model: str = MODEL) -> dict[str, Any]:
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 0,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Use DDI."},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150},
    }


class Provider:
    """A stand-in for every endpoint the broker may call, answering each with `status`."""

    def __init__(self, status: int = 200) -> None:
        self.status = status
        self.seen: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        if self.status != 200:
            return httpx.Response(self.status, json={"error": {"message": f"key {OWN_KEY}"}})
        return httpx.Response(200, json=answer())

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


@pytest.fixture
def harness() -> FakeHarness:
    return FakeHarness()


@pytest.fixture
def provider() -> Provider:
    return Provider()


def broker_with(
    harness: FakeHarness,
    tmp_path: Path,
    provider: Provider,
    *,
    keys: Mapping[str, str] | None = None,
    gateway: str | None = None,
    allowed: Sequence[str] = (),
) -> Broker:
    return make_broker(
        harness,
        tmp_path / "broker.sqlite3",
        deployment_keys=(
            {"openai": DEPLOYMENT_OPENAI, "gemini": DEPLOYMENT_GEMINI} if keys is None else keys
        ),
        deployment_base_url=gateway,
        transport=provider.transport,
        allowed=allowed,
    )


def own(broker: Broker, provider: str = "openai", base_url: str | None = None) -> None:
    broker.store.put(PSEUDONYM, provider, OWN_KEY, label="own", base_url=base_url)


def grant(harness: FakeHarness, account: Account = Account.OWN, **claims: Any) -> str:
    claims.setdefault("models", [MODEL])
    if account is not Account.DEPLOYMENT:
        claims.setdefault("providers", ["openai", "gemini", "openai-compatible"])
    return harness.grant(account=account, **claims)


def reason(response: Any) -> str:
    return str(response.headers.get(HEADER_REASON))


@pytest.mark.parametrize(
    ("name", "url", "key"),
    [
        ("openai", "https://api.openai.com/v1/chat/completions", DEPLOYMENT_OPENAI),
        (
            "gemini",
            "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
            DEPLOYMENT_GEMINI,
        ),
    ],
)
def test_the_deployment_pays_at_the_providers_own_endpoint(
    harness: FakeHarness, tmp_path: Path, provider: Provider, name: str, url: str, key: str
) -> None:
    broker = broker_with(harness, tmp_path, provider)
    with client(broker) as http:
        response = http.post(
            completions(name), json=body(), headers=headers(grant(harness, Account.DEPLOYMENT))
        )

    assert response.status_code == 200
    assert response.headers[HEADER_ACCOUNT] == "deployment"
    assert response.headers[HEADER_PROVIDER] == name
    assert response.json()["model"] == MODEL
    (sent,) = provider.seen
    assert str(sent.url) == url
    assert sent.headers["authorization"] == f"Bearer {key}"
    # Only the deployment's own gateway is told which agent called.
    assert GATEWAY_TAGS_HEADER not in sent.headers
    usage = broker.store.usage(PSEUDONYM)
    assert [(u.payer.value, u.provider, u.model) for u in usage] == [("deployment", name, MODEL)]
    assert (usage[0].input_tokens, usage[0].output_tokens) == (120, 30)


@pytest.mark.parametrize("name", ["openai", "openai-compatible"])
def test_the_deployments_calls_go_through_the_gateway(
    harness: FakeHarness, tmp_path: Path, provider: Provider, name: str
) -> None:
    broker = broker_with(
        harness,
        tmp_path,
        provider,
        keys={"openai": GATEWAY_KEY, "openai-compatible": GATEWAY_KEY},
        gateway=GATEWAY,
    )
    own(broker)  # A deployment grant never uses the person's key, even when they have one.
    with client(broker) as http:
        response = http.post(
            completions(name), json=body(), headers=headers(grant(harness, Account.DEPLOYMENT))
        )

    assert response.status_code == 200
    assert response.headers[HEADER_PROVIDER] == name
    (sent,) = provider.seen
    assert str(sent.url) == f"{GATEWAY}/v1/chat/completions"
    assert sent.headers["authorization"] == f"Bearer {GATEWAY_KEY}"
    assert sent.headers[GATEWAY_TAGS_HEADER] == f"agent:{AGENT}"


def test_the_deployment_pays_an_openai_compatible_endpoint_only_through_its_gateway(
    harness: FakeHarness, tmp_path: Path, provider: Provider
) -> None:
    broker = broker_with(harness, tmp_path, provider, keys={"openai-compatible": GATEWAY_KEY})
    with client(broker) as http:
        response = http.post(
            completions("openai-compatible"),
            json=body(),
            headers=headers(grant(harness, Account.DEPLOYMENT)),
        )

    assert response.status_code == 503
    assert reason(response) == "deployment-account-unavailable"
    assert provider.seen == []


def test_a_provider_without_a_deployment_key_is_refused(
    harness: FakeHarness, tmp_path: Path, provider: Provider
) -> None:
    broker = broker_with(harness, tmp_path, provider, keys={"openai": DEPLOYMENT_OPENAI})
    with client(broker) as http:
        response = http.post(
            completions("gemini"), json=body(), headers=headers(grant(harness, Account.DEPLOYMENT))
        )

    assert response.status_code == 503
    assert reason(response) == "deployment-account-unavailable"
    assert provider.seen == []


def test_an_own_openai_account_pays(
    harness: FakeHarness, tmp_path: Path, provider: Provider
) -> None:
    broker = broker_with(harness, tmp_path, provider)
    own(broker)
    with client(broker) as http:
        response = http.post(completions(), json=body(), headers=headers(grant(harness)))

    assert response.status_code == 200
    assert response.headers[HEADER_ACCOUNT] == "own"
    assert response.headers[HEADER_PROVIDER] == "openai"
    (sent,) = provider.seen
    assert str(sent.url) == "https://api.openai.com/v1/chat/completions"
    assert sent.headers["authorization"] == f"Bearer {OWN_KEY}"
    assert [u.payer.value for u in broker.store.usage(PSEUDONYM)] == ["own"]


def test_an_own_account_call_neither_goes_through_the_gateway_nor_names_the_agent(
    harness: FakeHarness, tmp_path: Path, provider: Provider
) -> None:
    broker = broker_with(harness, tmp_path, provider, keys={"openai": GATEWAY_KEY}, gateway=GATEWAY)
    own(broker)
    with client(broker) as http:
        response = http.post(completions(), json=body(), headers=headers(grant(harness)))

    assert response.status_code == 200
    assert response.headers[HEADER_ACCOUNT] == "own"
    (sent,) = provider.seen
    assert str(sent.url) == "https://api.openai.com/v1/chat/completions"
    assert sent.headers["authorization"] == f"Bearer {OWN_KEY}"
    assert GATEWAY_TAGS_HEADER not in sent.headers


def test_an_own_openai_compatible_account_is_called_at_the_address_that_was_checked(
    harness: FakeHarness, tmp_path: Path, provider: Provider
) -> None:
    broker = broker_with(harness, tmp_path, provider, allowed=[ENDPOINT])
    own(broker, "openai-compatible", f"{ENDPOINT}/v1")
    with client(broker) as http:
        response = http.post(
            completions("openai-compatible"),
            json=body(),
            headers=headers(grant(harness, base_urls=[ENDPOINT])),
        )

    assert response.status_code == 200
    assert response.headers[HEADER_PROVIDER] == "openai-compatible"
    (sent,) = provider.seen
    assert sent.url.host == "93.184.215.14"
    assert sent.url.path == "/v1/chat/completions"
    assert sent.headers["host"] == "llm.example.ac.uk"
    assert sent.extensions["sni_hostname"] == "llm.example.ac.uk"


@pytest.mark.parametrize(
    ("path_provider", "account_provider"),
    [("openai", "gemini"), ("gemini", "openai"), ("openai", "anthropic")],
)
def test_an_account_with_another_provider_is_no_account_for_the_call(
    harness: FakeHarness,
    tmp_path: Path,
    provider: Provider,
    path_provider: str,
    account_provider: str,
) -> None:
    """An own grant ends with `model-account-missing`: the other provider never serves the call,
    and the person's key is never sent (invariant 12)."""
    broker = broker_with(harness, tmp_path, provider)
    own(broker, account_provider)
    with client(broker) as http:
        response = http.post(
            completions(path_provider), json=body(), headers=headers(grant(harness))
        )

    assert response.status_code == 403
    assert reason(response) == "model-account-missing"
    assert provider.seen == []


@pytest.mark.parametrize(
    ("path_provider", "account_provider", "key"),
    [
        ("openai", "gemini", DEPLOYMENT_OPENAI),
        ("gemini", "openai", DEPLOYMENT_GEMINI),
        ("openai", "anthropic", DEPLOYMENT_OPENAI),
    ],
)
def test_own_or_deployment_pays_with_the_deployments_key_for_the_paths_provider(
    harness: FakeHarness,
    tmp_path: Path,
    provider: Provider,
    path_provider: str,
    account_provider: str,
    key: str,
) -> None:
    broker = broker_with(harness, tmp_path, provider)
    own(broker, account_provider)
    with client(broker) as http:
        response = http.post(
            completions(path_provider),
            json=body(),
            headers=headers(grant(harness, Account.OWN_OR_DEPLOYMENT)),
        )

    assert response.status_code == 200
    assert response.headers[HEADER_ACCOUNT] == "deployment"
    assert response.headers[HEADER_PROVIDER] == path_provider
    [sent] = provider.seen
    assert sent.headers["authorization"] == f"Bearer {key}"


DECLARED = "claude-sonnet-5-5"
MAPPED = {"openai": {DECLARED: MODEL}}


def mapped_grant(harness: FakeHarness, account: Account = Account.OWN_OR_DEPLOYMENT) -> str:
    """A grant for an agent whose card declares a Claude model the profile maps, for OpenAI
    accounts, to the model the OpenAI tests call (docs/specs/model-accounts.md, The model map)."""
    return grant(harness, account, models=[DECLARED], model_map=MAPPED)


@pytest.mark.parametrize("account", [Account.OWN, Account.OWN_OR_DEPLOYMENT])
def test_a_mapped_model_is_served_on_the_persons_own_account(
    harness: FakeHarness, tmp_path: Path, provider: Provider, account: Account
) -> None:
    broker = broker_with(harness, tmp_path, provider)
    own(broker)
    with client(broker) as http:
        response = http.post(
            completions("openai"), json=body(), headers=headers(mapped_grant(harness, account))
        )

    assert response.status_code == 200, response.text
    assert response.headers[HEADER_ACCOUNT] == "own"
    assert response.headers[HEADER_PROVIDER] == "openai"
    [sent] = provider.seen
    assert sent.headers["authorization"] == f"Bearer {OWN_KEY}"


@pytest.mark.parametrize("account_provider", [None, "gemini", "anthropic"])
def test_the_deployment_never_pays_for_a_mapped_call(
    harness: FakeHarness, tmp_path: Path, provider: Provider, account_provider: str | None
) -> None:
    """A mapped model is allowed only on the person's own account with the provider it is mapped
    for; without one the call ends `model-account-missing`, even where the deployment may pay
    for a declared model (invariant 12)."""
    broker = broker_with(harness, tmp_path, provider)
    if account_provider is not None:
        own(broker, account_provider)
    with client(broker) as http:
        response = http.post(
            completions("openai"), json=body(), headers=headers(mapped_grant(harness))
        )

    assert response.status_code == 403
    assert reason(response) == "model-account-missing"
    assert provider.seen == []


def test_a_mapped_model_is_not_granted_on_another_providers_path(
    harness: FakeHarness, tmp_path: Path, provider: Provider
) -> None:
    """The map names a model for one provider; on any other path it is a model the grant does not
    allow, and the broker never chooses a model the map does not name."""
    broker = broker_with(harness, tmp_path, provider)
    own(broker, "gemini")
    with client(broker) as http:
        response = http.post(
            completions("gemini"), json=body(), headers=headers(mapped_grant(harness))
        )

    assert response.status_code == 403
    assert reason(response) == "model-not-granted"
    assert provider.seen == []


def test_an_openai_account_is_not_used_on_the_anthropic_route(
    harness: FakeHarness, tmp_path: Path, provider: Provider
) -> None:
    """An agent whose card declares an Anthropic model, called for a person with an OpenAI
    account, ends with `model-account-missing` under an own grant."""
    broker = broker_with(harness, tmp_path, provider)
    own(broker)
    with client(broker) as http:
        response = http.post(
            "/anthropic/v1/messages",
            json=body(),
            headers=headers(grant(harness, providers=["anthropic", "openai"])),
        )

    assert response.status_code == 403
    assert reason(response) == "model-account-missing"
    assert provider.seen == []


def test_an_own_account_with_a_provider_the_profile_does_not_allow_is_refused(
    harness: FakeHarness, tmp_path: Path, provider: Provider
) -> None:
    broker = broker_with(harness, tmp_path, provider)
    own(broker)
    with client(broker) as http:
        response = http.post(
            completions(),
            json=body(),
            headers=headers(grant(harness, Account.OWN_OR_DEPLOYMENT, providers=["anthropic"])),
        )

    assert response.status_code == 403
    assert reason(response) == "account-unsupported"
    assert provider.seen == []


def test_an_openai_compatible_base_url_the_profile_does_not_allow_is_refused(
    harness: FakeHarness, tmp_path: Path, provider: Provider
) -> None:
    broker = broker_with(harness, tmp_path, provider, allowed=[ENDPOINT])
    own(broker, "openai-compatible", f"{ENDPOINT}/v1")
    with client(broker) as http:
        response = http.post(
            completions("openai-compatible"), json=body(), headers=headers(grant(harness))
        )

    assert response.status_code == 403
    assert reason(response) == "base-url-refused"
    assert provider.seen == []


@pytest.mark.parametrize(
    ("status", "answered", "code"),
    [(401, 403, "model-account-rejected"), (429, 429, "model-account-limit")],
)
def test_a_failing_own_key_is_refused_without_the_providers_text(
    harness: FakeHarness, tmp_path: Path, status: int, answered: int, code: str
) -> None:
    provider = Provider(status)
    broker = broker_with(harness, tmp_path, provider)
    own(broker)
    with client(broker) as http:
        response = http.post(
            completions(), json=body(), headers=headers(grant(harness, Account.OWN_OR_DEPLOYMENT))
        )

    assert response.status_code == answered
    assert reason(response) == code
    assert HEADER_ACCOUNT not in response.headers
    assert OWN_KEY not in response.text
    assert len(provider.seen) == 1


def test_a_refusal_has_the_chat_completions_error_shape(
    harness: FakeHarness, tmp_path: Path, provider: Provider
) -> None:
    broker = broker_with(harness, tmp_path, provider)
    with client(broker) as http:
        response = http.post(completions(), json=body(), headers=headers(grant(harness)))

    assert response.status_code == 403
    error = response.json()["error"]
    assert error["code"] == reason(response) == "model-account-missing"
    assert set(error) >= {"message", "type", "code"}


@pytest.mark.parametrize(
    ("sent", "status", "code"),
    [
        (body(stream=True), 400, "streaming-unsupported"),
        ({"messages": []}, 400, "request-invalid"),
        (body(model="gpt-other"), 403, "model-not-granted"),
    ],
)
def test_a_request_the_broker_does_not_serve_is_refused(
    harness: FakeHarness,
    tmp_path: Path,
    provider: Provider,
    sent: dict[str, Any],
    status: int,
    code: str,
) -> None:
    broker = broker_with(harness, tmp_path, provider)
    own(broker)
    with client(broker) as http:
        response = http.post(completions(), json=sent, headers=headers(grant(harness)))

    assert response.status_code == status
    assert reason(response) == code
    assert provider.seen == []


def test_an_unauthenticated_call_is_refused(
    harness: FakeHarness, tmp_path: Path, provider: Provider
) -> None:
    broker = broker_with(harness, tmp_path, provider)
    with client(broker) as http:
        response = http.post(
            completions(),
            json=body(),
            headers={"authorization": "Bearer not-a-credential"},
        )

    assert response.status_code == 401
    assert reason(response) == "agent-unauthenticated"


def test_a_provider_the_broker_does_not_serve_is_not_found(
    harness: FakeHarness, tmp_path: Path, provider: Provider
) -> None:
    broker = broker_with(harness, tmp_path, provider)
    with client(broker) as http:
        response = http.post(completions("mistral"), json=body(), headers=headers(grant(harness)))

    assert response.status_code == 404
    assert provider.seen == []


def test_only_the_paying_key_reaches_the_provider(
    harness: FakeHarness, tmp_path: Path, provider: Provider
) -> None:
    broker = broker_with(harness, tmp_path, provider)
    own(broker)
    given = grant(harness)
    with client(broker) as http:
        http.post(completions(), json=body(), headers=headers(given))

    (sent,) = provider.seen
    assert sent.headers["authorization"] == f"Bearer {OWN_KEY}"
    forwarded = " ".join(f"{name}: {value}" for name, value in sent.headers.items())
    assert given not in forwarded
    assert AGENT_CREDENTIAL not in forwarded
    assert HEADER_GRANT.lower() not in sent.headers
    assert "openai-organization" not in sent.headers


def test_the_openai_client_works_through_the_broker(
    harness: FakeHarness, tmp_path: Path, provider: Provider
) -> None:
    # What an agent's adapter does (`dd_sdk.model_openai.openai_client`): its usual client, with
    # the broker's base URL, its broker credential as the API key, and the grant as a header.
    broker = broker_with(harness, tmp_path, provider)
    own(broker)
    with client(broker) as http:
        model = openai.OpenAI(
            base_url=f"{http.base_url}/openai",
            api_key=AGENT_CREDENTIAL,
            default_headers={HEADER_GRANT: grant(harness)},
            http_client=http,
            max_retries=0,
        )
        reply = model.chat.completions.create(
            model=MODEL, messages=[{"role": "user", "content": "Which standard?"}]
        )
        refused = openai.OpenAI(
            base_url=f"{http.base_url}/openai",
            api_key=AGENT_CREDENTIAL,
            http_client=http,
            max_retries=0,
        )
        with pytest.raises(openai.AuthenticationError) as raised:
            refused.chat.completions.create(
                model=MODEL, messages=[{"role": "user", "content": "Which standard?"}]
            )

    assert reply.model == MODEL
    assert reply.choices[0].message.content
    assert raised.value.response.headers[HEADER_REASON] == "grant-missing"


@pytest.mark.parametrize("status", [404, 500, 503])
def test_a_failing_provider_is_logged_with_its_status_not_its_text(
    harness: FakeHarness, tmp_path: Path, status: int, caplog: pytest.LogCaptureFixture
) -> None:
    provider = Provider(status)
    broker = broker_with(harness, tmp_path, provider)
    caplog.set_level("WARNING", logger="dd_broker")
    with client(broker) as http:
        response = http.post(
            completions(), json=body(), headers=headers(grant(harness, Account.DEPLOYMENT))
        )

    assert response.status_code == 502
    assert reason(response) == "provider-error"
    assert any(str(status) in r.getMessage() for r in caplog.records)
    assert OWN_KEY not in caplog.text
