"""The enrolment interface (docs/specs/model-accounts.md, Enrolment): a person reads, adds, replaces
or removes their own account with a single-use ticket the harness signed, and only a key the
provider accepts is stored."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from broker_support import (
    MODEL,
    PSEUDONYM,
    FakeHarness,
    call_headers,
    client,
    make_broker,
    message_body,
)
from joserfc.jwk import RSAKey

from dd_broker.app import Broker
from dd_broker.enrolment import ACCOUNT_PATH
from dd_broker.reasons import Reason
from dd_sdk.model_grant import HEADER_REASON, Payer

KEY = "sk-ant-api03-enrolment-test-key-9c4e"
REPLACEMENT = "sk-ant-api03-enrolment-test-key-b7d1"


def provider(status: int, seen: list[httpx.Request] | None = None) -> httpx.MockTransport:
    def answer(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, json={"data": [{"id": MODEL}]})

    return httpx.MockTransport(answer)


def unreachable() -> httpx.MockTransport:
    def answer(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    return httpx.MockTransport(answer)


def bearer(ticket: str) -> dict[str, str]:
    return {"authorization": f"Bearer {ticket}"}


@pytest.fixture
def harness() -> FakeHarness:
    return FakeHarness()


@pytest.fixture
def broker_for(harness: FakeHarness, tmp_path: Path) -> Callable[..., Broker]:
    def build(transport: httpx.AsyncBaseTransport | None = None) -> Broker:
        return make_broker(harness, tmp_path / "broker.sqlite3", transport=transport)

    return build


def test_a_person_with_no_account_reads_none(
    harness: FakeHarness, broker_for: Callable[..., Broker]
) -> None:
    with client(broker_for()) as http:
        answer = http.get(ACCOUNT_PATH, headers=bearer(harness.ticket()))
    assert answer.status_code == 200
    assert answer.json() == {"account": None, "usage": []}
    assert answer.headers["cache-control"] == "no-store"


def test_a_key_the_provider_accepts_is_stored_and_shown_only_by_its_label(
    harness: FakeHarness, broker_for: Callable[..., Broker]
) -> None:
    seen: list[httpx.Request] = []
    broker = broker_for(provider(200, seen))
    with client(broker) as http:
        answer = http.put(
            ACCOUNT_PATH,
            json={"provider": "anthropic", "key": KEY},
            headers=bearer(harness.ticket()),
        )
        read = http.get(ACCOUNT_PATH, headers=bearer(harness.ticket()))

    assert answer.status_code == 200
    account = answer.json()["account"]
    assert account["provider"] == "anthropic"
    assert account["label"].endswith(KEY[-4:])
    assert KEY[:-4] not in answer.text
    assert read.json()["account"] == account
    # One inexpensive call, with the person's key, to list models.
    [check] = seen
    assert check.method == "GET"
    assert check.url.path == "/v1/models"
    assert check.headers["x-api-key"] == KEY
    stored = broker.store.account(PSEUDONYM)
    assert stored is not None and stored.key == KEY


@pytest.mark.parametrize(
    ("status", "answered", "reason"),
    [
        (401, 422, Reason.MODEL_ACCOUNT_REJECTED),
        (403, 422, Reason.MODEL_ACCOUNT_REJECTED),
        (429, 429, Reason.MODEL_ACCOUNT_LIMIT),
        (500, 502, Reason.PROVIDER_ERROR),
    ],
)
def test_a_key_that_fails_the_check_is_not_stored(
    harness: FakeHarness,
    broker_for: Callable[..., Broker],
    status: int,
    answered: int,
    reason: Reason,
) -> None:
    broker = broker_for(provider(status))
    with client(broker) as http:
        answer = http.put(
            ACCOUNT_PATH,
            json={"provider": "anthropic", "key": KEY},
            headers=bearer(harness.ticket()),
        )
    assert answer.status_code == answered
    assert answer.json() == {"reason": reason.value}
    assert answer.headers[HEADER_REASON] == reason.value
    assert broker.store.label(PSEUDONYM) is None


def test_an_unreachable_provider_stores_nothing(
    harness: FakeHarness, broker_for: Callable[..., Broker]
) -> None:
    broker = broker_for(unreachable())
    with client(broker) as http:
        answer = http.put(
            ACCOUNT_PATH,
            json={"provider": "anthropic", "key": KEY},
            headers=bearer(harness.ticket()),
        )
    assert answer.json() == {"reason": Reason.PROVIDER_UNREACHABLE.value}
    assert broker.store.label(PSEUDONYM) is None


def test_a_key_that_fails_does_not_replace_the_one_that_works(
    harness: FakeHarness, broker_for: Callable[..., Broker]
) -> None:
    broker = broker_for(provider(401))
    broker.store.put(PSEUDONYM, "anthropic", KEY, label="Anthropic ····9c4e")
    with client(broker) as http:
        http.put(
            ACCOUNT_PATH,
            json={"provider": "anthropic", "key": REPLACEMENT},
            headers=bearer(harness.ticket()),
        )
    stored = broker.store.account(PSEUDONYM)
    assert stored is not None and stored.key == KEY


def test_a_working_key_replaces_the_last(
    harness: FakeHarness, broker_for: Callable[..., Broker]
) -> None:
    broker = broker_for(provider(200))
    broker.store.put(PSEUDONYM, "anthropic", KEY, label="Anthropic ····9c4e")
    with client(broker) as http:
        answer = http.put(
            ACCOUNT_PATH,
            json={"provider": "anthropic", "key": REPLACEMENT},
            headers=bearer(harness.ticket()),
        )
    assert answer.json()["account"]["label"].endswith(REPLACEMENT[-4:])
    stored = broker.store.account(PSEUDONYM)
    assert stored is not None and stored.key == REPLACEMENT


@pytest.mark.parametrize(
    "body",
    [
        {"provider": "openai", "key": KEY},
        {"provider": "anthropic"},
        {"provider": "anthropic", "key": "short"},
        {"provider": "anthropic", "key": "sk-ant with a space"},
        {"provider": "anthropic", "key": 42},
        ["anthropic", KEY],
    ],
)
def test_a_malformed_enrolment_is_refused_without_calling_the_provider(
    harness: FakeHarness, broker_for: Callable[..., Broker], body: Any
) -> None:
    seen: list[httpx.Request] = []
    broker = broker_for(provider(200, seen))
    with client(broker) as http:
        answer = http.put(ACCOUNT_PATH, json=body, headers=bearer(harness.ticket()))
    assert answer.status_code == 400
    assert answer.json()["reason"] in {
        Reason.REQUEST_INVALID.value,
        Reason.ACCOUNT_UNSUPPORTED.value,
    }
    assert seen == []
    assert broker.store.label(PSEUDONYM) is None


def test_a_large_body_is_refused(harness: FakeHarness, broker_for: Callable[..., Broker]) -> None:
    with client(broker_for(provider(200))) as http:
        answer = http.put(
            ACCOUNT_PATH,
            json={"provider": "anthropic", "key": "k" * 10_000},
            headers=bearer(harness.ticket()),
        )
    assert answer.status_code == 413


def test_removing_the_account_erases_it_at_once(
    harness: FakeHarness, broker_for: Callable[..., Broker]
) -> None:
    broker = broker_for()
    broker.store.put(PSEUDONYM, "anthropic", KEY, label="Anthropic ····9c4e")
    with client(broker) as http:
        answer = http.delete(ACCOUNT_PATH, headers=bearer(harness.ticket()))
        again = http.delete(ACCOUNT_PATH, headers=bearer(harness.ticket()))
    assert answer.status_code == 204
    assert again.status_code == 204
    assert broker.store.label(PSEUDONYM) is None
    assert broker.store.account(PSEUDONYM) is None


def test_the_page_reads_the_persons_token_use(
    harness: FakeHarness, broker_for: Callable[..., Broker]
) -> None:
    broker = broker_for()
    broker.store.add_usage(
        PSEUDONYM,
        payer=Payer.OWN,
        provider="anthropic",
        model=MODEL,
        input_tokens=120,
        output_tokens=30,
    )
    broker.store.add_usage(
        "someone-else",
        payer=Payer.OWN,
        provider="anthropic",
        model=MODEL,
        input_tokens=999,
        output_tokens=999,
    )
    with client(broker) as http:
        answer = http.get(ACCOUNT_PATH, headers=bearer(harness.ticket()))
    [row] = answer.json()["usage"]
    assert (row["payer"], row["model"]) == ("own", MODEL)
    assert (row["input_tokens"], row["output_tokens"]) == (120, 30)


def test_a_ticket_names_only_its_own_person(
    harness: FakeHarness, broker_for: Callable[..., Broker]
) -> None:
    broker = broker_for()
    broker.store.put(PSEUDONYM, "anthropic", KEY, label="Anthropic ····9c4e")
    with client(broker) as http:
        answer = http.get(ACCOUNT_PATH, headers=bearer(harness.ticket(pseudonym="pseud-other")))
    assert answer.json()["account"] is None


# --- The ticket ---


def test_a_ticket_is_accepted_once(harness: FakeHarness, broker_for: Callable[..., Broker]) -> None:
    ticket = harness.ticket()
    with client(broker_for()) as http:
        first = http.get(ACCOUNT_PATH, headers=bearer(ticket))
        second = http.get(ACCOUNT_PATH, headers=bearer(ticket))
    assert first.status_code == 200
    assert second.status_code == 401
    assert second.json() == {"reason": Reason.TICKET_USED.value}


def test_a_request_without_a_ticket_is_refused(broker_for: Callable[..., Broker]) -> None:
    with client(broker_for()) as http:
        answer = http.get(ACCOUNT_PATH)
    assert answer.status_code == 401
    assert answer.json() == {"reason": Reason.TICKET_MISSING.value}


def test_an_expired_ticket_is_refused(
    harness: FakeHarness, broker_for: Callable[..., Broker]
) -> None:
    ticket = harness.ticket(issued_at=int(time.time()) - 600)
    with client(broker_for()) as http:
        answer = http.get(ACCOUNT_PATH, headers=bearer(ticket))
    assert answer.json() == {"reason": Reason.TICKET_EXPIRED.value}


def test_a_model_grant_is_not_a_ticket(
    harness: FakeHarness, broker_for: Callable[..., Broker]
) -> None:
    with client(broker_for()) as http:
        answer = http.get(ACCOUNT_PATH, headers=bearer(harness.grant()))
    assert answer.json() == {"reason": Reason.TICKET_INVALID.value}


@pytest.mark.parametrize(
    "forge",
    [
        # The ticket's claims under a grant's `typ`.
        lambda harness: harness.ticket(typ="JWT"),
        # Signed by a key that is not the harness's.
        lambda harness: FakeHarness(
            signing_key=RSAKey.generate_key(2048, parameters={"kid": "harness-1"}),
            subject_key=harness.subject_key,
        ).ticket(),
        # Its pseudonym sealed to a key that is not the broker's.
        lambda harness: FakeHarness(signing_key=harness.signing_key).ticket(),
        lambda harness: "not-a-ticket",
    ],
)
def test_a_forged_ticket_is_refused(
    harness: FakeHarness,
    broker_for: Callable[..., Broker],
    forge: Callable[[FakeHarness], str],
) -> None:
    with client(broker_for()) as http:
        answer = http.get(ACCOUNT_PATH, headers=bearer(forge(harness)))
    assert answer.status_code == 401
    assert answer.json() == {"reason": Reason.TICKET_INVALID.value}


def test_a_ticket_is_not_a_grant(harness: FakeHarness, broker_for: Callable[..., Broker]) -> None:
    with client(broker_for()) as http:
        answer = http.post(
            "/anthropic/v1/messages", json=message_body(), headers=call_headers(harness.ticket())
        )
    assert answer.status_code == 401
    assert answer.headers[HEADER_REASON] == Reason.GRANT_INVALID.value


def test_a_used_ticket_is_forgotten_once_it_has_expired(
    harness: FakeHarness, broker_for: Callable[..., Broker]
) -> None:
    store = broker_for().store
    assert store.use_ticket("t-1", expires=100, now=50)
    assert not store.use_ticket("t-1", expires=100, now=60)
    # Long after it expired, its row is gone; the signature check refuses it by then anyway.
    assert store.use_ticket("t-2", expires=300, now=200)
    assert store.use_ticket("t-1", expires=400, now=200)
