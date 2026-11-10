"""The AG-UI binding (docs/specs/transport.md): the order of a run's events for each kind of
outcome, `RUN_ERROR` for a request that makes no run, and cancelling. Driven in-process over
`dd_harness.transport.agui`'s own routes; nothing here names a real agent."""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from starlette.applications import Starlette

from dd_harness import testing as fakes
from dd_harness.conductor import Conductor
from dd_harness.grounding import GroundingReport
from dd_harness.identity import OperatorAssertion
from dd_harness.observe import STEPS, Step
from dd_harness.sources import SourceReport
from dd_harness.testing import (
    RESTRICTIVE,
    TEST_PRINCIPAL,
    AbstainingStub,
    Chat,
    ScriptedAgent,
    make_conductor,
    request,
)
from dd_harness.transport.agui import Cancellation, RunsInFlight, agui_routes, stream_run
from dd_sdk.agent import AgentResult, RunContext
from dd_sdk.contract.models import (
    GroundingMode,
    InvocationRequest,
    Principal,
    new_invocation_id,
    to_document,
)

BASE = "http://testserver"
OTHER = Principal(principal_id="https://example.org/people/someone-else", name="Someone Else")
PLANNED = [{"id": step.id, "label": step.label} for step in STEPS]


def _app(conductor: Conductor, principal: Principal = TEST_PRINCIPAL) -> Starlette:
    return Starlette(routes=agui_routes(conductor, OperatorAssertion(principal)))


def _body(doc: dict[str, Any], *, thread_id: str = "t1", run_id: str = "r1") -> dict[str, Any]:
    return {
        "threadId": thread_id,
        "runId": run_id,
        "messages": [],
        "state": {},
        "tools": [],
        "context": [],
        "forwardedProps": {"request": doc},
    }


def _events(text: str) -> list[dict[str, Any]]:
    return [
        json.loads(line[len("data: ") :]) for line in text.splitlines() if line.startswith("data: ")
    ]


def _client(app: Starlette) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE)


def _post(app: Starlette, body: dict[str, Any]) -> list[dict[str, Any]]:
    async def go() -> list[dict[str, Any]]:
        async with _client(app) as hc:
            return _events((await hc.post("/agui", json=body)).text)

    return asyncio.run(go())


def _run(conductor: Conductor, invocation: InvocationRequest) -> list[dict[str, Any]]:
    try:
        return _post(_app(conductor), _body(to_document(invocation)))
    finally:
        conductor.close()


