"""The Data Director app's server: its reference configuration, what `GET /api/agents` tells the
shell, start-up, and the fixture the shell's tests are drawn from.

An alpha substantiates no requirement, so these tests carry no requirement marker.
"""

from __future__ import annotations

import json
import os
import re
import webbrowser
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from a2a.helpers import get_data_parts
from a2a.types import TaskState
from starlette.testclient import TestClient

from dd_agent_director.agent import build as build_director
from dd_agent_hello.agent import build as build_hello
from dd_agent_quality.agent import build as build_quality
from dd_agent_standards import factory as standards
from dd_app import app as dd_app
from dd_app.app import ShellNotBuiltError, build_app
from dd_app.config import DEFAULT_AGENTS_CONFIG, DEFAULT_PROFILE, settings_from_env
from dd_app.governance import Governance
from dd_harness.conductor import Conductor
from dd_harness.identity import IdentityError
from dd_harness.policy import load_profile
from dd_harness.registry import Registry, load_config
from dd_harness.remote import RemoteAgent, RemoteAgentError
from dd_harness.store import RunStore
from dd_harness.testing import (
    PERMISSIVE,
    RESTRICTIVE,
    TEST_PRINCIPAL,
    AbstainingStub,
    asgi_client_factory,
    in_process,
    make_conductor,
    send_to_harness,
)
from dd_harness.transport.a2a import DELEGATED_ONLY
from dd_sdk.agent import Agent
from dd_sdk.contract.models import UUID7_PATTERN, InvocationRequest

