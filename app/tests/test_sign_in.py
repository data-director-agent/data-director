"""Signing in (ADR-0029, #152): a person signs in through the OpenID Connect provider, each
request acts for the person its session names, and a request with no session is refused.

The provider is `FakeIdentityProvider`, so no test needs the network or an ORCID account.
"""

from __future__ import annotations

import json
import os
import time
import webbrowser
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import uvicorn
from starlette.testclient import TestClient
from support import check_fixture, configure_env, dist_dir, with_standards

from dd_app import app as dd_app
from dd_app.app import build_app
from dd_app.config import settings_from_env
from dd_app.governance import Governance
from dd_app.sessions import PENDING_S, SESSION_COOKIE, SessionStore
from dd_app.signin import SignIn, SignInSettings, safe_return_to
from dd_harness.identity import IdentityError, OperatorAssertion
from dd_harness.testing import TEST_PRINCIPAL, FakeIdentityProvider

PUBLIC_URL = "https://app.test"
EXAMPLE = Path(__file__).resolve().parents[1] / "config/examples/soil-chemistry.profile.json"
JOSIAH = "0000-0002-1825-0097"
ADA = "0000-0001-5000-0007"


@dataclass
class Clock:
    now: float = field(default_factory=time.time)

    def __call__(self) -> float:
        return self.now


@dataclass
class Deployment:
    idp: FakeIdentityProvider
    sign_in: SignIn
    governance: Governance
    app: Any
    clock: Clock
    runs: Path

    def browser(self) -> TestClient:
        return TestClient(self.app, base_url=PUBLIC_URL)


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    return configure_env(monkeypatch, tmp_path)


def provider_env(monkeypatch: pytest.MonkeyPatch, idp: FakeIdentityProvider) -> None:
    monkeypatch.delenv("DD_PRINCIPAL_ID")
    monkeypatch.delenv("DD_PRINCIPAL_NAME")
    monkeypatch.setenv("DD_OIDC_ISSUER", idp.issuer)
    monkeypatch.setenv("DD_OIDC_CLIENT_ID", idp.client_id)
    monkeypatch.setenv("DD_OIDC_CLIENT_SECRET", idp.client_secret)
    monkeypatch.setenv("DD_APP_PUBLIC_URL", PUBLIC_URL)


@pytest.fixture
def deployment(env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Deployment]:
    idp = FakeIdentityProvider()
    provider_env(monkeypatch, idp)
    settings = settings_from_env()
    configured = SignInSettings.from_env(os.environ, settings, "http://127.0.0.1:7860")
    assert configured is not None
    clock = Clock()
    sign_in = SignIn(
        configured,
        store=SessionStore(configured.idle_s, configured.lifetime_s, clock=clock),
        keys=idp.keys(),
        client=httpx.AsyncClient(transport=idp.transport()),
    )
    governance = with_standards(Governance.create(settings, PUBLIC_URL, sign_in.authenticator))
    app = build_app(governance, dist_dir(tmp_path), sign_in=sign_in)
    yield Deployment(idp, sign_in, governance, app, clock, env)
    governance.conductor.close()


def start(browser: TestClient, return_to: str = "/") -> str:
    """Begin signing in, and return where the provider is asked to send the person back."""
    response = browser.get("/api/sign-in", params={"return_to": return_to}, follow_redirects=False)
    assert response.status_code == 302
    location: str = response.headers["location"]
    return location


def come_back(browser: TestClient, url: str) -> Any:
    return browser.get(url, follow_redirects=False)


def sign_in(deployment: Deployment, browser: TestClient, sub: str = JOSIAH, **token: Any) -> Any:
    return come_back(browser, deployment.idp.approve(start(browser), sub, **token))


def run(browser: TestClient) -> Any:
    input = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    return browser.post("/api/runs", json={"agent_id": "standards.advisor", "input": input})


def problem_after(response: Any) -> str | None:
    """Why a sign-in was sent back to the sign-in page, or None if it was not."""
    location = urlsplit(response.headers.get("location", ""))
    if location.path != "/sign-in":
        return None
    return str(parse_qs(location.query)["problem"][0])


# The flow.


def test_a_person_signs_in_and_their_runs_act_for_them(deployment: Deployment):
    browser = deployment.browser()
    response = sign_in(deployment, browser, name="Josiah Carberry")
    assert response.status_code == 303 and response.headers["location"] == "/"

    session = browser.get("/api/session").json()
    assert session["signs_in"] is True
    assert session["principal"] == {
        "principal_id": f"https://sandbox.orcid.org/{JOSIAH}",
        "name": "Josiah Carberry",
        "assurance": "authenticated",
        "vouched_by": "https://sandbox.orcid.org",
    }
    assert session["expires_at"].endswith("Z")

    envelope = run(browser).json()["envelope"]
    assert envelope["acting_for"]["principal_id"] == f"https://sandbox.orcid.org/{JOSIAH}"
    assert envelope["acting_for"]["assurance"] == "authenticated"
    assert envelope["acting_for"]["vouched_by"] == "https://sandbox.orcid.org"
    acting_for = browser.get("/api/agents").json()["acting_for"]
    assert acting_for == {
        "name": "Josiah Carberry",
        "assurance": "authenticated",
        "vouched_by": "https://sandbox.orcid.org",
    }


