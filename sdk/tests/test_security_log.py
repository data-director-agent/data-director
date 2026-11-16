"""The security event log: one JSON record per event, with only the fields `emit` builds
(docs/specs/security.md, Security events)."""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator

import pytest

from dd_sdk import security_log
from dd_sdk.security_log import CONTEXT_KEYS, SecurityEvent, emit
from dd_sdk.testing import security_events

FIXED = {"time", "event", "outcome", "service", "principal", "reason"}


@pytest.fixture
def configured() -> Iterator[io.StringIO]:
    stream = io.StringIO()
    logger = logging.getLogger(security_log.LOGGER)
    before = (list(logger.handlers), logger.level, logger.propagate)
    security_log.configure(stream)
    yield stream
    logger.handlers[:], logger.level, logger.propagate = before


def test_an_event_is_one_line_of_json_with_the_fixed_fields(configured: io.StringIO) -> None:
    emit(
        SecurityEvent.GRANT_MINTED,
        outcome="success",
        service="harness",
        principal="https://orcid.org/0000-0002-1825-0097",
        agent_id="example",
        models=["model-a"],
    )
    emit(SecurityEvent.CALLER_REFUSED, outcome="failure", service="harness", reason="no-session")

    lines = configured.getvalue().splitlines()
    assert len(lines) == 2
    first, second = (json.loads(line) for line in lines)
    assert first.keys() >= FIXED
    assert first["event"] == SecurityEvent.GRANT_MINTED.value
    assert first["models"] == ["model-a"]
    assert first["time"].endswith("Z")
    assert second["outcome"] == "failure"
    assert second["principal"] is None


def test_configuring_twice_writes_each_event_once(configured: io.StringIO) -> None:
    security_log.configure(configured)
    emit(SecurityEvent.SIGN_OUT, outcome="success", service="app")
    assert len(configured.getvalue().splitlines()) == 1


class Collect(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def test_a_configured_log_does_not_reach_the_root_loggers_handlers(
    configured: io.StringIO,
) -> None:
    root = logging.getLogger()
    collect = Collect()
    root.addHandler(collect)
    try:
        emit(SecurityEvent.SIGN_OUT, outcome="success", service="app")
    finally:
        root.removeHandler(collect)
    assert security_events(collect.records) == []
    assert configured.getvalue()


def test_a_field_outside_the_allowed_context_is_refused() -> None:
    with pytest.raises(ValueError, match="token"):
        emit(SecurityEvent.GRANT_MINTED, outcome="success", service="harness", token="secret")


def test_every_record_has_only_fixed_and_allowed_fields(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=security_log.LOGGER)
    emit(
        SecurityEvent.BROKER_ENROLLED,
        outcome="success",
        service="model-broker",
        principal="pseudonym",
        provider="anthropic",
    )
    [event] = security_events(caplog.records)
    assert event.keys() <= FIXED | CONTEXT_KEYS


def test_enum_values_are_recorded_as_plain_strings(caplog: pytest.LogCaptureFixture) -> None:
    # pytest-xdist serialises captured log records with execnet, which refuses a `StrEnum`.
    caplog.set_level(logging.INFO, logger=security_log.LOGGER)
    emit(
        SecurityEvent.CALLER_REFUSED,
        outcome="failure",
        service="harness",
        reason=SecurityEvent.SIGN_OUT,
        transport=SecurityEvent.SIGN_OUT,
        models=[SecurityEvent.SIGN_OUT],
    )
    [event] = security_events(caplog.records)
    assert type(event["reason"]) is str
    assert type(event["transport"]) is str
    assert [type(m) for m in event["models"]] == [str]