PATH_VARIABLES = ("DD_PROFILE", "DD_AGENTS_CONFIG", "DD_SOURCES_CONFIG")
# The shell's component and browser tests are drawn from these, so each must be what the server
# says. `DD_WRITE_FIXTURES=1 uv run pytest app/tests` rewrites them. `agents.json` is the
# reference set; `agents-several.json` is five agents of different grounding modes and payload
# shapes under the permissive test profile, which does not list the standards advisor.
FIXTURES = Path(__file__).resolve().parents[1] / "web/fixtures"
APP_URL = "http://app.test"
STANDARDS_AGENT_ID = "standards.advisor"


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """The app's reference set, a principal, and runs written under `tmp_path`.

    The reference agent list names services these tests do not start, and whether one happens to
    be running would change what the server says, so it is replaced by an empty list. A test
    that needs an agent serves it in memory over A2A (`with_standards`).
    """
    for variable in PATH_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    no_remote_agents = tmp_path / "agents.yaml"
    no_remote_agents.write_text("agents: []\n", encoding="utf-8")
    monkeypatch.setenv("DD_AGENTS_CONFIG", str(no_remote_agents))
    for variable in ("DD_STANDARDS_RETRIEVAL", "DD_STANDARDS_EXPLAINER", "DD_SNAPSHOT_PATH"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("DD_PRINCIPAL_ID", TEST_PRINCIPAL.principal_id)
    monkeypatch.setenv("DD_PRINCIPAL_NAME", TEST_PRINCIPAL.name)
    monkeypatch.setenv("DD_RUNS_DIR", str(tmp_path))
    return tmp_path


def with_standards(governance: Governance) -> Governance:
    """`governance` with the standards advisor registered as the reference list would reach its
    service, but served in memory over A2A."""
    governance.conductor.registry.add(in_process(standards.build()))
    return governance


@pytest.fixture
def governance(env: Path) -> Iterator[Governance]:
    governance = with_standards(Governance.create(settings_from_env(), APP_URL))
    yield governance
    governance.worker.shutdown()


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    built = tmp_path / "dist"
    built.mkdir()
    (built / "index.html").write_text("<!doctype html><title>shell</title>", encoding="utf-8")
    return built


def agents_response(governance: Governance, dist: Path) -> dict[str, Any]:
    response = TestClient(build_app(governance, dist)).get("/api/agents")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def test_the_reference_set_lists_and_enables_every_in_tree_agent():
    entries = load_config(DEFAULT_AGENTS_CONFIG)
    assert [(e["name"], e["url"]) for e in entries] == [
        ("hello", "http://127.0.0.1:8101"),
        ("quality", "http://127.0.0.1:8102"),
        ("standards", "http://127.0.0.1:8105"),
        ("director", "http://127.0.0.1:8106"),
    ]
    enabled = (
        STANDARDS_AGENT_ID,
        "hello.world",
        "quality.reviewer",
        "director.stub",
    )
    assert load_profile(DEFAULT_PROFILE).agents == dict.fromkeys(enabled, "advise")


def test_the_app_runs_no_agent_its_list_does_not_name(env: Path):
    # Every agent is a service (ADR-0027): with none listed, the app has none to run.
    governance = Governance.create(settings_from_env(), APP_URL)
    try:
        assert governance.conductor.registry.ids() == []
        assert governance.conductor.profile.profile_id == "data-director-app"
        assert governance.acting_for == TEST_PRINCIPAL
    finally:
        governance.worker.shutdown()


def test_api_agents_gives_each_manifest_beside_what_the_profile_assigns(
    governance: Governance, dist: Path
):
    body = agents_response(governance, dist)
    (standards,) = body["agents"]
    assert standards["agent_id"] == STANDARDS_AGENT_ID
    assert standards["action_class"] == "advise"  # what the card declares
    assert standards["assigned_action_class"] == "advise"  # what the steward assigns
    assert standards["requires_approval"] is False
    assert standards["grounding_mode"] == "retrieval"
    assert body["unavailable"] == {} and body["incompatible"] == {}
    assert body["profile"]["ref"] == "profile:data-director-app@v3"
    assert body["acting_for"] == {"name": TEST_PRINCIPAL.name, "assurance": "asserted"}


def test_an_agent_the_profile_does_not_list_is_shown_unassigned(
    env: Path, dist: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("DD_PROFILE", str(RESTRICTIVE))
    governance = with_standards(Governance.create(settings_from_env(), APP_URL))
    try:
        (standards,) = agents_response(governance, dist)["agents"]
    finally:
        governance.worker.shutdown()
    assert standards["assigned_action_class"] is None
    assert standards["requires_approval"] is False


def test_every_other_path_serves_the_built_shell(governance: Governance, dist: Path):
    response = TestClient(build_app(governance, dist)).get("/")
    assert response.status_code == 200
    assert "<title>shell</title>" in response.text


def test_the_agents_page_serves_the_built_shell(governance: Governance, dist: Path):
    response = TestClient(build_app(governance, dist)).get("/agents")
    assert response.status_code == 200
    assert "<title>shell</title>" in response.text


def test_an_unbuilt_shell_stops_start_up(governance: Governance, tmp_path: Path):
    with pytest.raises(ShellNotBuiltError, match="npm ci && npm run build"):
        build_app(governance, tmp_path / "missing")


def test_no_principal_stops_start_up(env: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DD_PRINCIPAL_ID")
    with pytest.raises(IdentityError, match="DD_PRINCIPAL_ID"):
        Governance.create(settings_from_env(), APP_URL)


def test_a_listed_agent_that_is_not_running_is_shown_unavailable(
    env: Path, monkeypatch: pytest.MonkeyPatch
):
    # The app does not quietly run its own copy in its place.
    agents = env / "with-standards.yaml"
    agents.write_text("agents:\n  - name: standards\n    url: http://127.0.0.1:9\n")
    monkeypatch.setenv("DD_AGENTS_CONFIG", str(agents))

    def unreachable(url: str, **_: Any) -> RemoteAgent:
        raise RemoteAgentError(f"{url}: connection refused")

    monkeypatch.setattr(RemoteAgent, "from_url", unreachable)
    governance = Governance.create(settings_from_env(), APP_URL)
    try:
        assert governance.conductor.registry.ids() == []
        assert "standards" in governance.conductor.registry.unavailable
    finally:
        governance.worker.shutdown()


def check_fixture(name: str, body: dict[str, Any]) -> None:
    path = FIXTURES / name
    text = json.dumps(body, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if os.environ.get("DD_WRITE_FIXTURES") == "1":
        path.write_text(text, encoding="utf-8")
    assert path.read_text(encoding="utf-8") == text, (
        f"{path} is stale; rerun with DD_WRITE_FIXTURES=1"
    )


def test_the_reference_fixture_is_what_the_server_says(governance: Governance, dist: Path):
    check_fixture("agents.json", agents_response(governance, dist))


def test_the_several_agents_fixture_is_what_the_server_says(env: Path, dist: Path):
    agents: list[Agent] = [
        build_hello(),
        build_quality(),
        AbstainingStub(),
        standards.build(),
    ]
    governance = Governance(
        make_conductor(env, *agents, remote=False, profile=PERMISSIVE),
        TEST_PRINCIPAL,
        ThreadPoolExecutor(max_workers=1),
    )
    try:
        check_fixture("agents-several.json", agents_response(governance, dist))
    finally:
        governance.worker.shutdown()


# Runs (`POST /api/runs`, `GET /api/runs`, `GET /api/runs/{id}`) and examples. The run fixtures
# hold fixed values for what changes between two runs of the same input.

EXAMPLES = Path(__file__).resolve().parents[1] / "config/examples"
FIXED_RUN_ID = "01900000-0000-7000-8000-000000000001"
FIXED_TIME = "2026-01-01T00:00:00Z"


def example(name: str) -> dict[str, Any]:
    document: dict[str, Any] = json.loads((EXAMPLES / f"{name}.json").read_text("utf-8"))
    return document


def run(client: TestClient, input: Any, agent_id: str = STANDARDS_AGENT_ID) -> Any:
    return client.post("/api/runs", json={"agent_id": agent_id, "input": input})


def normalised(body: dict[str, Any]) -> dict[str, Any]:
    envelope = body["envelope"]
    envelope["invocation_id"] = FIXED_RUN_ID
    envelope["completed_at"] = FIXED_TIME
    envelope["telemetry"]["trace_id"] = "0" * 32
    for item in envelope.get("evidence") or []:
        item["retrieved_at"] = FIXED_TIME
    return body


def test_a_run_answers_with_its_envelope_and_the_checks(governance: Governance, dist: Path):
    response = run(TestClient(build_app(governance, dist)), example("soil-chemistry.profile"))
    assert response.status_code == 200
    body = response.json()
    envelope = body["envelope"]
    assert envelope["agent_id"] == STANDARDS_AGENT_ID
    assert envelope["outcome"]["status"] == "succeeded"
    assert envelope["acting_for"]["name"] == TEST_PRINCIPAL.name
    assert envelope["evidence"] and envelope["payload"]["schema_class"] == "Recommendations"
    assert body["checks"]["grounding"]["passed"] is True
    assert body["checks"]["sources"]["passed"] is True
    assert body["checks"]["sources"]["summary"].startswith("sources: ")
    check_fixture("run-succeeded.json", normalised(body))


def test_a_profile_with_nothing_to_search_on_abstains(governance: Governance, dist: Path):
    body = run(TestClient(build_app(governance, dist)), example("empty.profile")).json()
    assert body["envelope"]["outcome"]["status"] == "abstained"
    assert body["envelope"]["outcome"]["reason_code"] == "insufficient_input"
    check_fixture("run-abstained.json", normalised(body))


@pytest.mark.parametrize(
    "body",
    [
        {"input": {}},
        {"agent_id": STANDARDS_AGENT_ID},
        {"agent_id": STANDARDS_AGENT_ID, "input": []},
        [],
    ],
)
def test_a_malformed_body_is_refused_as_a_problem(governance: Governance, dist: Path, body: Any):
    response = TestClient(build_app(governance, dist)).post("/api/runs", json=body)
    assert response.status_code == 400
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"].endswith("/request-refused")


def test_an_unknown_agent_is_refused_before_it_runs(governance: Governance, dist: Path):
    client = TestClient(build_app(governance, dist))
    response = run(client, example("soil-chemistry.profile"), agent_id="no.such-agent")
    assert response.status_code == 400
    assert "no.such-agent" in response.json()["detail"]
    assert client.get("/api/runs").json() == []


def test_an_input_the_agent_does_not_accept_is_a_failed_run(governance: Governance, dist: Path):
    body = run(TestClient(build_app(governance, dist)), {"schema_class": "Claim"}).json()
    assert body["envelope"]["outcome"]["status"] == "failed"
    assert body["envelope"]["problem"]["type"].endswith("/input-not-accepted")
    # The checks run over every envelope; with no output there was nothing for them to find.
    assert body["checks"]["grounding"]["passed"] is True
    assert body["checks"]["sources"]["summary"] == "sources: 0 verified, 0 unresolved"


def test_the_history_lists_runs_newest_first_and_each_reopens(governance: Governance, dist: Path):
    client = TestClient(build_app(governance, dist))
    first = run(client, example("soil-chemistry.profile")).json()["envelope"]
    second = run(client, example("empty.profile")).json()["envelope"]
    rows = client.get("/api/runs").json()
    assert [r["invocation_id"] for r in rows] == [
        second["invocation_id"],
        first["invocation_id"],
    ]
    assert rows[0] == {
        "invocation_id": second["invocation_id"],
        "agent_id": STANDARDS_AGENT_ID,
        "status": "abstained",
        "completed_at": second["completed_at"],
        "acting_for": TEST_PRINCIPAL.name,
    }
    stored = client.get(f"/api/runs/{first['invocation_id']}").json()
    assert stored["envelope"] == first
    assert stored["request"]["agent_id"] == STANDARDS_AGENT_ID
    assert stored["checks"]["grounding"]["passed"] is True


@pytest.mark.parametrize("invocation_id", ["01900000-0000-7000-8000-000000000009", "a.b"])
def test_a_run_that_is_not_stored_is_not_found(
    governance: Governance, dist: Path, invocation_id: str
):
    response = TestClient(build_app(governance, dist)).get(f"/api/runs/{invocation_id}")
    assert response.status_code == 404
    assert response.json()["type"].endswith("/run-not-found")


def test_the_examples_name_their_class(governance: Governance, dist: Path):
    found = TestClient(build_app(governance, dist)).get("/api/examples").json()
    assert [(e["name"], e["schema_class"]) for e in found] == [
        ("director.message", "Message"),
        ("empty.profile", "DatasetProfile"),
        ("hello.salutation", "Salutation"),
        ("orda-record.metadata", "MetadataRecord"),
        ("soil-chemistry.profile", "DatasetProfile"),
    ]
    assert found[4]["input"] == example("soil-chemistry.profile")


# Delegation (#129): the app is the conductor's callback, and its A2A routes take delegation
# callbacks and nothing else.


@pytest.fixture
def delegating(env: Path, dist: Path) -> Iterator[tuple[Governance, Any]]:
    """The app over the orchestrator and `hello.world`, each reached over in-process A2A, with
    the orchestrator calling back to the app's own routes, under the app's reference profile."""
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
        registry=registry, store=RunStore(env), profile=load_profile(DEFAULT_PROFILE)
    )
    conductor.harness_url = APP_URL
    governance = Governance(conductor, TEST_PRINCIPAL, ThreadPoolExecutor(max_workers=1))
    served["app"] = build_app(governance, dist)
    yield governance, served["app"]
    governance.worker.shutdown()


def test_the_orchestrator_delegates_through_the_app(delegating: tuple[Governance, Any]):
    _governance, app = delegating
    response = run(TestClient(app), example("director.message"), agent_id="director.stub")
    assert response.status_code == 200
    envelope = response.json()["envelope"]
    assert envelope["outcome"]["status"] == "succeeded"
    assert [d["delegated_agent_id"] for d in envelope["delegations"]] == ["hello.world"]


def test_the_app_takes_no_a2a_call_but_a_delegation_callback(delegating: tuple[Governance, Any]):
    governance, app = delegating
    card = TestClient(app).get("/.well-known/agent-card.json").json()
    assert card["supportedInterfaces"][0]["url"] == f"{APP_URL}/a2a"
    request = InvocationRequest(agent_id="hello.world", input=example("hello.salutation"))
    task = send_to_harness(app, APP_URL, request)
    assert task.status.state == TaskState.TASK_STATE_FAILED
    assert get_data_parts(task.status.message.parts)[0]["error"] == DELEGATED_ONLY
    assert list(governance.conductor.store.iter_envelopes()) == []


@pytest.fixture
def started(env: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """What `main` built and served, in place of serving it or opening a browser."""
    seen: dict[str, Any] = {}

    def spy_build(governance: Governance) -> str:
        seen["governance"] = governance
        return "app"

    def spy_run(app: Any, *, host: str, port: int) -> None:
        seen.update(host=host, port=port)

    for variable in ("DD_APP_HOST", "DD_APP_PORT", "DD_HARNESS_URL"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(dd_app, "build_app", spy_build)
    monkeypatch.setattr(uvicorn, "run", spy_run)
    monkeypatch.setattr(webbrowser, "open", lambda url: True)
    return seen


def test_the_app_is_its_own_delegation_callback(started: dict[str, Any]):
    assert dd_app.main() == 0
    assert started["governance"].conductor.harness_url == "http://127.0.0.1:7860"


def test_the_configured_url_is_the_callback(
    started: dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setenv("DD_HARNESS_URL", "http://app.internal:7860")
    monkeypatch.setenv("DD_APP_HOST", "0.0.0.0")
    dd_app.main()
    assert started["governance"].conductor.harness_url == "http://app.internal:7860"
    assert "private network only" in capsys.readouterr().err


# Conversations (#130): a turn is one invocation of the orchestrator with a `conversation_id`,
# and the server, not the caller, builds its history from the stored turns (ADR-0024 §17).

UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
SHA256 = re.compile(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])")
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})")
TRACE_ID = re.compile(r'"trace_id": "[0-9a-f]{32}"')


def normalised_conversation(body: Any) -> Any:
    """`body` with each identifier and hash that changes between two runs of the same
    conversation replaced by a fixed one, numbered in order of first appearance, so the same
    value stays the same throughout. A turn's input hash covers the history, which names the
    earlier turns' runs, and a delegation's content hash covers the child's envelope, so the
    hashes change with the identifiers."""
    text = json.dumps(body, sort_keys=True)
    seen: dict[str, str] = {}

    def fixed(template: str) -> Any:
        def replace(match: re.Match[str]) -> str:
            value = match.group(0)
            if value not in seen:
                seen[value] = template.format(len(seen) + 1)
            return seen[value]

        return replace

    text = UUID.sub(fixed("01900000-0000-7000-8000-{:012d}"), text)
    text = SHA256.sub(fixed("{:064d}"), text)
    text = TIMESTAMP.sub(FIXED_TIME, text)
    text = TRACE_ID.sub(f'"trace_id": "{"0" * 32}"', text)
    return json.loads(text)


def start(client: TestClient) -> str:
    response = client.post("/api/conversations")
    assert response.status_code == 201
    conversation_id: str = response.json()["conversation_id"]
    assert response.headers["location"] == f"/api/conversations/{conversation_id}"
    return conversation_id


def turn(client: TestClient, conversation_id: str, text: str, **extra: Any) -> Any:
    return client.post(
        f"/api/conversations/{conversation_id}/turns",
        json={"agent_id": "director.stub", "message_text": text, **extra},
    )


def test_a_conversation_is_started_with_no_turns(governance: Governance, dist: Path):
    client = TestClient(build_app(governance, dist))
    conversation_id = start(client)
    assert re.fullmatch(UUID7_PATTERN, conversation_id)
    found = client.get(f"/api/conversations/{conversation_id}").json()
    assert found["turns"] == [] and found["history"] == []
    # Listed once it has a turn, since the store is what holds a conversation.
    assert client.get("/api/conversations").json() == []


@pytest.mark.parametrize(
    "conversation_id",
    ["01900000-0000-7000-8000-000000000001", "not-an-id", "01900000-0000-4000-8000-000000000001"],
)
def test_a_conversation_the_app_did_not_start_is_not_found(
    governance: Governance, dist: Path, conversation_id: str
):
    client = TestClient(build_app(governance, dist))
    for response in (
        client.get(f"/api/conversations/{conversation_id}"),
        turn(client, conversation_id, "hello world"),
    ):
        assert response.status_code == 404
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["type"].endswith("conversation-not-found")


def test_each_turn_is_shown_the_turns_before_it(delegating: tuple[Governance, Any]):
    governance, app = delegating
    client = TestClient(app)
    conversation_id = start(client)
    first = turn(client, conversation_id, "hello world")
    assert first.status_code == 200
    second = turn(client, conversation_id, "hello again")
    assert second.status_code == 200
    envelopes = [first.json()["envelope"], second.json()["envelope"]]
    for envelope in envelopes:
        assert envelope["conversation_id"] == conversation_id
        assert envelope["outcome"]["status"] == "succeeded"
        assert [d["delegated_agent_id"] for d in envelope["delegations"]] == ["hello.world"]

    store = governance.conductor.store
    shown = [(store.get_request(e["invocation_id"]) or {})["input"] for e in envelopes]
    assert shown[0] == {"schema_class": "Message", "message_text": "hello world", "history": []}
    assert shown[1]["message_text"] == "hello again"
    user, agent = shown[1]["history"]
    assert (user["role"], user["turn_text"]) == ("user", "hello world")
    assert agent["role"] == "agent"
    assert agent["turn_text"] == envelopes[0]["payload"]["reply_text"]
    assert agent["turn_invocation_id"] == envelopes[0]["invocation_id"]

    found = client.get(f"/api/conversations/{conversation_id}").json()
    assert [t["invocation_id"] for t in found["turns"]] == [e["invocation_id"] for e in envelopes]
    for t, envelope in zip(found["turns"], envelopes, strict=True):
        assert [c["invocation_id"] for c in t["children"]] == [
            d["delegated_invocation_id"] for d in envelope["delegations"]
        ]
    (listed,) = client.get("/api/conversations").json()
    assert (listed["conversation_id"], listed["turns"]) == (conversation_id, 2)
    check_fixture("conversation-turn.json", normalised_conversation(second.json()))
    check_fixture("conversation.json", normalised_conversation(found))


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"history": []}, "history"),
        ({"input": {}}, "only `agent_id` and `message_text`"),
        ({"message_text": 3}, "as strings"),
        ({"message_text": "  "}, "empty"),
    ],
)
def test_a_malformed_turn_is_refused_and_nothing_runs(
    delegating: tuple[Governance, Any], body: dict[str, Any], detail: str
):
    governance, app = delegating
    client = TestClient(app)
    conversation_id = start(client)
    response = turn(client, conversation_id, "hello world", **body)
    assert response.status_code == 400
    assert response.headers["content-type"] == "application/problem+json"
    assert detail in response.json()["detail"]
    assert list(governance.conductor.store.iter_envelopes()) == []


def test_a_turn_that_is_not_json_is_refused(governance: Governance, dist: Path):
    client = TestClient(build_app(governance, dist))
    response = client.post(f"/api/conversations/{start(client)}/turns", content=b"{")
    assert response.status_code == 400


def test_a_turn_to_an_unknown_agent_is_refused_before_it_runs(governance: Governance, dist: Path):
    client = TestClient(build_app(governance, dist))
    response = client.post(
        f"/api/conversations/{start(client)}/turns",
        json={"agent_id": "no.such.agent", "message_text": "hello"},
    )
    assert response.status_code == 400
    assert response.json()["type"].endswith("request-refused")
    assert list(governance.conductor.store.iter_envelopes()) == []