def test_the_session_fixtures_are_what_the_server_says(deployment: Deployment):
    browser = deployment.browser()
    check_fixture("session-signed-out.json", browser.get("/api/session").json())
    sign_in(deployment, browser, name="Josiah Carberry")
    session = browser.get("/api/session").json()
    session["expires_at"] = "2099-01-01T00:00:00Z"  # far off, so no notice shows
    check_fixture("session-signed-in.json", session)


def test_the_app_asks_for_openid_alone_and_authenticates_with_its_secret(
    deployment: Deployment,
):
    browser = deployment.browser()
    query = parse_qs(urlsplit(start(browser)).query)
    assert query["scope"] == ["openid"]
    assert query["redirect_uri"] == [f"{PUBLIC_URL}/api/sign-in/callback"]
    assert len(query["state"][0]) >= 43 and len(query["nonce"][0]) >= 43
    sign_in(deployment, browser)
    (form,) = deployment.idp.token_requests
    assert form["client_secret"] == deployment.idp.client_secret
    assert form["grant_type"] == "authorization_code"


def test_the_session_cookie_is_opaque_and_kept_from_script(deployment: Deployment):
    response = sign_in(deployment, deployment.browser())
    (cookie,) = [c for c in response.headers.get_list("set-cookie") if c.startswith("dd_session=")]
    attributes = cookie.lower()
    assert "httponly" in attributes and "secure" in attributes and "samesite=lax" in attributes
    assert "path=/;" in attributes
    assert "eyj" not in cookie.split(";")[0].lower()  # not a JWT


def test_two_people_each_act_for_themselves(deployment: Deployment):
    josiah, ada = deployment.browser(), deployment.browser()
    sign_in(deployment, josiah, JOSIAH, name="Josiah Carberry")
    sign_in(deployment, ada, ADA, name="Ada Example")
    assert run(ada).json()["envelope"]["acting_for"]["name"] == "Ada Example"
    assert run(josiah).json()["envelope"]["acting_for"]["name"] == "Josiah Carberry"


def test_the_name_falls_back_to_the_id_when_it_is_private(deployment: Deployment):
    browser = deployment.browser()
    sign_in(deployment, browser, name=None)
    principal = browser.get("/api/session").json()["principal"]
    assert principal["name"] == f"https://sandbox.orcid.org/{JOSIAH}"


def test_the_person_returns_to_the_page_they_were_on(deployment: Deployment):
    browser = deployment.browser()
    url = deployment.idp.approve(start(browser, "/agents?agent=standards.advisor"))
    assert come_back(browser, url).headers["location"] == "/agents?agent=standards.advisor"


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "https://evil.example/",
        "//evil.example/",
        "/\\evil.example",
        "agents",
        "/api/sign-out",
    ],
)
def test_signing_in_never_returns_to_another_site(value: str | None):
    assert safe_return_to(value) == "/"


def test_no_token_reaches_the_run_store(deployment: Deployment):
    browser = deployment.browser()
    sign_in(deployment, browser)
    assert run(browser).status_code == 200
    (form,) = deployment.idp.token_requests
    for path in deployment.runs.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            assert "eyJ" not in text, path  # a JWT's header
            assert form["code"] not in text and deployment.idp.client_secret not in text


# Refusals.


PROTECTED = [
    ("GET", "/api/agents"),
    ("GET", "/api/runs"),
    ("POST", "/api/runs"),
    ("GET", "/api/runs/01900000-0000-7000-8000-000000000001"),
    ("GET", "/api/conversations"),
    ("POST", "/api/conversations"),
    ("GET", "/api/conversations/01900000-0000-7000-8000-000000000001"),
    ("POST", "/api/conversations/01900000-0000-7000-8000-000000000001/turns"),
    ("GET", "/api/examples"),
    ("GET", "/api/process-flow"),
    ("POST", "/api/feedback"),
]


@pytest.mark.parametrize(("method", "path"), PROTECTED)
def test_a_request_with_no_session_is_refused(deployment: Deployment, method: str, path: str):
    response = deployment.browser().request(method, path, json={})
    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"] == "https://w3id.org/data-director/problems/unauthenticated"
    assert list(deployment.runs.glob("*/envelope.json")) == []


