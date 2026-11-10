"""The AG-UI cassettes the shell replays (`app/web/cassettes`, docs/specs/transport.md): each is
what the harness's AG-UI binding streams for one kind of run, made here with the agents in
process. Outside CI a stale cassette is rewritten (`support.check_cassette`); in CI it fails.

The succeeded, abstained and refused runs go through the app's own conductor and agents; the
referred, withheld and cancelled ones need an outcome no in-tree agent gives on demand, so they use
the harness's scripted doubles.
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from support import (
    CASSETTES,
    check_cassette,
    configure_env,
    new_governance,
)

from dd_app.governance import Governance
from dd_harness import testing as fakes
from dd_harness.conductor import Conductor
from dd_harness.observe import RunObserver
from dd_harness.testing import (
    RESTRICTIVE,
    TEST_PRINCIPAL,
    AbstainingStub,
    Chat,
    ScriptedAgent,
    make_conductor,
    request,
)
from dd_harness.transport.agui import Cancellation, stream_run
from dd_sdk.agent import AgentResult, RunContext
from dd_sdk.contract.models import Envelope, GroundingMode, InvocationRequest

EXAMPLES = Path(__file__).resolve().parents[1] / "config/examples"
STANDARDS_AGENT_ID = "advisor.standards"
FIXED_RUN_ID = "01900000-0000-7000-8000-000000000001"
FIXED_TIME = "2026-01-01T00:00:00Z"
THREAD = "thread"
RUN = "run"
# Keys that hold a credential, and how a credential's value starts; neither may be in a cassette.
CREDENTIAL_KEYS = {
    "authorization",
    "cookie",
    "set-cookie",
    "token",
    "access_token",
    "id_token",
    "api_key",
    "apikey",
    "secret",
    "password",
}
CREDENTIAL_VALUES = ("bearer ", "basic ", "eyj", "sk-")

Start = Callable[[RunObserver, threading.Event], Awaitable[Envelope]]


@pytest.fixture
def governance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Governance]:
    configure_env(monkeypatch, tmp_path)
    yield from new_governance()


def _example(name: str) -> dict[str, Any]:
    document: dict[str, Any] = json.loads((EXAMPLES / f"{name}.json").read_text("utf-8"))
    return document


def _starting(conductor: Conductor, invocation: InvocationRequest) -> Start:
    def start(observer: RunObserver, cancel: threading.Event) -> Awaitable[Envelope]:
        return conductor.ainvoke(
            invocation, acting_for=TEST_PRINCIPAL, observer=observer, cancel=cancel
        )

    return start


def _normalised(event: dict[str, Any]) -> dict[str, Any]:
    """The event with what changes between two runs of the same input held fixed."""
    envelope = event.get("result")
    if isinstance(envelope, dict):
        envelope["invocation_id"] = FIXED_RUN_ID
        envelope["completed_at"] = FIXED_TIME
        envelope["telemetry"]["trace_id"] = "0" * 32
        for item in envelope.get("evidence") or []:
            item["retrieved_at"] = FIXED_TIME
    return event


def _record(start: Start, *, cancel_at: str | None = None) -> list[dict[str, Any]]:
    """The run's events as the browser receives them. With `cancel_at`, the run is cancelled once
    that stage has started."""

    async def go() -> list[dict[str, Any]]:
        cancellation = Cancellation()
        out = []
        async for event in stream_run(
            start, thread_id=THREAD, run_id=RUN, cancellation=cancellation
        ):
            out.append(json.loads(event.model_dump_json(by_alias=True)))
            if cancel_at is not None and getattr(event, "step_name", None) == cancel_at:
                cancellation.cancel()
        return out

    return [_normalised(e) for e in asyncio.run(go())]


def _credentials(value: Any, where: str = "") -> Iterator[str]:
    """Where `value` holds what looks like a credential, as JSON paths."""
    if isinstance(value, dict):
        for key, inner in value.items():
            if str(key).lower() in CREDENTIAL_KEYS:
                yield f"{where}.{key}"
            yield from _credentials(inner, f"{where}.{key}")
    elif isinstance(value, list):
        for i, inner in enumerate(value):
            yield from _credentials(inner, f"{where}[{i}]")
    elif isinstance(value, str) and value.lower().startswith(CREDENTIAL_VALUES):
        yield where


def _check(name: str, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    assert list(_credentials(events)) == [], name
    check_cassette(name, events)
    return events


def _last(events: list[dict[str, Any]]) -> dict[str, Any]:
    assert events[0]["type"] == "RUN_STARTED" and events[-1]["type"] == "RUN_FINISHED"
    return events[-1]


def test_succeeded(governance: Governance) -> None:
    invocation = InvocationRequest(
        agent_id=STANDARDS_AGENT_ID, input=_example("soil-chemistry.profile")
    )
    events = _check("succeeded.jsonl", _record(_starting(governance.conductor, invocation)))
    assert _last(events)["result"]["outcome"]["status"] == "succeeded"


def test_abstained(governance: Governance) -> None:
    invocation = InvocationRequest(agent_id=STANDARDS_AGENT_ID, input=_example("empty.profile"))
    events = _check("abstained.jsonl", _record(_starting(governance.conductor, invocation)))
    assert _last(events)["result"]["outcome"]["status"] == "abstained"


def test_run_error(governance: Governance) -> None:
    invocation = InvocationRequest(agent_id="no.such.agent", input=_example("empty.profile"))
    events = _check("run-error.jsonl", _record(_starting(governance.conductor, invocation)))
    assert [e["type"] for e in events] == ["RUN_ERROR"]


@pytest.fixture
def doubles(tmp_path: Path) -> Iterator[list[Conductor]]:
    made: list[Conductor] = []
    yield made
    for conductor in made:
        conductor.close()


def test_referred(tmp_path: Path, doubles: list[Conductor]) -> None:
    doubles.append(conductor := make_conductor(tmp_path, AbstainingStub(), profile=RESTRICTIVE))
    invocation = request("stub.abstain", fakes.message())
    events = _check("referred.jsonl", _record(_starting(conductor, invocation)))
    assert _last(events)["result"]["outcome"]["status"] == "referred"


def test_failed_grounding(tmp_path: Path, doubles: list[Conductor]) -> None:
    agent = ScriptedAgent(GroundingMode.NONE, fakes.review_of_input, steps=[Chat()])
    doubles.append(conductor := make_conductor(tmp_path, agent))
    events = _check(
        "failed-grounding.jsonl", _record(_starting(conductor, request(agent.spec.agent_id)))
    )
    assert _last(events)["result"]["problem"]["type"].endswith("/grounding-violation")


def test_cancelled(tmp_path: Path, doubles: list[Conductor]) -> None:
    release = threading.Event()

    def held(req: InvocationRequest, ctx: RunContext) -> AgentResult:
        assert release.wait(30), "the agent was never let answer"
        return fakes.review_of_input(req, ctx)

    agent = ScriptedAgent(GroundingMode.INPUT_ONLY, held)
    doubles.append(conductor := make_conductor(tmp_path, agent, remote=False))
    try:
        events = _record(_starting(conductor, request(agent.spec.agent_id)), cancel_at="agent")
    finally:
        release.set()
    _check("cancelled.jsonl", events)
    assert _last(events)["outcome"] == {"type": "cancelled"}


def test_every_cassette_is_made_here() -> None:
    """A cassette nothing here makes would never be checked, so it would go stale unnoticed."""
    made = {
        "succeeded.jsonl",
        "abstained.jsonl",
        "run-error.jsonl",
        "referred.jsonl",
        "failed-grounding.jsonl",
        "cancelled.jsonl",
    }
    assert {path.name for path in CASSETTES.glob("*.jsonl")} <= made