def _steps(events: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return [
        (e["type"], e["stepName"]) for e in events if e["type"] in ("STEP_STARTED", "STEP_FINISHED")
    ]


def _ran(*ids: str) -> list[tuple[str, str]]:
    return [pair for i in ids for pair in (("STEP_STARTED", i), ("STEP_FINISHED", i))]


def _custom(events: list[dict[str, Any]], name: str) -> dict[str, Any]:
    (value,) = [e["value"] for e in events if e["type"] == "CUSTOM" and e["name"] == name]
    return dict(value)


def _check_shape(events: list[dict[str, Any]]) -> dict[str, Any]:
    """What every run's stream shares: started, then the plan, then the stages, the reports inside
    their stages, then finished with the envelope. Returns the envelope."""
    types = [e["type"] for e in events]
    assert types[0] == "RUN_STARTED" and types[-1] == "RUN_FINISHED"
    assert events[1]["type"] == "CUSTOM" and events[1]["name"] == "dd.plan"
    assert events[1]["value"] == {"steps": PLANNED}
    order = [step.id for step in STEPS]
    started = [name for kind, name in _steps(events) if kind == "STEP_STARTED"]
    assert started == sorted(started, key=order.index)
    # Each report sits inside its own stage.
    for name, step in (("dd.grounding", "grounding"), ("dd.sources", "sources")):
        at = next(i for i, e in enumerate(events) if e.get("name") == name)
        assert events[at - 1] == {"type": "STEP_STARTED", "stepName": step}
        assert events[at + 1] == {"type": "STEP_FINISHED", "stepName": step}
    return dict(events[-1]["result"])


@pytest.mark.requirement("C5.1", "DD-OUTCOME")
def test_a_succeeded_run_streams_every_stage_and_both_reports(runs_dir: Path) -> None:
    agent = ScriptedAgent(GroundingMode.INPUT_ONLY, fakes.review_of_input)
    events = _run(make_conductor(runs_dir, agent), request(agent.spec.agent_id))
    envelope = _check_shape(events)
    assert envelope["outcome"]["status"] == "succeeded"
    assert _steps(events) == _ran("gate", "input", "agent", "grounding", "sources")
    assert _custom(events, "dd.grounding")["passed"] is True
    assert _custom(events, "dd.grounding")["mode"] == "input_only"
    assert _custom(events, "dd.sources")["passed"] is True


@pytest.mark.requirement("C5.1", "DD-OUTCOME")
def test_an_abstained_run_finishes_with_its_envelope(runs_dir: Path) -> None:
    events = _run(
        make_conductor(runs_dir, AbstainingStub()), request("stub.abstain", fakes.message())
    )
    envelope = _check_shape(events)
    assert envelope["outcome"]["status"] == "abstained"
    assert _steps(events) == _ran("gate", "input", "agent", "grounding", "sources")


@pytest.mark.requirement("C5.1", "DD-POLICY")
def test_a_referred_run_has_no_input_or_agent_stage(runs_dir: Path) -> None:
    conductor = make_conductor(runs_dir, AbstainingStub(), profile=RESTRICTIVE)
    events = _run(conductor, request("stub.abstain", fakes.message()))
    envelope = _check_shape(events)
    assert envelope["outcome"]["status"] == "referred"
    assert _steps(events) == _ran("gate", "grounding", "sources")


@pytest.mark.requirement("C5.1", "DD-POLICY")
def test_a_run_the_gate_refuses_has_no_input_or_agent_stage(runs_dir: Path) -> None:
    agent = ScriptedAgent(
        GroundingMode.INPUT_ONLY, fakes.review_of_input, agent_id="advisor.quality"
    )
    conductor = make_conductor(runs_dir, agent, profile=RESTRICTIVE)
    events = _run(conductor, request(agent.spec.agent_id))
    envelope = _check_shape(events)
    assert envelope["problem"]["type"].endswith("/action-class-mismatch")
    assert _steps(events) == _ran("gate", "grounding", "sources")


@pytest.mark.requirement("C5.1", "DD-INPUT-ACCEPTS")
def test_an_input_the_agent_does_not_accept_has_no_agent_stage(runs_dir: Path) -> None:
    events = _run(make_conductor(runs_dir, AbstainingStub()), request("stub.abstain"))
    envelope = _check_shape(events)
    assert envelope["problem"]["type"].endswith("/input-not-accepted")
    assert _steps(events) == _ran("gate", "input", "grounding", "sources")


@pytest.mark.requirement("C5.1", "DD-GROUNDING")
def test_a_grounding_violation_is_reported_before_the_failed_run(runs_dir: Path) -> None:
    agent = ScriptedAgent(GroundingMode.NONE, fakes.review_of_input, steps=[Chat()])
    events = _run(make_conductor(runs_dir, agent), request(agent.spec.agent_id))
    envelope = _check_shape(events)
    report = _custom(events, "dd.grounding")
    assert report["passed"] is False
    assert any(v.startswith("N1") for v in report["violations"])
    assert envelope["outcome"]["status"] == "failed"
    assert envelope["problem"]["type"].endswith("/grounding-violation")


@pytest.mark.requirement("C5.1")
@pytest.mark.parametrize(
    "body",
    [
        pytest.param(_body({}) | {"forwardedProps": {}}, id="no-request"),
        pytest.param(_body(to_document(request("no.such.agent"))), id="unknown-agent"),
        pytest.param(
            _body(
                to_document(request("stub.abstain").model_copy(update={"conversation_id": "c1"})),
                thread_id="another",
            ),
            id="thread-is-not-the-conversation",
        ),
    ],
)
def test_a_request_that_makes_no_run_is_run_error_alone(
    runs_dir: Path, body: dict[str, Any]
) -> None:
    conductor = make_conductor(runs_dir, AbstainingStub())
    try:
        events = _post(_app(conductor), body)
    finally:
        conductor.close()
    assert [e["type"] for e in events] == ["RUN_ERROR"]
    assert events[0]["message"]
    assert list(conductor.store.iter_envelopes()) == []


class _Held:
    """An agent's behaviour that waits until the test lets it answer."""

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()

    def __call__(self, req: InvocationRequest, ctx: RunContext) -> AgentResult:
        self.entered.set()
        assert self.release.wait(30), "the test never let the agent answer"
        return fakes.review_of_input(req, ctx)


async def _entered(held: _Held) -> None:
    assert await asyncio.to_thread(held.entered.wait, 30)


def _stored(conductor: Conductor, invocation_id: str) -> dict[str, Any]:
    conductor.close()  # waits for the run's thread, which stores it
    stored = conductor.store.get(invocation_id)
    assert stored is not None
    return stored


@pytest.mark.requirement("C5.1", "DD-OUTCOME")
def test_a_cancelled_run_finishes_cancelled_and_is_stored_failed(runs_dir: Path) -> None:
    held = _Held()
    agent = ScriptedAgent(GroundingMode.INPUT_ONLY, held)
    conductor = make_conductor(runs_dir, agent, remote=False)
    app = _app(conductor)
    invocation = request(agent.spec.agent_id)

    async def go() -> tuple[list[dict[str, Any]], int, int]:
        async with _client(app) as hc:
            run = asyncio.create_task(hc.post("/agui", json=_body(to_document(invocation))))
            await _entered(held)
            mine = await hc.post("/agui/runs/r1/cancel")
            events = _events((await run).text)
            # The stream ended without waiting for the agent; once it answers, nothing is left to
            # cancel.
            held.release.set()
            again = await hc.post("/agui/runs/r1/cancel")
            return events, mine.status_code, again.status_code

    events, mine, again = asyncio.run(go())
    assert (mine, again) == (202, 404)
    assert events[0]["type"] == "RUN_STARTED"
    assert events[-1]["type"] == "RUN_FINISHED"
    assert events[-1]["outcome"] == {"type": "cancelled"}
    assert "result" not in events[-1]
    assert ("STEP_STARTED", "agent") in _steps(events)
    stored = _stored(conductor, invocation.invocation_id)
    assert stored["outcome"]["status"] == "failed"
    assert stored["problem"]["type"].endswith("/run-cancelled")
    assert "payload" not in stored


@pytest.mark.requirement("C5.1", "DD-ACTS-FOR")
def test_only_the_principal_who_started_a_run_may_cancel_it(runs_dir: Path) -> None:
    held = _Held()
    agent = ScriptedAgent(GroundingMode.INPUT_ONLY, held)
    conductor = make_conductor(runs_dir, agent, remote=False)
    runs = RunsInFlight()
    mine = Starlette(routes=agui_routes(conductor, OperatorAssertion(TEST_PRINCIPAL), runs))
    theirs = Starlette(routes=agui_routes(conductor, OperatorAssertion(OTHER), runs))
    invocation = request(agent.spec.agent_id)

    async def go() -> tuple[int, list[dict[str, Any]]]:
        async with _client(mine) as hc, _client(theirs) as other:
            run = asyncio.create_task(hc.post("/agui", json=_body(to_document(invocation))))
            await _entered(held)
            refused = (await other.post("/agui/runs/r1/cancel")).status_code
            held.release.set()
            return refused, _events((await run).text)

    refused, events = asyncio.run(go())
    assert refused == 404
    assert events[-1]["result"]["outcome"]["status"] == "succeeded"
    conductor.close()


@pytest.mark.requirement("C5.1")
def test_a_stream_the_client_leaves_cancels_its_run(runs_dir: Path) -> None:
    held = _Held()
    agent = ScriptedAgent(GroundingMode.INPUT_ONLY, held)
    conductor = make_conductor(runs_dir, agent, remote=False)
    invocation = request(agent.spec.agent_id)

    def start(observer: Any, cancel: threading.Event) -> Any:
        return conductor.ainvoke(
            invocation, acting_for=TEST_PRINCIPAL, observer=observer, cancel=cancel
        )

    async def go() -> list[str]:
        stream = stream_run(start, thread_id="t1", run_id="r1", cancellation=Cancellation())
        seen = []
        async for event in stream:
            seen.append(event.type.value)
            if getattr(event, "step_name", None) == "agent":
                break
        await stream.aclose()  # what a dropped connection does
        held.release.set()
        return seen

    seen = asyncio.run(go())
    assert seen[0] == "RUN_STARTED"
    stored = _stored(conductor, invocation.invocation_id)
    assert stored["problem"]["type"].endswith("/run-cancelled")


def test_a_run_id_streaming_already_is_refused(runs_dir: Path) -> None:
    runs = RunsInFlight()

    async def go() -> None:
        runs.open(TEST_PRINCIPAL, "r1")
        with pytest.raises(ValueError, match="already running"):
            runs.open(TEST_PRINCIPAL, "r1")
        runs.open(OTHER, "r1")  # another principal's runs are theirs

    asyncio.run(go())


class _Recording:
    def __init__(self, fail: bool = False) -> None:
        self.told: list[tuple[str, str]] = []
        self.fail = fail

    def _note(self, what: str, detail: str) -> None:
        self.told.append((what, detail))
        if self.fail:
            raise RuntimeError("a broken watcher")

    def plan(self, steps: tuple[Step, ...]) -> None:
        self._note("plan", ",".join(step.id for step in steps))

    def step_started(self, step: Step) -> None:
        self._note("started", step.id)

    def step_finished(self, step: Step) -> None:
        self._note("finished", step.id)

    def grounding(self, report: GroundingReport) -> None:
        self._note("grounding", str(report.passed))

    def sources(self, report: SourceReport) -> None:
        self._note("sources", str(report.passed))


@pytest.fixture
def scripted(runs_dir: Path) -> Iterator[Callable[[], tuple[Conductor, InvocationRequest]]]:
    made: list[Conductor] = []

    def make() -> tuple[Conductor, InvocationRequest]:
        agent = ScriptedAgent(GroundingMode.INPUT_ONLY, fakes.review_of_input)
        made.append(conductor := make_conductor(runs_dir, agent, remote=False))
        return conductor, request(agent.spec.agent_id)

    yield make
    for conductor in made:
        conductor.close()


def test_the_conductor_tells_its_observer_each_stage_in_pairs_and_in_order(
    scripted: Callable[[], tuple[Conductor, InvocationRequest]],
) -> None:
    conductor, invocation = scripted()
    watcher = _Recording()
    conductor.invoke(invocation, acting_for=TEST_PRINCIPAL, observer=watcher)
    assert watcher.told[0] == ("plan", ",".join(step.id for step in STEPS))
    stages = [(what, step) for what, step in watcher.told if what in ("started", "finished")]
    assert stages == [
        pair for step in STEPS for pair in (("started", step.id), ("finished", step.id))
    ]
    assert ("grounding", "True") in watcher.told and ("sources", "True") in watcher.told


def test_a_broken_observer_changes_nothing_about_the_run(
    scripted: Callable[[], tuple[Conductor, InvocationRequest]],
) -> None:
    conductor, invocation = scripted()
    envelope = conductor.invoke(
        invocation, acting_for=TEST_PRINCIPAL, observer=_Recording(fail=True)
    )
    assert envelope.outcome.status.value == "succeeded"
    assert conductor.store.get(invocation.invocation_id) is not None


@pytest.mark.requirement("DD-OUTCOME")
def test_a_run_cancelled_before_it_starts_never_runs_its_agent(runs_dir: Path) -> None:
    agent = ScriptedAgent(GroundingMode.INPUT_ONLY, fakes.review_of_input)
    conductor = make_conductor(runs_dir, agent, remote=False)
    cancel = threading.Event()
    cancel.set()
    envelope = conductor.invoke(
        request(agent.spec.agent_id), acting_for=TEST_PRINCIPAL, cancel=cancel
    )
    assert envelope.problem is not None and envelope.problem.type.endswith("/run-cancelled")
    assert agent.calls == 0


def test_the_replay_of_a_stored_run_starts_and_finishes(runs_dir: Path) -> None:
    conductor = make_conductor(runs_dir, AbstainingStub())
    envelope = conductor.invoke(request("stub.abstain", fakes.message()), acting_for=TEST_PRINCIPAL)
    app = _app(conductor)

    async def go() -> tuple[list[dict[str, Any]], int]:
        async with _client(app) as hc:
            found = _events((await hc.get(f"/agui/runs/{envelope.invocation_id}")).text)
            missing = (await hc.get(f"/agui/runs/{new_invocation_id()}")).status_code
            return found, missing

    found, missing = asyncio.run(go())
    conductor.close()
    assert [e["type"] for e in found] == ["RUN_STARTED", "RUN_FINISHED"]
    assert found[-1]["result"] == envelope.to_document()
    assert missing == 404
