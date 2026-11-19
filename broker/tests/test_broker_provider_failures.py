"""A provider's failure is logged with its own HTTP status, so an operator can tell a refused key
from a wrong address or an outage, and never with the provider's text
(docs/specs/model-accounts.md)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx
import pytest
from broker_support import (
    DEPLOYMENT_KEY,
    GATEWAY,
    FakeHarness,
    call_headers,
    client,
    make_broker,
    message_body,
)

from dd_broker import anthropic as broker_anthropic
from dd_broker.app import Broker
from dd_sdk.model_grant import HEADER_REASON, Account

MESSAGES = "/anthropic/v1/messages"
# Text a provider might send back; the broker must not repeat it anywhere.
PROVIDER_TEXT = "upstream detail that might echo " + DEPLOYMENT_KEY


@pytest.fixture
def broker(tmp_path: Path) -> tuple[FakeHarness, Broker]:
    harness = FakeHarness()
    return harness, make_broker(harness, tmp_path / "broker.sqlite3", deployment_base_url=GATEWAY)


def answering(monkeypatch: pytest.MonkeyPatch, answer: httpx.Response | Exception) -> None:
    async def send(*_: Any) -> httpx.Response:
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(broker_anthropic, "send", send)


def call(harness: FakeHarness, broker: Broker) -> Any:
    grant = harness.grant(account=Account.DEPLOYMENT)
    with client(broker) as http:
        return http.post(MESSAGES, json=message_body(), headers=call_headers(grant))


def broker_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == "dd_broker" and r.levelno >= logging.WARNING]


@pytest.mark.parametrize("status", [401, 404, 500, 503])
def test_a_provider_failure_is_logged_with_the_providers_status(
    broker: tuple[FakeHarness, Broker],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    status: int,
) -> None:
    caplog.set_level(logging.INFO, logger="dd_broker")
    answering(monkeypatch, httpx.Response(status, json={"error": {"message": PROVIDER_TEXT}}))

    response = call(*broker)

    assert response.headers[HEADER_REASON] == "provider-error"
    [record] = broker_records(caplog)
    assert status in record.args  # type: ignore[operator]
    assert PROVIDER_TEXT not in caplog.text
    assert DEPLOYMENT_KEY not in caplog.text


def test_a_provider_answer_that_is_not_json_is_logged(
    broker: tuple[FakeHarness, Broker],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="dd_broker")
    answering(
        monkeypatch,
        httpx.Response(200, text=PROVIDER_TEXT, headers={"content-type": "text/html"}),
    )

    response = call(*broker)

    assert response.headers[HEADER_REASON] == "provider-error"
    [record] = broker_records(caplog)
    assert "text/html" in record.args  # type: ignore[operator]
    assert PROVIDER_TEXT not in caplog.text


def test_an_unreachable_provider_is_logged_without_the_address(
    broker: tuple[FakeHarness, Broker],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="dd_broker")
    answering(monkeypatch, httpx.ConnectError(f"cannot connect to {GATEWAY}"))

    response = call(*broker)

    assert response.headers[HEADER_REASON] == "provider-unreachable"
    [record] = broker_records(caplog)
    assert "ConnectError" in record.args  # type: ignore[operator]
    assert GATEWAY not in caplog.text
