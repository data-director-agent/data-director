"""The broker records enrolment, removal and refused callers as security events, naming a person
only by their pseudonym (docs/specs/security.md, Security events)."""

from __future__ import annotations

import logging
from pathlib import Path

import httpx
import pytest
from broker_support import PSEUDONYM, FakeHarness, call_headers, client, make_broker, message_body

from dd_broker.enrolment import ACCOUNT_PATH
from dd_broker.reasons import Reason
from dd_sdk.security_log import LOGGER, SecurityEvent
from dd_sdk.testing import security_events

KEY = "sk-ant-api03-security-event-key-41d7"


@pytest.fixture(autouse=True)
def capture(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER)


def accepting() -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(200, json={"data": []}))


def test_an_enrolment_is_recorded_under_the_pseudonym(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    harness = FakeHarness()
    broker = make_broker(harness, tmp_path / "broker.sqlite3", transport=accepting())
    with client(broker) as http:
        answer = http.put(
            ACCOUNT_PATH,
            json={"provider": "anthropic", "key": KEY},
            headers={"Authorization": f"Bearer {harness.ticket()}"},
        )
    assert answer.status_code == 200
    [event] = security_events(caplog.records)
    assert event["event"] == SecurityEvent.BROKER_ENROLLED
    assert event["outcome"] == "success"
    assert event["principal"] == PSEUDONYM
    assert event["provider"] == "anthropic"
    assert KEY not in str(event)


def test_removing_an_account_is_recorded_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    harness = FakeHarness()
    broker = make_broker(harness, tmp_path / "broker.sqlite3")
    broker.store.put(PSEUDONYM, "anthropic", KEY, label="Anthropic ····41d7")
    with client(broker) as http:
        for _ in range(2):
            http.delete(ACCOUNT_PATH, headers={"Authorization": f"Bearer {harness.ticket()}"})
    [event] = security_events(caplog.records)
    assert event["event"] == SecurityEvent.BROKER_ACCOUNT_REMOVED
    assert event["principal"] == PSEUDONYM


def test_an_enrolment_without_a_ticket_is_recorded_as_refused(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with client(make_broker(FakeHarness(), tmp_path / "broker.sqlite3")) as http:
        http.get(ACCOUNT_PATH)
    [event] = security_events(caplog.records)
    assert event["event"] == SecurityEvent.BROKER_ENROLMENT_REFUSED
    assert event["reason"] == Reason.TICKET_MISSING
    assert event["principal"] is None


def test_a_call_without_a_grant_is_recorded_as_refused(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with client(make_broker(FakeHarness(), tmp_path / "broker.sqlite3")) as http:
        answer = http.post(
            "/anthropic/v1/messages", json=message_body(), headers=call_headers(None)
        )
    assert answer.status_code >= 400
    [event] = security_events(caplog.records)
    assert event["event"] == SecurityEvent.BROKER_CALL_REFUSED
    assert event["reason"] == Reason.GRANT_MISSING