def test_what_the_sign_in_page_needs_is_open(deployment: Deployment):
    browser = deployment.browser()
    assert browser.get("/api/session").json() == {
        "signs_in": True,
        "issuer": "https://sandbox.orcid.org",
        "principal": None,
        "expires_at": None,
    }
    assert browser.get("/api/about").status_code == 200
    assert browser.get("/sign-in").status_code == 200
    assert browser.get("/signed-out").status_code == 200


def test_an_unknown_session_cookie_is_refused(deployment: Deployment):
    browser = deployment.browser()
    browser.cookies.set(SESSION_COOKIE, "made-up", domain="app.test")
    assert browser.get("/api/agents").status_code == 401


def test_signing_out_ends_the_session_on_the_server(deployment: Deployment):
    browser = deployment.browser()
    sign_in(deployment, browser)
    session_id = browser.cookies.get(SESSION_COOKIE)
    assert session_id
    assert browser.post("/api/sign-out").status_code == 204
    assert browser.get("/api/agents").status_code == 401
    # The cookie the browser held is no good anywhere: the session is gone, not hidden.
    replay = deployment.browser()
    replay.cookies.set(SESSION_COOKIE, session_id, domain="app.test")
    assert replay.get("/api/agents").status_code == 401


def test_a_session_ends_when_it_has_been_idle(deployment: Deployment):
    browser = deployment.browser()
    sign_in(deployment, browser)
    deployment.clock.now += deployment.sign_in.settings.idle_s - 60
    assert browser.get("/api/agents").status_code == 200  # restarts the idle time
    deployment.clock.now += deployment.sign_in.settings.idle_s - 60
    assert browser.get("/api/agents").status_code == 200
    deployment.clock.now += deployment.sign_in.settings.idle_s
    assert browser.get("/api/agents").status_code == 401


def test_asking_when_a_session_ends_does_not_keep_it_going(deployment: Deployment):
    browser = deployment.browser()
    sign_in(deployment, browser)
    idle_s = deployment.sign_in.settings.idle_s
    first = browser.get("/api/session").json()["expires_at"]
    deployment.clock.now += idle_s / 2
    assert browser.get("/api/session").json()["expires_at"] == first
    stayed = browser.post("/api/session").json()["expires_at"]  # "Stay signed in"
    assert stayed > first
    deployment.clock.now += idle_s - 60
    assert browser.get("/api/agents").status_code == 200


def test_a_session_ends_at_its_lifetime_however_busy(deployment: Deployment):
    browser = deployment.browser()
    sign_in(deployment, browser)
    settings, began = deployment.sign_in.settings, deployment.clock.now
    # Busy all along: a request every half idle time, until one is refused.
    while browser.get("/api/agents").status_code == 200:
        deployment.clock.now += settings.idle_s / 2
    assert (
        settings.lifetime_s <= deployment.clock.now - began < settings.lifetime_s + settings.idle_s
    )
    assert browser.get("/api/session").json()["principal"] is None


def test_a_callback_carried_to_another_browser_is_refused(deployment: Deployment):
    url = deployment.idp.approve(start(deployment.browser()))
    other = deployment.browser()
    assert problem_after(come_back(other, url)) == "failed"
    assert other.get("/api/agents").status_code == 401


def test_a_callback_is_used_once(deployment: Deployment):
    browser = deployment.browser()
    authorize = start(browser)
    url = deployment.idp.approve(authorize)
    state = browser.cookies.get("dd_sign_in")
    assert state is not None
    assert come_back(browser, url).status_code == 303
    browser.cookies.set("dd_sign_in", state, domain="app.test", path="/api/sign-in")
    assert problem_after(come_back(browser, url)) == "failed"


@pytest.mark.parametrize(
    "token",
    [
        {"nonce": "another-nonce"},
        {"issued_at": int(time.time()) - 3600},
        {"audience": "APP-ANOTHERCLIENT"},
        {"issuer": "https://orcid.org"},
    ],
    ids=["wrong nonce", "expired", "another audience", "another issuer"],
)
def test_a_token_that_fails_verification_opens_no_session(
    deployment: Deployment, token: dict[str, Any]
):
    browser = deployment.browser()
    assert problem_after(sign_in(deployment, browser, **token)) == "failed"
    assert browser.get("/api/agents").status_code == 401


def test_a_sign_in_left_too_long_must_be_started_again(deployment: Deployment):
    browser = deployment.browser()
    url = deployment.idp.approve(start(browser))
    deployment.clock.now += PENDING_S + 1
    assert problem_after(come_back(browser, url)) == "failed"


def test_a_person_who_declines_is_told_so(deployment: Deployment):
    browser = deployment.browser()
    response = come_back(browser, deployment.idp.deny(start(browser)))
    assert problem_after(response) == "declined"
    assert browser.get("/api/agents").status_code == 401


