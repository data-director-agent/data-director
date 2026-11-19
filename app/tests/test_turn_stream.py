"""A conversation turn streamed over AG-UI (docs/specs/app.md, "Run events to the browser"):
`POST /api/conversations/{id}/turns/stream` and its cancel. A turn goes to the profile's
orchestrator alone, so the outcomes no in-tree orchestrator gives on demand use the harness's
scripted doubles in its place.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import threading
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

import httpx
import pytest
from support import APP_URL, JSON_HEADERS, configure_env, dist_dir

from dd_agent_example_hello.agent import build as build_hello
from dd_agent_orchestrator_stub.agent import build as build_director
from dd_app.app import build_app
from dd_app.config import DEFAULT_PROFILE
from dd_app.governance import Governance
from dd_harness import testing as fakes
from dd_harness.conductor import Conductor
from dd_harness.identity import Unauthenticated
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
)
from dd_sdk.agent import Agent, AgentResult, RunContext
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import GroundingMode, InvocationRequest, Message, Principal

OTHER = Principal(principal_id="https://example.org/people/someone-else", name="Someone Else")
PERSON_HEADER = "x-test-person"
RUN = "run-1"


@dataclasses.dataclass(frozen=True)
class _People:
    """Acts for `TEST_PRINCIPAL`, or for `OTHER` when the request says so; refuses a request that
    names nobody, as a server that signs people in refuses one with no session."""

    def principal_for(self, headers: Mapping[str, str] | None) -> Principal:
        person = (headers or {}).get(PERSON_HEADER)
        if person == "me":
            return TEST_PRINCIPAL
        if person == "other":
            return OTHER
        raise Unauthenticated("no one is signed in")


ME = {PERSON_HEADER: "me"}


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    return configure_env(monkeypatch, tmp_path)


@pytest.fixture
def conductors() -> Iterator[list[Conductor]]:
    made: list[Conductor] = []
    yield made
    for conductor in made:
        conductor.close()


def _over(
    env: Path, made: list[Conductor], agent: Agent, *, profile: Path | None = None, **kw: Any
) -> tuple[Governance, Any]:
    """The app with `agent` as the profile's orchestrator."""
    made.append(
        conductor := make_conductor(env / "runs", agent, profile=profile or fakes.PERMISSIVE, **kw)
    )
    conductor.profile = dataclasses.replace(conductor.profile, orchestrator=agent.spec.agent_id)
    governance = Governance(conductor, _People())
    return governance, build_app(governance, dist_dir(env))


def _delegating(env: Path, made: list[Conductor]) -> tuple[Governance, Any]:
    """The app over `orchestrator.stub`, which delegates to `example.hello` through the app's own
    A2A routes, under the app's reference profile."""
    served: dict[str, Any] = {}

    def app_client(base_url: str, timeout_s: float) -> httpx.AsyncClient:
        return asgi_client_factory(served["app"])(base_url, timeout_s)

    registry = Registry.from_agents(
        [
            in_process(build_director(), delegate_client_factory=app_client),
            in_process(build_hello()),
        ]
    )
    made.append(
        conductor := Conductor(
            registry=registry, store=RunStore(env / "runs"), profile=load_profile(DEFAULT_PROFILE)
        )
    )
    conductor.harness_url = APP_URL
    governance = Governance(conductor, _People())
    served["app"] = build_app(governance, dist_dir(env))
    return governance, served["app"]


def _message_agent(mode: GroundingMode, behaviour: Any, **kw: Any) -> ScriptedAgent:
    """A scripted agent that accepts a conversation's `Message`, as an orchestrator does."""
    return ScriptedAgent(mode, behaviour, accepts=(ClassSchema.of(Message),), **kw)


class _Held:
    """An agent's behaviour that waits until the test lets it answer."""

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()

    def __call__(self, req: InvocationRequest, ctx: RunContext) -> AgentResult:
        self.entered.set()
        assert self.release.wait(30), "the test never let the agent answer"
        return fakes.review_of_input(req, ctx)


def _client(app: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=APP_URL)


def _events(text: str) -> list[dict[str, Any]]:
    return [
        json.loads(line[len("data: ") :]) for line in text.splitlines() if line.startswith("data: ")
    ]


def _input(
    conversation_id: str, agent_id: str, *, follows: str | None = None, **turn: Any
) -> dict[str, Any]:
    """A `RunAgentInput` as `HttpAgent` posts it, carrying the turn in `forwardedProps`."""
    return {
        "threadId": conversation_id,
        "runId": RUN,
        "messages": [],
        "state": {},
        "tools": [],
        "context": [],
        "forwardedProps": {
            "agent_id": agent_id,
            "message_text": "hello world",
            "follows": follows,
            **turn,
        },
    }


