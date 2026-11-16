"""The AG-UI cassettes the shell replays (`app/web/cassettes`, docs/specs/transport.md): each is
what the harness's AG-UI binding streams for one kind of run, made here with the agents in
process. Outside CI a stale cassette is rewritten (`support.check_cassette`); in CI it fails.

The succeeded, abstained and refused runs go through the app's own conductor and agents; the
referred, withheld and cancelled ones need an outcome no in-tree agent gives on demand, so they use
the harness's scripted doubles. The delegated one is a conversation turn, made as the app's turn
stream makes it (`Governance.turn_run`), with the orchestrator's child in it as `SUBAGENT_*`.
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from support import (
    APP_URL,
    CASSETTES,
    check_cassette,
    configure_env,
    dist_dir,
    new_governance,
)

from dd_agent_example_hello.agent import build as build_hello
from dd_agent_orchestrator_stub.agent import build as build_director
from dd_app.app import build_app
from dd_app.config import DEFAULT_PROFILE
from dd_app.governance import Governance
from dd_harness import testing as fakes
from dd_harness.conductor import Conductor
from dd_harness.identity import OperatorAssertion
from dd_harness.observe import RunObserver
from dd_harness.policy import load_profile
from dd_harness.registry import Registry
from dd_harness.store import RunStore
from dd_harness.testing import (
    RESTRICTIVE,
    TEST_PRINCIPAL,
    AbstainingStub,
    Chat,
    ScriptedAgent,
    asgi_client_factory,
    in_process,
    make_conductor,
    request,
)
from dd_harness.transport.agui import Cancellation, stream_run
from dd_sdk.agent import AgentResult, RunContext
from dd_sdk.contract.models import Envelope, GroundingMode, InvocationRequest

EXAMPLES = Path(__file__).resolve().parents[1] / "config/examples"
STANDARDS_AGENT_ID = "advisor.standards"
FIXED_RUN_ID = "01900000-0000-7000-8000-000000000001"
FIXED_CHILD_ID = "01900000-0000-7000-8000-000000000002"
FIXED_CONVERSATION_ID = "01900000-0000-7000-8000-000000000003"
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
    if event["type"] == "RUN_FINISHED" and isinstance(envelope, dict):
        # The run's id is also in what cites its input (`input:<id>`).
        envelope = json.loads(json.dumps(envelope).replace(envelope["invocation_id"], FIXED_RUN_ID))
        event["result"] = envelope
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


def test_delegated(tmp_path: Path, doubles: list[Conductor]) -> None:
    """A conversation turn to `orchestrator.stub`, which delegates to `example.hello` through the
    app's own A2A routes, under the app's reference profile."""
    served: dict[str, Any] = {}

    def app_client(base_url: str, timeout_s: float) -> httpx.AsyncClient:
        return asgi_client_factory(served["app"])(base_url, timeout_s)

    registry = Registry.from_agents(
        [
            in_process(build_director(), delegate_client_factory=app_client),
            in_process(build_hello()),
        ]
    )
    conductor = Conductor(
        registry=registry, store=RunStore(tmp_path / "runs"), profile=load_profile(DEFAULT_PROFILE)
    )
    doubles.append(conductor)
    conductor.harness_url = APP_URL
    governance = Governance(conductor, OperatorAssertion(TEST_PRINCIPAL))
    served["app"] = build_app(governance, dist_dir(tmp_path))
    conversation_id = governance.start_conversation(TEST_PRINCIPAL)

    def start(observer: RunObserver, cancel: threading.Event) -> Awaitable[Envelope]:
        return governance.turn_run(
            conversation_id,
            "orchestrator.stub",
            "hello world",
            None,
            TEST_PRINCIPAL,
            observer=observer,
            cancel=cancel,
        )

    recorded = _record(start)
    envelope = _last(recorded)["result"]
    [delegation] = envelope["delegations"]
    # The identifiers and the child's content hash change from one run to the next.
    text = json.dumps(recorded)
    for found, fixed in (
        (delegation["delegated_invocation_id"], FIXED_CHILD_ID),
        (delegation["content_hash"], "0" * 64),
        (conversation_id, FIXED_CONVERSATION_ID),
    ):
        text = text.replace(found, fixed)
    events = _check("delegated.jsonl", json.loads(text))
    types = [e["type"] for e in events]
    assert types.index("SUBAGENT_STARTED") < types.index("SUBAGENT_FINISHED")
    assert _last(events)["result"]["outcome"]["status"] == "succeeded"


def test_every_cassette_is_made_here() -> None:
    """A cassette nothing here makes would never be checked, so it would go stale unnoticed."""
    made = {
        "succeeded.jsonl",
        "abstained.jsonl",
        "run-error.jsonl",
        "referred.jsonl",
        "failed-grounding.jsonl",
        "cancelled.jsonl",
        "delegated.jsonl",
    }
    assert {path.name for path in CASSETTES.glob("*.jsonl")} <= made
