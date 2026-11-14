"""A person's own model account (docs/specs/model-accounts.md, Enrolment; issue #807): the app
issues a single-use enrolment ticket for the person signed in, and the browser takes it, with the
key, straight to the model broker. The app and the harness never receive the key.

The broker runs in process here (`dd_broker`, a development dependency of the app's tests only),
with the provider faked by `httpx.MockTransport`, so no test needs the network or a real key.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Awaitable, Callable, Iterator, MutableMapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest
from starlette.testclient import TestClient
from support import JSON_HEADERS, check_fixture, configure_env, dist_dir, with_standards

from dd_app.app import build_app
from dd_app.config import EXAMPLE_PROFILE, settings_from_env
from dd_app.governance import Governance
from dd_app.model_accounts import BROKER_URL_VARIABLE, broker_path
from dd_broker.agents import AgentCredentials
from dd_broker.app import Broker
from dd_broker.app import build_app as build_broker
from dd_broker.enrolment import ACCOUNT_PATH
from dd_broker.grants import GrantVerifier, HarnessKeys, TicketVerifier
from dd_broker.store import Store
from dd_harness.sessions import SessionStore
from dd_harness.settings import MODEL_GRANT_SETTINGS
from dd_harness.signin import SignIn, SignInSettings
from dd_harness.testing import FakeIdentityProvider, GrantKeys
from dd_sdk.credentials import ConfigError
from dd_sdk.model_grant import Payer

PUBLIC_URL = "https://app.test"
BROKER_PATH = "/broker"
JOSIAH = "0000-0002-1825-0097"
ADA = "0000-0001-5000-0007"
EXAMPLE = Path(__file__).resolve().parents[1] / "config/examples/soil-chemistry.profile.json"
# Distinctive enough that finding it anywhere means it leaked.
SENTINEL = "sk-ant-api03-sentinel-807-e4b19d2a7c"
MODEL = "claude-sonnet-5-5"

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGI = Callable[[Scope, Receive, Send], Awaitable[None]]


class Recorder:
    """An ASGI wrapper that keeps every byte the app is sent and sends back, as the app's request
    log would see them."""

    def __init__(self, app: ASGI) -> None:
        self.app = app
        self.seen: list[bytes] = []

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            query = scope.get("query_string", b"").decode()
            self.seen.append(f"{scope['method']} {scope['path']}?{query}".encode())
            self.seen.extend(name + b": " + value for name, value in scope.get("headers", []))

        async def receiving() -> Message:
            message = await receive()
            self.seen.append(bytes(message.get("body", b"")))
            return message

        async def sending(message: Message) -> None:
            self.seen.append(bytes(message.get("body", b"")))
            self.seen.extend(name + b": " + value for name, value in message.get("headers", []))
            await send(message)

        await self.app(scope, receiving, sending)


@dataclass
class Deployment:
    idp: FakeIdentityProvider
    keys: GrantKeys
    governance: Governance
    app: Recorder
    root: Path
    kek: bytes = field(default_factory=lambda: os.urandom(32), repr=False)
    store: Store | None = None

    def browser(self) -> TestClient:
        return TestClient(self.app, base_url=PUBLIC_URL)

    def broker(self, provider: httpx.MockTransport) -> TestClient:
        """The model broker, trusting this harness's published keys, as the reverse proxy passes
        the browser's requests to it."""
        minter = self.governance.conductor.model_grants
        assert minter is not None
        store = Store(self.root / "broker" / "broker.sqlite3", self.kek)
        self.store = store
        keys = HarnessKeys(minter.jwks)
        broker = Broker(
            store=store,
            verifier=GrantVerifier(keys, self.keys.subject_key),
            tickets=TicketVerifier(keys, self.keys.subject_key, store),
            agents=AgentCredentials({}),
            transport=provider,
        )
        return TestClient(build_broker(broker))


def grant_env(keys: GrantKeys) -> dict[str, str]:
    return dict(
        zip(
            MODEL_GRANT_SETTINGS,
            (
                json.dumps(keys.signing_key.as_dict(private=True)),
                keys.subject_key.as_pem(private=False).decode(),
                keys.secret.hex(),
            ),
            strict=True,
        )
    )


# What a profile adds to let people's own accounts pay (docs/specs/model-accounts.md).
OWN_ACCOUNTS = """
model_accounts:
  own: allowed
  fallback: deployment
  providers:
    - provider: anthropic
"""


