"""A person's key appears in no answer, log line, error or record the broker writes, even when the
provider quotes it back (docs/specs/model-accounts.md, invariant 1; issue #806)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx
import pytest
from broker_support import (
    AGENT_CREDENTIAL,
    PSEUDONYM,
    FakeHarness,
    broker_calls_only,
    call_headers,
    client,
    make_broker,
    message_body,
)

from dd_broker.enrolment import ACCOUNT_PATH

# Distinctive enough that finding it anywhere means it leaked. The cassette's error answers quote
# it, as a careless provider might.
SENTINEL = "sk-ant-sentinel-7d2e9b40c1a85f36"


@pytest.fixture(scope="module")
def vcr_config(vcr_config: dict[str, Any]) -> dict[str, Any]:
    return {**vcr_config, "before_record_request": broker_calls_only}


@pytest.mark.vcr
def test_a_persons_key_appears_in_no_answer_log_or_record(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    caplog.set_level(logging.DEBUG)
    harness = FakeHarness()
    broker = make_broker(harness, tmp_path / "store" / "broker.sqlite3")
    broker.store.put(PSEUDONYM, "anthropic", SENTINEL, label="anthropic …5f36")

    answers = []
    with client(broker) as http:
        # Served, rejected (the provider quotes the key), then limited (it quotes it again).
        for _ in range(3):
            answers.append(
                http.post(
                    "/anthropic/v1/messages",
                    json=message_body(),
                    headers=call_headers(harness.grant()),
                )
            )

    assert [a.status_code for a in answers] == [200, 403, 429]
    for answer in answers:
        assert SENTINEL not in answer.text
        assert SENTINEL not in str(answer.headers)
        # Nor the pseudonym or the agent's credential: the broker's answer names neither.
        assert PSEUDONYM not in answer.text and PSEUDONYM not in str(answer.headers)
        assert AGENT_CREDENTIAL not in answer.text
    captured = capsys.readouterr()
    for text in (caplog.text, captured.out, captured.err):
        assert SENTINEL not in text
        assert AGENT_CREDENTIAL not in text
    for path in (tmp_path / "store").iterdir():
        assert SENTINEL.encode() not in path.read_bytes()


def test_a_key_enrolled_through_the_browser_appears_in_no_answer_log_or_record(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    caplog.set_level(logging.DEBUG)
    statuses = iter([401, 429, 200])

    def provider(request: httpx.Request) -> httpx.Response:
        # A careless provider quotes the key back, in failure and in success.
        return httpx.Response(next(statuses), text=f"key {SENTINEL} is not valid")

    harness = FakeHarness()
    broker = make_broker(
        harness, tmp_path / "store" / "broker.sqlite3", transport=httpx.MockTransport(provider)
    )
    answers = []
    with client(broker) as http:
        for _ in range(3):
            answers.append(
                http.put(
                    ACCOUNT_PATH,
                    json={"provider": "anthropic", "key": SENTINEL},
                    headers={"authorization": f"Bearer {harness.ticket()}"},
                )
            )
        answers.append(
            http.get(ACCOUNT_PATH, headers={"authorization": f"Bearer {harness.ticket()}"})
        )

    assert [a.status_code for a in answers] == [422, 429, 200, 200]
    for answer in answers:
        assert SENTINEL not in answer.text
        assert SENTINEL not in str(answer.headers)
        assert PSEUDONYM not in answer.text
    captured = capsys.readouterr()
    for text in (caplog.text, captured.out, captured.err):
        assert SENTINEL not in text
    for path in (tmp_path / "store").iterdir():
        assert SENTINEL.encode() not in path.read_bytes()