async def _start(hc: httpx.AsyncClient, headers: Mapping[str, str] = ME) -> str:
    response = await hc.post("/api/conversations", headers={**JSON_HEADERS, **headers})
    assert response.status_code == 201
    conversation_id: str = response.json()["conversation_id"]
    return conversation_id


def _stream_path(conversation_id: str) -> str:
    return f"/api/conversations/{conversation_id}/turns/stream"


def _cancel_path(conversation_id: str, run_id: str = RUN) -> str:
    return f"/api/conversations/{conversation_id}/turns/{run_id}/cancel"


def _turn(app: Any, agent_id: str, **turn: Any) -> list[dict[str, Any]]:
    async def go() -> list[dict[str, Any]]:
        async with _client(app) as hc:
            conversation_id = await _start(hc)
            response = await hc.post(
                _stream_path(conversation_id),
                json=_input(conversation_id, agent_id, **turn),
                headers=ME,
            )
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            events = _events(response.text)
            assert all(e.get("threadId", conversation_id) == conversation_id for e in events)
            return events

    return asyncio.run(go())


def _types(events: list[dict[str, Any]]) -> list[str]:
    return [e["type"] for e in events]


def _finished(events: list[dict[str, Any]]) -> dict[str, Any]:
    """The envelope a whole run's stream ends with, after its plan and stages."""
    types = _types(events)
    assert types[0] == "RUN_STARTED" and types[-1] == "RUN_FINISHED"
    assert events[1]["type"] == "CUSTOM" and events[1]["name"] == "dd.plan"
    assert "STEP_STARTED" in types and "STEP_FINISHED" in types
    return dict(events[-1]["result"])


def _stages(events: list[dict[str, Any]]) -> list[str]:
    return [e["stepName"] for e in events if e["type"] == "STEP_STARTED"]


# Each outcome, through the app's route.


def test_a_succeeded_turn_streams_its_stages_and_its_children(
    env: Path, conductors: list[Conductor]
) -> None:
    governance, app = _delegating(env, conductors)
    events = _turn(app, "orchestrator.stub")
    envelope = _finished(events)
    assert envelope["outcome"]["status"] == "succeeded"
    assert _stages(events) == ["gate", "input", "agent", "grounding", "sources"]
    [delegation] = envelope["delegations"]
    children = [e for e in events if e["type"].startswith("SUBAGENT_")]
    assert [e["type"] for e in children] == ["SUBAGENT_STARTED", "SUBAGENT_FINISHED"]
    assert {e["subagentRunId"] for e in children} == {delegation["delegated_invocation_id"]}
    assert children[0]["name"] == delegation["delegated_agent_id"]
    assert children[1]["result"] == {"status": delegation["delegated_status"]}
    # The child's full record is read back from the run store, and the turn is stored as the
    # JSON route stores it.
    assert governance.conductor.store.get(delegation["delegated_invocation_id"]) is not None
    assert governance.conductor.store.get(envelope["invocation_id"]) is not None


def test_an_abstained_turn_finishes_with_its_envelope(
    env: Path, conductors: list[Conductor]
) -> None:
    _, app = _over(env, conductors, AbstainingStub())
    envelope = _finished(_turn(app, "stub.abstain"))
    assert envelope["outcome"]["status"] == "abstained"


def test_a_referred_turn_has_no_input_or_agent_stage(
    env: Path, conductors: list[Conductor]
) -> None:
    _, app = _over(env, conductors, AbstainingStub(), profile=RESTRICTIVE)
    events = _turn(app, "stub.abstain")
    assert _finished(events)["outcome"]["status"] == "referred"
    assert "agent" not in _stages(events) and "input" not in _stages(events)


def test_a_turn_that_fails_grounding_is_reported_before_it_finishes(
    env: Path, conductors: list[Conductor]
) -> None:
    agent = _message_agent(GroundingMode.NONE, fakes.review_of_input, steps=[Chat()])
    _, app = _over(env, conductors, agent)
    events = _turn(app, agent.spec.agent_id)
    envelope = _finished(events)
    assert envelope["problem"]["type"].endswith("/grounding-violation")
    (report,) = [e["value"] for e in events if e.get("name") == "dd.grounding"]
    assert report["passed"] is False