def make_deployment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    grants: bool,
    broker: str | None,
    own: bool = True,
) -> Deployment:
    configure_env(monkeypatch, tmp_path)
    if own:
        profile = tmp_path / "profile.yaml"
        profile.write_text(
            EXAMPLE_PROFILE.read_text(encoding="utf-8") + OWN_ACCOUNTS, encoding="utf-8"
        )
        monkeypatch.setenv("DD_PROFILE", str(profile))
    idp = FakeIdentityProvider()
    monkeypatch.delenv("DD_PRINCIPAL_ID")
    monkeypatch.delenv("DD_PRINCIPAL_NAME")
    monkeypatch.setenv("DD_OIDC_ISSUER", idp.issuer)
    monkeypatch.setenv("DD_OIDC_CLIENT_ID", idp.client_id)
    monkeypatch.setenv("DD_OIDC_CLIENT_SECRET", idp.client_secret)
    monkeypatch.setenv("DD_APP_PUBLIC_URL", PUBLIC_URL)
    keys = GrantKeys()
    if grants:
        for name, value in grant_env(keys).items():
            monkeypatch.setenv(name, value)
    settings = settings_from_env()
    configured = SignInSettings.from_env(
        os.environ, settings, "http://127.0.0.1:7860", public_url_variable="DD_APP_PUBLIC_URL"
    )
    assert configured is not None
    sign_in = SignIn(
        configured,
        store=SessionStore(configured.idle_s, configured.lifetime_s),
        keys=idp.keys(),
        client=httpx.AsyncClient(transport=idp.transport()),
    )
    governance = with_standards(Governance.create(settings, PUBLIC_URL, sign_in.authenticator))
    app = build_app(governance, dist_dir(tmp_path), sign_in=sign_in, model_broker_path=broker)
    return Deployment(idp, keys, governance, Recorder(app), tmp_path)


@pytest.fixture
def deployment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Deployment]:
    deployed = make_deployment(monkeypatch, tmp_path, grants=True, broker=BROKER_PATH)
    yield deployed
    deployed.governance.conductor.close()


def sign_in(deployment: Deployment, browser: TestClient, sub: str = JOSIAH) -> None:
    started = browser.get("/api/sign-in", params={"return_to": "/profile"}, follow_redirects=False)
    back = browser.get(
        deployment.idp.approve(started.headers["location"], sub), follow_redirects=False
    )
    assert back.status_code == 303


def ticket(browser: TestClient) -> dict[str, Any]:
    answer = browser.post("/api/model-account/ticket", headers=JSON_HEADERS)
    assert answer.status_code == 200
    body: dict[str, Any] = answer.json()
    return body


def provider(status: int = 200) -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(status, json={"data": []}))


# The ticket.


def test_a_signed_in_person_is_issued_a_ticket_naming_only_their_pseudonym(
    deployment: Deployment,
) -> None:
    browser = deployment.browser()
    sign_in(deployment, browser)
    assert browser.get("/api/session").json()["model_accounts"] is True

    answer = browser.post("/api/model-account/ticket", headers=JSON_HEADERS)
    assert answer.status_code == 200
    assert answer.headers["cache-control"] == "no-store"
    body = answer.json()
    assert body["broker_url"] == BROKER_PATH

    opened = deployment.keys.open(body["ticket"])
    minter = deployment.governance.conductor.model_grants
    assert minter is not None
    principal = deployment.governance.authenticator.principal_for(
        {"cookie": "; ".join(f"{k}={v}" for k, v in browser.cookies.items())}
    )
    assert opened.pseudonym == minter.pseudonym(principal)
    assert JOSIAH not in json.dumps(opened.claims)
    check_fixture(
        "model-account-ticket.json",
        body | {"ticket": "eyJ.ticket", "expires_at": "2026-11-13T12:02:00Z"},
    )


def test_two_people_are_issued_tickets_for_two_pseudonyms(deployment: Deployment) -> None:
    josiah, ada = deployment.browser(), deployment.browser()
    sign_in(deployment, josiah)
    sign_in(deployment, ada, ADA)
    first = deployment.keys.open(ticket(josiah)["ticket"])
    again = deployment.keys.open(ticket(josiah)["ticket"])
    other = deployment.keys.open(ticket(ada)["ticket"])
    assert first.pseudonym == again.pseudonym != other.pseudonym
    assert first.claims["jti"] != again.claims["jti"]


def test_nobody_signed_in_is_issued_no_ticket(deployment: Deployment) -> None:
    answer = deployment.browser().post("/api/model-account/ticket", headers=JSON_HEADERS)
    assert answer.status_code == 401


@pytest.mark.parametrize(
    ("grants", "broker", "own"),
    [(True, None, True), (False, BROKER_PATH, False), (True, BROKER_PATH, False)],
)
def test_a_deployment_that_does_not_offer_own_accounts_issues_no_ticket(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, grants: bool, broker: str | None, own: bool
) -> None:
    """Without grants, without the broker, or with a profile that keeps own accounts off."""
    deployed = make_deployment(monkeypatch, tmp_path, grants=grants, broker=broker, own=own)
    try:
        browser = deployed.browser()
        sign_in(deployed, browser)
        assert browser.get("/api/session").json()["model_accounts"] is False
        answer = browser.post("/api/model-account/ticket", headers=JSON_HEADERS)
        assert answer.status_code == 404
        assert answer.json()["type"].endswith("model-accounts-unavailable")
    finally:
        deployed.governance.conductor.close()


