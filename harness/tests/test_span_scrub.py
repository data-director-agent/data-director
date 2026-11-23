"""Secrets kept out of the spans the harness imports from a remote agent (docs/specs/security.md,
invariant 2; docs/specs/transport.md, invariant 11).

A hostile agent writes a recognisable secret into its spans in each way the scrub knows: under a
secret-shaped name, as a bearer credential or token-shaped value, and as the very grant the
harness sent it. None of them reaches the run store, and each is a security event.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from dd_harness.span_scrub import Reason, scrub, secret_named
from dd_harness.testing import (
    TEST_PRINCIPAL,
    ScriptedAgent,
    grant_token,
    make_conductor,
    message,
    request,
    review_of_input,
)
from dd_sdk import security_log
from dd_sdk.agent import AgentResult, RunContext
from dd_sdk.contract.models import GroundingMode, InvocationRequest
from dd_sdk.security_log import SecurityEvent
from dd_sdk.testing import security_events

SENTINEL = "sentinel-7d1f4c2a9b"
JWT = "eyJhbGciOiJFUzI1NiJ9.eyJzdWIiOiJ4In0.c2lnbmF0dXJl"


@pytest.mark.parametrize(
    "name",
    ["dd.delegation_token", "http.request.header.authorization", "x-api-key", "db.password"],
)
def test_a_secret_shaped_name_is_secret(name: str) -> None:
    assert secret_named(name)


@pytest.mark.parametrize(
    "name", ["dd.input_tokens", "gen_ai.usage.output_tokens", "dd.source_id", "dd.content_hash"]
)
def test_an_owned_or_usage_attribute_is_not(name: str) -> None:
    assert not secret_named(name)


def test_attributes_of_spans_events_links_and_resource_are_scrubbed() -> None:
    span = {
        "name": "chat",
        "attributes": {"dd.model_id": "m", "api.token": SENTINEL},
        "events": [{"name": "e", "attributes": {"note": f"Bearer {SENTINEL}"}}],
        "links": [{"context": {}, "attributes": {"grant": JWT}}],
        "resource": {"attributes": {"service.name": "a", "issued": f"x{SENTINEL}x"}},
    }
    result = scrub([span], issued=[SENTINEL])
    assert SENTINEL not in str(result.spans) and JWT not in str(result.spans)
    (clean,) = result.spans
    assert clean["attributes"] == {"dd.model_id": "m"}
    assert clean["resource"]["attributes"] == {"service.name": "a"}
    assert set(result.reasons) == {Reason.NAME, Reason.SHAPE, Reason.ISSUED}


def test_a_span_with_no_secret_is_unchanged() -> None:
    span = {"name": "retrieval", "attributes": {"dd.source_id": "s", "dd.content_hash": "0" * 64}}
    result = scrub([span], issued=[SENTINEL])
    assert result.spans == (span,) and result.reasons == []


def _leaking(attributes: dict[str, str]) -> ScriptedAgent:
    def behaviour(req: InvocationRequest, ctx: RunContext) -> AgentResult:
        with ctx.tracer.start_as_current_span("chat") as span:
            for name, value in attributes.items():
                span.set_attribute(name, value)
        return review_of_input(req, ctx)

    return ScriptedAgent(GroundingMode.INPUT_ONLY, behaviour)


@pytest.mark.parametrize(
    ("attributes", "reason"),
    [
        ({"agent.secret": SENTINEL}, Reason.NAME),
        ({"note": f"Authorization: Bearer {SENTINEL}"}, Reason.SHAPE),
        ({"note": JWT}, Reason.SHAPE),
    ],
)
def test_a_leaked_secret_never_reaches_the_run_store(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    attributes: dict[str, str],
    reason: str,
) -> None:
    caplog.set_level(logging.INFO, logger=security_log.LOGGER)
    runs = tmp_path / "runs"
    agent = _leaking(attributes)
    req = request(agent.spec.agent_id)
    make_conductor(runs, agent, crate=True).invoke(req, acting_for=TEST_PRINCIPAL)
    for path in runs.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            assert SENTINEL not in text and JWT not in text, path
    dropped = SecurityEvent.SPAN_SECRET_DROPPED
    events = [e for e in security_events(caplog.records) if e["event"] == dropped]
    assert [(e["reason"], e["invocation_id"]) for e in events] == [(reason, req.invocation_id)]


def test_the_grant_the_harness_sent_never_reaches_the_run_store(tmp_path: Path) -> None:
    sent: dict[str, str] = {}

    def behaviour(req: InvocationRequest, ctx: RunContext) -> AgentResult:
        sent["token"] = grant_token(ctx)
        with ctx.tracer.start_as_current_span("chat") as span:
            span.set_attribute("note", f"called back with {sent['token']}")
        return review_of_input(req, ctx)

    runs = tmp_path / "runs"
    agent = ScriptedAgent(GroundingMode.DELEGATION, behaviour)
    make_conductor(runs, agent, crate=True).invoke(
        request(agent.spec.agent_id, message()), acting_for=TEST_PRINCIPAL
    )
    assert sent["token"]
    for path in runs.rglob("*"):
        if path.is_file():
            assert sent["token"] not in path.read_text(encoding="utf-8", errors="replace"), path


def test_a_secret_in_a_list_valued_attribute_is_dropped() -> None:
    span = {"name": "chat", "attributes": {"notes": ["fine", f"Bearer {SENTINEL}"], "n": [1, 2]}}
    result = scrub([span])
    assert result.spans[0]["attributes"] == {"n": [1, 2]}
    assert result.reasons == [Reason.SHAPE]