@pytest.mark.parametrize(
    "turn",
    [
        {"agent_id": "not.the.orchestrator"},  # the conductor's turn refuses it
        {"follows": "01900000-0000-7000-8000-000000000001"},  # not the latest turn
    ],
)
def test_a_turn_refused_once_the_stream_is_open_is_run_error_alone(
    env: Path, conductors: list[Conductor], turn: dict[str, Any]
) -> None:
    governance, app = _over(env, conductors, AbstainingStub())
    agent_id = turn.pop("agent_id", "stub.abstain")
    events = _turn(app, agent_id, **turn)
    assert _types(events) == ["RUN_ERROR"]
    assert events[0]["message"]
    assert list(governance.conductor.store.iter_envelopes()) == []


# Cancelling.


def test_a_cancelled_turn_finishes_cancelled_and_is_stored_failed(
    env: Path, conductors: list[Conductor]
) -> None:
    held = _Held()
    agent = _message_agent(GroundingMode.INPUT_ONLY, held)
    governance, app = _over(env, conductors, agent, remote=False)

    async def go() -> tuple[list[dict[str, Any]], int, int, int]:
        async with _client(app) as hc:
            conversation_id = await _start(hc)
            run = asyncio.create_task(
                hc.post(
                    _stream_path(conversation_id),
                    json=_input(conversation_id, agent.spec.agent_id),
                    headers=ME,
                )
            )
            assert await asyncio.to_thread(held.entered.wait, 30)
            theirs = await hc.post(
                _cancel_path(conversation_id), headers={**JSON_HEADERS, PERSON_HEADER: "other"}
            )
            mine = await hc.post(_cancel_path(conversation_id), headers={**JSON_HEADERS, **ME})
            events = _events((await run).text)
            held.release.set()
            again = await hc.post(_cancel_path(conversation_id), headers={**JSON_HEADERS, **ME})
            return events, theirs.status_code, mine.status_code, again.status_code

    events, theirs, mine, again = asyncio.run(go())
    assert (theirs, mine, again) == (404, 202, 404)
    assert _types(events)[0] == "RUN_STARTED"
    assert events[-1]["type"] == "RUN_FINISHED"
    assert events[-1]["outcome"] == {"type": "cancelled"}
    assert "result" not in events[-1]
    assert "agent" in _stages(events)
    governance.conductor.close()  # waits for the run's thread, which stores it
    [stored] = list(governance.conductor.store.iter_envelopes())
    assert stored["outcome"]["status"] == "failed"
    assert stored["problem"]["type"].endswith("/run-cancelled")


# What is refused before the stream opens.


def _refusal(app: Any, make: Callable[[str], tuple[str, Any, dict[str, str]]]) -> httpx.Response:
    async def go() -> httpx.Response:
        async with _client(app) as hc:
            conversation_id = await _start(hc)
            path, body, headers = make(conversation_id)
            if isinstance(body, (bytes, str)):
                return await hc.post(path, content=body, headers=headers)
            return await hc.post(path, json=body, headers=headers)

    return asyncio.run(go())


@pytest.mark.parametrize(
    ("make", "status", "slug"),
    [
        (lambda c: (_stream_path(c), _input(c, "stub.abstain"), {}), 401, "unauthenticated"),
        (
            lambda c: (
                _stream_path(c),
                json.dumps(_input(c, "stub.abstain")),
                {**ME, "content-type": "text/plain"},
            ),
            415,
            "unsupported-media-type",
        ),
        (
            lambda c: (_stream_path(c), {**_input(c, "stub.abstain"), "runId": None}, ME),
            400,
            "",
        ),
        (
            lambda c: (_stream_path(c), {**_input(c, "stub.abstain"), "threadId": "another"}, ME),
            400,
            "",
        ),
        (
            lambda c: (_stream_path(c), {**_input(c, "stub.abstain"), "forwardedProps": {}}, ME),
            400,
            "",
        ),
        (
            lambda c: (
                _stream_path(c),
                _input(c, "stub.abstain"),
                {PERSON_HEADER: "other"},
            ),
            404,
            "conversation-not-found",
        ),
        (lambda c: (_cancel_path(c), {}, ME), 404, "run-not-streaming"),
        (lambda c: (_cancel_path(c), {}, {}), 401, "unauthenticated"),
    ],
)
def test_what_is_refused_before_the_stream_opens_is_a_problem(
    env: Path,
    conductors: list[Conductor],
    make: Callable[[str], tuple[str, Any, dict[str, str]]],
    status: int,
    slug: str,
) -> None:
    governance, app = _over(env, conductors, AbstainingStub())
    response = _refusal(app, make)
    assert response.status_code == status
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"].endswith(f"/{slug}" if slug else "")
    assert list(governance.conductor.store.iter_envelopes()) == []