@pytest.mark.parametrize("value", ["https://broker.test", "broker", "//evil.test/x", "/a b", "/"])
def test_the_broker_must_be_a_path_on_the_apps_own_origin(value: str) -> None:
    if value == "/":
        assert broker_path({BROKER_URL_VARIABLE: value}) is None
        return
    with pytest.raises(ConfigError):
        broker_path({BROKER_URL_VARIABLE: value})


def test_the_broker_path_is_read_without_its_trailing_slash() -> None:
    assert broker_path({BROKER_URL_VARIABLE: "/broker/"}) == BROKER_PATH
    assert broker_path({}) is None


# The key goes to the broker alone.


def test_the_browser_enrols_with_the_broker_and_the_app_never_sees_the_key(
    deployment: Deployment,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    caplog.set_level(logging.DEBUG)
    browser = deployment.browser()
    sign_in(deployment, browser)
    broker = deployment.broker(provider(200))

    with broker:
        enrolled = broker.put(
            ACCOUNT_PATH,
            json={"provider": "anthropic", "key": SENTINEL},
            headers={"authorization": f"Bearer {ticket(browser)['ticket']}"},
        )
        assert enrolled.status_code == 200
        # The page reads the label and the person's token use with a fresh ticket.
        read = broker.get(
            ACCOUNT_PATH, headers={"authorization": f"Bearer {ticket(browser)['ticket']}"}
        )
    account = read.json()["account"]
    assert account["label"].endswith(SENTINEL[-4:])

    # The person then works as usual: a run, with every record the app and harness keep.
    input = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    started = browser.post("/api/runs", json={"agent_id": "advisor.standards", "input": input})
    assert started.status_code in (200, 201)

    needle = SENTINEL.encode()
    assert all(needle not in seen for seen in deployment.app.seen)
    captured = capsys.readouterr()
    for text in (caplog.text, captured.out, captured.err):
        assert SENTINEL not in text
    for path in deployment.root.rglob("*"):
        if path.is_file():
            assert needle not in path.read_bytes(), path
    # Nor does the label the person is shown leave the broker's store
    # (docs/specs/model-accounts.md, invariant 9): a run records whose account paid, never which.
    label = account["label"].encode()
    broker_store = deployment.root / "broker"
    for path in deployment.root.rglob("*"):
        if path.is_file() and not path.is_relative_to(broker_store):
            assert label not in path.read_bytes(), path


def test_removing_the_account_erases_it(deployment: Deployment) -> None:
    browser = deployment.browser()
    sign_in(deployment, browser)
    with deployment.broker(provider(200)) as broker:

        def bearer() -> dict[str, str]:
            return {"authorization": f"Bearer {ticket(browser)['ticket']}"}

        broker.put(ACCOUNT_PATH, json={"provider": "anthropic", "key": SENTINEL}, headers=bearer())
        removed = broker.delete(ACCOUNT_PATH, headers=bearer())
        read = broker.get(ACCOUNT_PATH, headers=bearer())
    assert removed.status_code == 204
    assert read.json()["account"] is None


# What the page is drawn from: the broker's answers, kept as fixtures for the shell's tests.


def test_the_broker_answers_the_page_draws(deployment: Deployment) -> None:
    browser = deployment.browser()
    sign_in(deployment, browser)

    def bearer() -> dict[str, str]:
        return {"authorization": f"Bearer {ticket(browser)['ticket']}"}

    with deployment.broker(provider(200)) as broker:
        check_fixture("model-account-none.json", broker.get(ACCOUNT_PATH, headers=bearer()).json())
        broker.put(
            ACCOUNT_PATH,
            json={"provider": "anthropic", "key": "sk-ant-api03-fixture-key-7f3a"},
            headers=bearer(),
        )
        pseudonym = deployment.keys.open(ticket(browser)["ticket"]).pseudonym
        assert deployment.store is not None
        for model, used in ((MODEL, (18240, 2310)), ("claude-haiku-5-5", (5120, 840))):
            deployment.store.add_usage(
                pseudonym,
                payer=Payer.OWN,
                provider="anthropic",
                model=model,
                input_tokens=used[0],
                output_tokens=used[1],
            )
        held = broker.get(ACCOUNT_PATH, headers=bearer()).json()
    # Fixed times, so the fixture does not change from one day to the next.
    held["account"]["created"] = "2026-11-13T12:00:00+00:00"
    for row in held["usage"]:
        row["day"] = "2026-11-13"
    check_fixture("model-account.json", held)

    with deployment.broker(provider(401)) as broker:
        rejected = broker.put(
            ACCOUNT_PATH,
            json={"provider": "anthropic", "key": "sk-ant-api03-fixture-key-7f3a"},
            headers=bearer(),
        )
    assert rejected.status_code == 422
    check_fixture("model-account-rejected.json", rejected.json())
