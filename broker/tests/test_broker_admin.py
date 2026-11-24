"""The operators' summary (`dd_broker.admin`): served only with the operators' credential set,
refused without it, and aggregate, naming no pseudonym and carrying no label or key."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from broker_support import (
    AGENT,
    AGENT_CREDENTIAL,
    OTHER_AGENT,
    PSEUDONYM,
    FakeHarness,
    client,
    make_broker,
)

from dd_broker.admin import SUMMARY_PATH
from dd_broker.agents import OperatorCredential, digest
from dd_broker.app import Broker
from dd_broker.reasons import Reason
from dd_sdk.model_grant import HEADER_REASON, Payer
from dd_sdk.security_log import LOGGER, SecurityEvent
from dd_sdk.testing import security_events

OPERATOR = "dd-broker-test-operator-credential-0c2e"
OWN_KEY = "sk-ant-api03-own-key-not-to-be-shown-9b1f"
OTHER_PSEUDONYM = "pseud-0000000000000002"


def broker_with_records(tmp_path: Path, *, operator: bool = True) -> Broker:
    broker = make_broker(
        FakeHarness(),
        tmp_path / "broker.sqlite3",
        deployment_base_url="http://gateway.test:4000",
        allowed=("https://models.example.ac.uk",),
    )
    if operator:
        broker.operator = OperatorCredential.from_digest(digest(OPERATOR))
    store = broker.store
    store.put(PSEUDONYM, "anthropic", OWN_KEY, label="Anthropic …9b1f")
    today = datetime.now(UTC).date()
    for pseudonym in (PSEUDONYM, OTHER_PSEUDONYM):
        store.add_usage(
            pseudonym,
            payer=Payer.DEPLOYMENT,
            provider="anthropic",
            model="claude-sonnet-5-5",
            input_tokens=100,
            output_tokens=10,
            day=today,
        )
    store.add_usage(
        PSEUDONYM,
        payer=Payer.OWN,
        provider="anthropic",
        model="claude-sonnet-5-5",
        input_tokens=7,
        output_tokens=3,
        day=today - timedelta(days=60),
    )
    return broker


def test_the_summary_is_aggregate_and_names_no_one(tmp_path: Path) -> None:
    with client(broker_with_records(tmp_path)) as http:
        answer = http.get(SUMMARY_PATH, headers={"Authorization": f"Bearer {OPERATOR}"})
    assert answer.status_code == 200
    found = answer.json()
    assert found["accounts_by_provider"] == {"anthropic": 1}
    assert found["people_with_usage"] == 2
    # Two people's calls on one day, summed into one row; the call 60 days ago is left out.
    [row] = found["usage"]
    assert row["payer"] == "deployment"
    assert (row["input_tokens"], row["output_tokens"]) == (200, 20)
    assert found["agents"] == sorted([AGENT, OTHER_AGENT])
    assert found["providers_paid"] == ["anthropic"]
    assert found["deployment_base_url"] is True
    assert found["allowed_base_urls"] == ["https://models.example.ac.uk"]
    text = json.dumps(found)
    for secret in (PSEUDONYM, OTHER_PSEUDONYM, OWN_KEY, "…9b1f", digest(OPERATOR), "gateway.test"):
        assert secret not in text


@pytest.mark.parametrize("presented", [None, "Bearer wrong-credential", f"Basic {OPERATOR}"])
def test_without_the_operators_credential_the_summary_is_refused(
    tmp_path: Path, presented: str | None, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER)
    headers = {"Authorization": presented} if presented else {}
    with client(broker_with_records(tmp_path)) as http:
        answer = http.get(SUMMARY_PATH, headers=headers)
    assert answer.status_code == 401
    assert answer.headers[HEADER_REASON] == Reason.OPERATOR_UNAUTHENTICATED
    [event] = security_events(caplog.records)
    assert event["event"] == SecurityEvent.BROKER_CALL_REFUSED
    assert event["reason"] == Reason.OPERATOR_UNAUTHENTICATED


def test_without_an_operators_credential_set_the_summary_is_not_served(tmp_path: Path) -> None:
    with client(broker_with_records(tmp_path, operator=False)) as http:
        answer = http.get(SUMMARY_PATH, headers={"Authorization": f"Bearer {OPERATOR}"})
    assert answer.status_code == 404


def test_an_agents_credential_does_not_open_the_summary(tmp_path: Path) -> None:
    with client(broker_with_records(tmp_path)) as http:
        answer = http.get(SUMMARY_PATH, headers={"Authorization": f"Bearer {AGENT_CREDENTIAL}"})
    assert answer.status_code == 401