def test_a_code_the_provider_refuses_opens_no_session(deployment: Deployment):
    browser = deployment.browser()
    authorize = start(browser)
    url = deployment.idp.approve(authorize)
    query = parse_qs(urlsplit(url).query)
    forged = f"{PUBLIC_URL}/api/sign-in/callback?code=forged&state={query['state'][0]}"
    assert problem_after(come_back(browser, forged)) == "failed"


# Configuration and start-up.


def test_a_development_server_acts_for_the_operator_and_says_so(env: Path, tmp_path: Path):
    governance = Governance.create(settings_from_env(), PUBLIC_URL)
    browser = TestClient(build_app(governance, dist_dir(tmp_path)), base_url=PUBLIC_URL)
    session = browser.get("/api/session").json()
    assert session["signs_in"] is False
    assert session["principal"]["name"] == TEST_PRINCIPAL.name
    assert session["principal"]["assurance"] == "asserted"
    check_fixture("session-development.json", session)
    assert browser.get("/api/sign-in", follow_redirects=False).status_code == 404
    assert browser.post("/api/sign-out").status_code == 204
    assert browser.get("/api/agents").status_code == 200


def test_a_provider_needs_the_sign_in(env: Path, monkeypatch: pytest.MonkeyPatch):
    provider_env(monkeypatch, FakeIdentityProvider())
    with pytest.raises(IdentityError, match="signs people in"):
        Governance.create(settings_from_env(), PUBLIC_URL)


def test_the_app_acts_for_whom_it_signed_in(deployment: Deployment, tmp_path: Path):
    other = Governance(deployment.governance.conductor, OperatorAssertion(TEST_PRINCIPAL))
    with pytest.raises(IdentityError):
        build_app(other, tmp_path / "dist", sign_in=deployment.sign_in)


@pytest.fixture
def started(env: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """What `main` built, in place of serving it or opening a browser."""
    seen: dict[str, Any] = {}

    def spy_build(governance: Governance, **settings: Any) -> str:
        seen.update(governance=governance, **settings)
        return "app"

    for variable in ("DD_APP_HOST", "DD_APP_PORT", "DD_HARNESS_URL"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(dd_app, "build_app", spy_build)
    monkeypatch.setattr(uvicorn, "run", lambda app, *, host, port: None)
    monkeypatch.setattr(webbrowser, "open", lambda url: True)
    return seen


def test_a_server_with_a_provider_signs_people_in(
    started: dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    provider_env(monkeypatch, FakeIdentityProvider())
    monkeypatch.setenv("DD_APP_HOST", "0.0.0.0")
    assert dd_app.main() == 0
    sign_in = started["sign_in"]
    assert isinstance(sign_in, SignIn)
    assert started["governance"].authenticator is sign_in.authenticator
    assert sign_in.settings.redirect_uri == f"{PUBLIC_URL}/api/sign-in/callback"
    assert "not authenticated" not in capsys.readouterr().err


def test_a_server_with_no_provider_signs_nobody_in(started: dict[str, Any]):
    assert dd_app.main() == 0
    assert started["sign_in"] is None


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"DD_PRINCIPAL_ID": "https://orcid.org/0000-0002-1825-0097"}, "both set"),
        ({"DD_OIDC_CLIENT_SECRET": None}, "DD_OIDC_CLIENT_SECRET unset"),
        ({"DD_OIDC_CLIENT_ID": None}, "DD_OIDC_CLIENT_ID unset"),
        ({"DD_SESSION_IDLE_S": "soon"}, "DD_SESSION_IDLE_S"),
        ({"DD_SESSION_LIFETIME_S": "0"}, "DD_SESSION_LIFETIME_S"),
    ],
)
def test_a_provider_configured_wrongly_stops_start_up(
    started: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    change: dict[str, str | None],
    message: str,
):
    provider_env(monkeypatch, FakeIdentityProvider())
    for variable, value in change.items():
        if value is None:
            monkeypatch.delenv(variable)
        else:
            monkeypatch.setenv(variable, value)
    with pytest.raises(SystemExit, match=message):
        dd_app.main()


def test_the_client_secret_can_be_read_from_a_file(
    started: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    idp = FakeIdentityProvider()
    provider_env(monkeypatch, idp)
    monkeypatch.delenv("DD_OIDC_CLIENT_SECRET")
    secret = tmp_path / "client-secret"
    secret.write_text(idp.client_secret + "\n", encoding="utf-8")
    monkeypatch.setenv("DD_OIDC_CLIENT_SECRET_FILE", str(secret))
    dd_app.main()
    assert started["sign_in"].settings.client_secret == idp.client_secret
    assert idp.client_secret not in repr(started["sign_in"].settings)
