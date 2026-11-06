"""A deployed workbench admits its admins only (docs/specs/policy-and-identity.md, #549).

Admins sign in through the harness's OpenID Connect flow. Anyone else is refused at the callback
and gets no session, every route but signing in needs an admin's session, and a run acts for the
admin who started it. The provider is `FakeIdentityProvider`, so no test needs the network.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from dd_agent_example_hello.agent import HelloWorld
from dd_harness.identity import OperatorAssertion
from dd_harness.settings import Settings
from dd_harness.signin import SignIn, SignInSettings
from dd_harness.testing import TEST_PRINCIPAL, FakeIdentityProvider, make_conductor, request
from dd_sdk.contract.models import Principal, to_document
from dd_sdk.credentials import ConfigError
from workbench.transport.app import build_app
from workbench.transport.signin import (
    ADMINS_VARIABLE,
    SESSION_COOKIE,
    Admins,
    admin_sign_in,
    admins_from_env,
)

BASE = "https://workbench.test:8443"
JOSIAH = "0000-0002-1825-0097"
ADA = "0000-0001-5000-0007"
PAGE = {"accept": "text/html,application/xhtml+xml"}


def agui_body(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "threadId": "t1",
        "runId": "r1",
        "messages": [],
        "state": {},
        "tools": [],
        "context": [],
        "forwardedProps": {"request": doc},
    }


def hello() -> dict[str, Any]:
    return {
        **to_document(request("example.hello")),
        "input": {"schema_class": "Salutation", "greeted_name": "Ada"},
    }


def events(text: str) -> list[dict[str, Any]]:
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


class Workbench:
    """A workbench that signs admins in, and a fake ORCID that signs anyone in."""

    def __init__(self, runs_dir: Path, admins: set[str]) -> None:
        self.idp = FakeIdentityProvider()
        self.admins = admins
        settings = SignInSettings(
            provider=self.idp.provider,
            client_secret=self.idp.client_secret,
            public_url=BASE,
        )
        self.sign_in = SignIn(
            settings,
            session_cookie=SESSION_COOKIE,
            # Read at each call, so a test can take someone off the list.
            admit=lambda p: Admins(self.idp.issuer, frozenset(self.admins))(p),
            keys=self.idp.keys(),
            client=httpx.AsyncClient(transport=self.idp.transport()),
        )
        self.conductor = make_conductor(runs_dir, HelloWorld())
        self.app = build_app(
            self.conductor, OperatorAssertion(TEST_PRINCIPAL), BASE, sign_in=self.sign_in
        )

    def browse(self, steps: Callable[[httpx.AsyncClient], Awaitable[Any]]) -> Any:
        async def go() -> Any:
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(transport=transport, base_url=BASE) as browser:
                return await steps(browser)

        return asyncio.run(go())


async def sign_in(workbench: Workbench, browser: httpx.AsyncClient, sub: str) -> httpx.Response:
    started = await browser.get("/api/sign-in", params={"return_to": "/viewer/"})
    assert started.status_code == 302
    return await browser.get(workbench.idp.approve(started.headers["location"], sub))


@pytest.fixture
def workbench(runs_dir: Path):
    found = Workbench(runs_dir, {JOSIAH})
    yield found
    found.conductor.close()


# Without a session.


def test_a_page_with_no_session_is_sent_to_sign_in_and_back(workbench: Workbench):
    async def steps(browser: httpx.AsyncClient) -> httpx.Response:
        return await browser.get("/viewer/inspect.html?invocation_id=x", headers=PAGE)

    response = workbench.browse(steps)
    assert response.status_code == 303
    location = urlsplit(response.headers["location"])
    assert location.path == "/api/sign-in"
    assert parse_qs(location.query)["return_to"] == ["/viewer/inspect.html?invocation_id=x"]


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/runs"),
        ("GET", "/agents"),
        ("GET", "/conversations"),
        ("GET", "/samples"),
        ("GET", "/viewer/js/common.js"),
        ("GET", "/agui/runs/01900000-0000-7000-8000-000000000001"),
        ("POST", "/agui"),
    ],
)
def test_a_request_with_no_session_is_refused(workbench: Workbench, method: str, path: str):
    async def steps(browser: httpx.AsyncClient) -> httpx.Response:
        return await browser.request(method, path, json=agui_body(hello()))

    response = workbench.browse(steps)
    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"].endswith("/unauthenticated")
    assert list(workbench.conductor.store.iter_envelopes()) == []


def test_session_says_the_workbench_signs_people_in(workbench: Workbench):
    async def steps(browser: httpx.AsyncClient) -> Any:
        return (await browser.get("/api/session")).json()

    assert workbench.browse(steps) == {"signs_in": True, "principal": None}


# Admins.


def test_an_admin_signs_in_and_runs_act_for_them(workbench: Workbench):
    async def steps(browser: httpx.AsyncClient) -> tuple[httpx.Response, Any, Any, int]:
        back = await sign_in(workbench, browser, JOSIAH)
        session = (await browser.get("/api/session")).json()
        run = events((await browser.post("/agui", json=agui_body(hello()))).text)
        page = await browser.get("/viewer/", headers=PAGE)
        return back, session, run, page.status_code

    back, session, run, page = workbench.browse(steps)
    assert back.status_code == 303 and back.headers["location"] == "/viewer/"
    (cookie,) = [c for c in back.headers.get_list("set-cookie") if c.startswith(SESSION_COOKIE)]
    assert "httponly" in cookie.lower() and "secure" in cookie.lower()
    assert session["principal"]["principal_id"] == f"https://sandbox.orcid.org/{JOSIAH}"
    envelope = run[-1]["result"]
    assert envelope["acting_for"]["principal_id"] == f"https://sandbox.orcid.org/{JOSIAH}"
    assert envelope["acting_for"]["assurance"] == "authenticated"
    assert page == 200


def test_someone_not_on_the_list_is_refused_and_gets_no_session(workbench: Workbench):
    async def steps(browser: httpx.AsyncClient) -> tuple[httpx.Response, int]:
        back = await sign_in(workbench, browser, ADA)
        return back, (await browser.get("/runs")).status_code

    back, runs = workbench.browse(steps)
    assert back.status_code == 403
    assert ADA in back.text and "not an admin" in back.text
    assert not [c for c in back.headers.get_list("set-cookie") if c.startswith(SESSION_COOKIE)]
    assert runs == 401


def test_an_admin_taken_off_the_list_is_refused_at_once(workbench: Workbench):
    async def steps(browser: httpx.AsyncClient) -> tuple[int, int]:
        await sign_in(workbench, browser, JOSIAH)
        before = (await browser.get("/runs")).status_code
        workbench.admins.clear()
        return before, (await browser.get("/runs")).status_code

    assert workbench.browse(steps) == (200, 403)


def test_signing_out_ends_the_session(workbench: Workbench):
    async def steps(browser: httpx.AsyncClient) -> tuple[int, int]:
        await sign_in(workbench, browser, JOSIAH)
        signed_out = (await browser.post("/api/sign-out")).status_code
        return signed_out, (await browser.get("/runs")).status_code

    assert workbench.browse(steps) == (204, 401)


def test_the_apps_session_cookie_names_no_session_here(workbench: Workbench):
    # The app is served on the same host, so its cookie reaches the workbench too.
    async def steps(browser: httpx.AsyncClient) -> int:
        await sign_in(workbench, browser, JOSIAH)
        session_id = browser.cookies.get(SESSION_COOKIE)
        browser.cookies.clear()
        browser.cookies.set("dd_session", session_id or "", domain="workbench.test")
        return (await browser.get("/runs")).status_code

    assert workbench.browse(steps) == 401


def test_a2a_takes_delegation_callbacks_only(workbench: Workbench):
    from a2a.client import ClientConfig, create_client
    from a2a.helpers import new_data_part, new_message
    from a2a.types import Role, SendMessageRequest, TaskState

    async def steps(browser: httpx.AsyncClient) -> Any:
        assert (await browser.get("/.well-known/agent-card.json")).status_code == 200
        client = await create_client(
            agent=BASE, client_config=ClientConfig(streaming=False, httpx_client=browser)
        )
        message = new_message([new_data_part(hello())], role=Role.ROLE_USER)
        last = None
        async for answer in client.send_message(SendMessageRequest(message=message)):
            last = answer
        return last

    answer = workbench.browse(steps)
    assert answer.task.status.state == TaskState.TASK_STATE_FAILED
    assert list(workbench.conductor.store.iter_envelopes()) == []


# Without a provider: a development server, as before.


def test_a_development_server_gates_nothing(runs_dir: Path):
    conductor = make_conductor(runs_dir, HelloWorld())
    app = build_app(conductor, OperatorAssertion(TEST_PRINCIPAL), BASE)

    async def go() -> tuple[int, Any, Any]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE) as browser:
            runs = (await browser.get("/runs")).status_code
            session = (await browser.get("/api/session")).json()
            run = events((await browser.post("/agui", json=agui_body(hello()))).text)
            return runs, session, run

    try:
        runs, session, run = asyncio.run(go())
    finally:
        conductor.close()
    assert runs == 200
    assert session == {"signs_in": False, "principal": None}
    assert run[-1]["result"]["acting_for"]["assurance"] == "asserted"


# Configuration.


@pytest.mark.parametrize(
    ("value", "admins"),
    [
        (JOSIAH, {JOSIAH}),
        (f"{JOSIAH}, https://orcid.org/{ADA}", {JOSIAH, ADA}),
        (f" {JOSIAH}\n0000-0002-1694-233X ", {JOSIAH, "0000-0002-1694-233X"}),
    ],
)
def test_admins_are_orcid_ids_bare_or_as_urls(value: str, admins: set[str]):
    assert admins_from_env({ADMINS_VARIABLE: value}) == admins


@pytest.mark.parametrize("value", ["", " , ", "josiah", "0000-0002-1825", f"{JOSIAH},ada@x.org"])
def test_an_empty_or_mistyped_list_stops_start_up(value: str):
    with pytest.raises(ConfigError, match=ADMINS_VARIABLE):
        admins_from_env({ADMINS_VARIABLE: value})


def principal(principal_id: str, vouched_by: str) -> Principal:
    return Principal(
        principal_id=principal_id,
        name="Someone",
        principal_kind="person",
        assurance="authenticated",
        vouched_by=vouched_by,
    )


def test_an_admin_is_listed_and_vouched_for_by_the_deployments_issuer():
    admins = Admins("https://orcid.org", frozenset({JOSIAH}))
    assert admins(principal(f"https://orcid.org/{JOSIAH}", "https://orcid.org"))
    assert not admins(principal(f"https://orcid.org/{ADA}", "https://orcid.org"))
    # The same iD at the sandbox is another person, as far as a production workbench knows.
    assert not admins(principal(f"https://sandbox.orcid.org/{JOSIAH}", "https://orcid.org"))
    assert not admins(principal(f"https://orcid.org/{JOSIAH}", "https://sandbox.orcid.org"))


def settings(tmp_path: Path, **changes: Any) -> Settings:
    return Settings(
        runs_dir=tmp_path,
        profile=tmp_path / "profile.yaml",
        agents_config=tmp_path / "agents.yaml",
        sources_config=tmp_path / "sources.yaml",
        **changes,
    )


def test_sign_in_is_configured_from_the_environment(tmp_path: Path):
    idp = FakeIdentityProvider()
    configured = settings(tmp_path, oidc_issuer=idp.issuer, oidc_client_id=idp.client_id)
    env = {
        "DD_OIDC_CLIENT_SECRET": idp.client_secret,
        "DD_WORKBENCH_PUBLIC_URL": BASE,
        ADMINS_VARIABLE: JOSIAH,
    }
    found = admin_sign_in(env, configured, "http://127.0.0.1:8000")
    assert found is not None
    assert found.settings.redirect_uri == f"{BASE}/api/sign-in/callback"
    assert found.authenticator.cookie_name == SESSION_COOKIE
    with pytest.raises(ConfigError, match=ADMINS_VARIABLE):
        admin_sign_in({**env, ADMINS_VARIABLE: ""}, configured, "http://127.0.0.1:8000")
    assert admin_sign_in(env, settings(tmp_path), "http://127.0.0.1:8000") is None
