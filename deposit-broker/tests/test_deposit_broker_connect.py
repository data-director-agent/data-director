"""A person connects their own repository account to the deposit broker through OAuth, or by
pasting a token, and can disconnect it; the token is sealed at rest and never returned."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from deposit_broker_support import (
    CLIENT,
    OTHER,
    PSEUDONYM,
    SANDBOX,
    TOKEN,
    Running,
    make_broker,
)

from dd_deposit_broker.app import COOKIE
from dd_deposit_broker.seal import SealError
from dd_deposit_broker.store import Store, Tokens
from dd_sdk.deposit_grant import HEADER_REASON


@pytest.fixture
def running(tmp_path: Path) -> Running:
    return make_broker(tmp_path)


def callback(running: Running, cookie: str, **params: str):
    """The repository sending the browser back, with `cookie` as the browser holds it."""
    running.client.cookies.clear()
    running.client.cookies.set(COOKIE, cookie)
    return running.client.get("/connect/zenodo/callback", params=params, follow_redirects=False)


def start(running: Running, ticket: str | None = None, base_url: str = SANDBOX):
    return running.client.post(
        "/connect/zenodo/start",
        content=f"ticket={ticket or running.harness.ticket()}&base_url={base_url}",
        headers={"content-type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )


def test_the_options_name_each_repository_and_how_it_is_connected(running: Running) -> None:
    answer = running.client.get("/connect/options")
    assert answer.json() == {
        "repositories": [{"base_url": SANDBOX, "transport": "zenodo", "oauth": True}]
    }


def test_connecting_through_oauth_asks_only_to_deposit_and_keeps_the_tokens(
    running: Running,
) -> None:
    started = start(running)
    assert started.status_code == 303
    location = urlsplit(started.headers["location"])
    assert (location.scheme, location.netloc, location.path) == (
        "https",
        "sandbox.zenodo.org",
        "/oauth/authorize",
    )
    query = {k: v[0] for k, v in parse_qs(location.query).items()}
    assert query["scope"] == "deposit:write"
    assert query["client_id"] == CLIENT.client_id
    assert query["redirect_uri"] == "https://dd.test/deposit-broker/connect/zenodo/callback"
    assert query["code_challenge_method"] == "S256"
    cookie = started.cookies[COOKIE]

    back = callback(running, cookie, code="good-code", state=query["state"])
    assert back.status_code == 303
    assert back.headers["location"] == "https://dd.test/settings?repository=connected"
    account = running.broker.store.account(PSEUDONYM, SANDBOX)
    assert account is not None
    assert account.method == "oauth"
    assert account.tokens.access_token == "oauth-access-1-xyz"
    assert account.tokens.refresh_token == "refresh-1"
    # The state is finished once.
    again = callback(running, cookie, code="good-code", state=query["state"])
    assert "repository_error" in again.headers["location"]


def test_an_authorisation_finishes_only_in_the_browser_that_started_it(running: Running) -> None:
    """Someone who starts an authorisation for themselves and sends the link to another person
    cannot have that person's account kept under their own name."""
    started = start(running)
    state = parse_qs(urlsplit(started.headers["location"]).query)["state"][0]
    back = callback(running, "someone-elses-browser", code="good-code", state=state)
    assert back.headers["location"] == "https://dd.test/settings?repository_error=ticket-invalid"
    assert running.broker.store.account(PSEUDONYM, SANDBOX) is None


def test_a_refused_authorisation_keeps_nothing(running: Running) -> None:
    started = start(running)
    state = parse_qs(urlsplit(started.headers["location"]).query)["state"][0]
    back = callback(running, started.cookies[COOKIE], error="access_denied", state=state)
    assert "repository_error=account-rejected" in back.headers["location"]
    assert running.broker.store.account(PSEUDONYM, SANDBOX) is None


def test_oauth_cannot_start_without_a_good_ticket_or_for_another_repository(
    running: Running,
) -> None:
    assert start(running, ticket="nonsense").headers[HEADER_REASON] == "ticket-invalid"
    refused = start(running, base_url="https://zenodo.org/api")
    assert refused.headers[HEADER_REASON] == "base-url-not-allowed"


def test_a_pasted_token_is_checked_then_sealed_and_never_returned(running: Running) -> None:
    ticket = running.harness.ticket()
    answer = running.client.put(
        "/connect/account",
        json={"base_url": SANDBOX, "token": TOKEN},
        headers={"Authorization": f"Bearer {ticket}"},
    )
    assert answer.status_code == 200
    assert answer.json()["label"] == f"Personal token ending {TOKEN[-4:]}"
    assert TOKEN not in answer.text
    shown = running.client.get(
        "/connect/account",
        params={"base_url": SANDBOX},
        headers={"Authorization": f"Bearer {running.harness.ticket()}"},
    )
    assert shown.json()["connected"] is True
    assert TOKEN not in shown.text
    with closing(sqlite3.connect(running.broker.settings.store)) as db:
        dumped = "\n".join(str(row) for row in db.execute("SELECT * FROM accounts"))
    assert TOKEN not in dumped


def test_a_token_the_repository_refuses_is_not_kept(running: Running) -> None:
    answer = running.client.put(
        "/connect/account",
        json={"base_url": SANDBOX, "token": "not-a-real-token"},
        headers={"Authorization": f"Bearer {running.harness.ticket()}"},
    )
    assert (answer.status_code, answer.headers[HEADER_REASON]) == (401, "account-rejected")
    assert running.broker.store.account(PSEUDONYM, SANDBOX) is None


def test_disconnecting_erases_the_account(running: Running) -> None:
    running.broker.store.put(PSEUDONYM, SANDBOX, Tokens(TOKEN), method="token", label="token")
    answer = running.client.delete(
        "/connect/account",
        params={"base_url": SANDBOX},
        headers={"Authorization": f"Bearer {running.harness.ticket()}"},
    )
    assert answer.status_code == 204
    assert running.broker.store.account(PSEUDONYM, SANDBOX) is None


def test_a_ticket_is_accepted_once_and_names_only_its_person(running: Running) -> None:
    running.broker.store.put(OTHER, SANDBOX, Tokens(TOKEN), method="token", label="token")
    ticket = running.harness.ticket()
    first = running.client.get(
        "/connect/account",
        params={"base_url": SANDBOX},
        headers={"Authorization": f"Bearer {ticket}"},
    )
    assert first.json()["connected"] is False
    again = running.client.get(
        "/connect/account",
        params={"base_url": SANDBOX},
        headers={"Authorization": f"Bearer {ticket}"},
    )
    assert again.headers[HEADER_REASON] == "ticket-used"


def test_a_grant_is_not_a_ticket(running: Running) -> None:
    answer = running.client.get(
        "/connect/account",
        params={"base_url": SANDBOX},
        headers={"Authorization": f"Bearer {running.harness.grant()}"},
    )
    assert answer.headers[HEADER_REASON] == "ticket-invalid"


def test_a_sealed_token_opens_only_for_its_own_record(tmp_path: Path) -> None:
    store = Store(tmp_path / "s.sqlite", bytes(32))
    store.put(PSEUDONYM, SANDBOX, Tokens(TOKEN), method="token", label="token")
    with closing(sqlite3.connect(tmp_path / "s.sqlite")) as db, db:
        db.execute("UPDATE accounts SET pseudonym = ?", (OTHER,))
    with pytest.raises(SealError):
        store.account(OTHER, SANDBOX)
