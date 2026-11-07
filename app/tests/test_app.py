"""The Data Director app's server: its reference configuration, what `GET /api/agents` tells the
shell, start-up, and the fixture the shell's tests are drawn from.

An alpha substantiates no requirement, so these tests carry no requirement marker.
"""

from __future__ import annotations

import asyncio
import json
import re
import threading
import uuid
import webbrowser
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from a2a.helpers import get_data_parts
from a2a.types import TaskState
from starlette.testclient import TestClient
from support import (
    APP_URL,
    check_fixture,
    configure_env,
    dist_dir,
    new_governance,
    with_standards,
)

from dd_agent_advisor_quality.agent import build as build_quality
from dd_agent_advisor_standards import factory as standards
from dd_agent_example_hello.agent import build as build_hello
from dd_agent_orchestrator_stub.agent import build as build_director
from dd_app import app as dd_app
from dd_app.app import ShellNotBuiltError, build_app
from dd_app.config import DEFAULT_AGENTS_CONFIG, DEFAULT_PROFILE, settings_from_env
from dd_app.governance import INVENTORY_ONLY_TEXT, Governance, TurnConflictError
from dd_harness.conductor import Conductor
from dd_harness.identity import IdentityError, OperatorAssertion
from dd_harness.policy import load_profile
from dd_harness.projects import ProjectStore
from dd_harness.registry import Registry, load_config
from dd_harness.remote import RemoteAgent, RemoteAgentError
from dd_harness.settings import SettingsError
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
from dd_sdk.contract.models import UUID7_PATTERN, InvocationRequest, Principal
from dd_sdk.process_flow import ENTRIES, PHASES

# The fixtures (`support.check_fixture`): `agents.json` is the reference set;
# `agents-several.json` is five agents of different grounding modes and payload shapes under the
# permissive test profile, which does not list the standards advisor.
STANDARDS_AGENT_ID = "advisor.standards"


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    return configure_env(monkeypatch, tmp_path)


@pytest.fixture
def governance(env: Path) -> Iterator[Governance]:
    yield from new_governance()


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    return dist_dir(tmp_path)


def agents_response(governance: Governance, dist: Path) -> dict[str, Any]:
    response = TestClient(build_app(governance, dist)).get("/api/agents")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def test_api_agents_retries_an_agent_that_was_down_and_still_reports_it(
    governance: Governance, dist: Path, tmp_path: Path
):
    def refused(url: str, timeout_s: float) -> httpx.AsyncClient:
        raise httpx.ConnectError("refused")

    config = tmp_path / "down.yaml"
    config.write_text("agents:\n  - name: down\n    url: http://127.0.0.1:9\n", encoding="utf-8")
    registry = governance.conductor.registry
    registry.config = config
    registry.client_factory = refused
    registry.unavailable["down"] = "not started"
    body = agents_response(governance, dist)
    assert "cannot read the agent card" in body["unavailable"]["down"]


def test_the_reference_set_lists_and_enables_every_in_tree_agent():
    entries = load_config(DEFAULT_AGENTS_CONFIG)
    assert [(e["name"], e["url"]) for e in entries] == [
        ("example-hello", "http://127.0.0.1:8101"),
        ("advisor-quality", "http://127.0.0.1:8102"),
        ("advisor-standards", "http://127.0.0.1:8105"),
        ("advisor-policy", "http://127.0.0.1:8108"),
        ("advisor-repository", "http://127.0.0.1:8109"),
        ("advisor-ethics", "http://127.0.0.1:8111"),
        ("advisor-files", "http://127.0.0.1:8110"),
        ("advisor-dmp", "http://127.0.0.1:8112"),
        ("advisor-metadata", "http://127.0.0.1:8113"),
        ("advisor-documentation", "http://127.0.0.1:8114"),
        ("advisor-rights", "http://127.0.0.1:8115"),
        ("advisor-linking", "http://127.0.0.1:8116"),
        ("advisor-fairness", "http://127.0.0.1:8117"),
        ("orchestrator-stub", "http://127.0.0.1:8106"),
        ("orchestrator-model", "http://127.0.0.1:8107"),
    ]
    enabled = (
        STANDARDS_AGENT_ID,
        "advisor.policy",
        "advisor.repository",
        "example.hello",
        "advisor.quality",
        "advisor.ethics",
        "advisor.files",
        "advisor.dmp",
        "advisor.metadata",
        "advisor.documentation",
        "advisor.rights",
        "advisor.linking",
        "advisor.fairness",
        "orchestrator.stub",
        "orchestrator.model",
    )
    profile = load_profile(DEFAULT_PROFILE)
    assert profile.agents == dict.fromkeys(enabled, "advise")
    # The rule-based stub, which needs no model key, is the conversation until a deployment
    # names another (docs/specs/app.md).
    assert profile.orchestrator == "orchestrator.stub"


def test_the_app_runs_no_agent_its_list_does_not_name(env: Path):
    # Every agent is a service (docs/specs/app.md): with none listed, the app has none to run.
    governance = Governance.create(settings_from_env(), APP_URL)
    assert governance.conductor.registry.ids() == []
    assert governance.conductor.profile.profile_id == "data-director-app"
    # A development server: every request acts for the operator's assertion
    # (docs/specs/policy-and-identity.md).
    assert governance.authenticator.principal_for({}) == TEST_PRINCIPAL


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
    assert body["profile"]["ref"] == "profile:data-director-app@v7"
    assert body["profile"]["orchestrator"] == "orchestrator.stub"
    assert body["acting_for"] == {"name": TEST_PRINCIPAL.name, "assurance": "asserted"}


def test_an_agent_the_profile_does_not_list_is_shown_unassigned(
    env: Path, dist: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("DD_PROFILE", str(RESTRICTIVE))
    governance = with_standards(Governance.create(settings_from_env(), APP_URL))
    (standards,) = agents_response(governance, dist)["agents"]
    assert standards["assigned_action_class"] is None
    assert standards["requires_approval"] is False


def test_every_other_path_serves_the_built_shell(governance: Governance, dist: Path):
    response = TestClient(build_app(governance, dist)).get("/")
    assert response.status_code == 200
    assert "<title>shell</title>" in response.text


@pytest.mark.parametrize("page", ["/agents", "/activity", "/policy"])
def test_each_page_serves_the_built_shell(governance: Governance, dist: Path, page: str):
    response = TestClient(build_app(governance, dist)).get(page)
    assert response.status_code == 200
    assert "<title>shell</title>" in response.text


def test_api_policy_gives_the_profile_the_gate_holds_runs_to(governance: Governance, dist: Path):
    response = TestClient(build_app(governance, dist)).get("/api/policy")
    assert response.status_code == 200
    body = response.json()
    profile = governance.conductor.profile
    assert body["profile"]["ref"] == profile.ref
    assert body["profile"]["digest"] == profile.digest
    assert body["profile"]["description"] == profile.description != ""
    assert body["profile"]["orchestrator"] == "orchestrator.stub"
    assert {a["agent_id"]: a["action_class"] for a in body["agents"]} == profile.agents
    assert body["actions_requiring_approval"] == sorted(profile.actions_requiring_approval)
    for agent in body["agents"]:
        assert agent["requires_approval"] is (
            agent["action_class"] in profile.actions_requiring_approval
        )
    check_fixture("policy.json", body)


def test_an_unbuilt_shell_stops_start_up(governance: Governance, tmp_path: Path):
    with pytest.raises(ShellNotBuiltError, match="npm ci && npm run build"):
        build_app(governance, tmp_path / "missing")


def test_no_principal_stops_start_up(env: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DD_PRINCIPAL_ID")
    with pytest.raises(IdentityError, match="DD_PRINCIPAL_ID"):
        Governance.create(settings_from_env(), APP_URL)


def test_a_projects_directory_that_cannot_be_made_stops_start_up(
    env: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    # A SettingsError, which `main` turns into one line, not a traceback.
    blocker = tmp_path / "a-file"
    blocker.write_text("")
    monkeypatch.setenv("DD_PROJECTS_DIR", str(blocker / "projects"))
    with pytest.raises(SettingsError, match=r"DD_PROJECTS_DIR .* cannot be used"):
        Governance.create(settings_from_env(), APP_URL)


def test_a_listed_agent_that_is_not_running_is_shown_unavailable(
    env: Path, monkeypatch: pytest.MonkeyPatch
):
    # The app does not quietly run its own copy in its place.
    agents = env / "with-standards.yaml"
    agents.write_text("agents:\n  - name: advisor-standards\n    url: http://127.0.0.1:9\n")
    monkeypatch.setenv("DD_AGENTS_CONFIG", str(agents))

    def unreachable(url: str, **_: Any) -> RemoteAgent:
        raise RemoteAgentError(f"{url}: connection refused")

    monkeypatch.setattr(RemoteAgent, "from_url", unreachable)
    governance = Governance.create(settings_from_env(), APP_URL)
    assert governance.conductor.registry.ids() == []
    assert "advisor-standards" in governance.conductor.registry.unavailable


def test_the_reference_fixture_is_what_the_server_says(governance: Governance, dist: Path):
    check_fixture("agents.json", agents_response(governance, dist))


def test_the_process_flow_is_the_blueprints(governance: Governance, dist: Path):
    response = TestClient(build_app(governance, dist)).get("/api/process-flow")
    assert response.status_code == 200
    body = response.json()
    assert [p["number"] for p in body["phases"]] == [p.number for p in PHASES]
    assert [e["starts_at"] for e in body["entries"]] == [e.starts_at for e in ENTRIES]
    assert body["phases"][0]["steps"][1] == {
        "id": "setup.vocabularies",
        "text": "Select controlled vocabularies and ontologies",
        "label": "Choose standard terms to describe your data",
        "requirements": ["R3"],
        "optional": False,
        "out_of_scope": False,
    }
    check_fixture("process-flow.json", body)


def test_the_several_agents_fixture_is_what_the_server_says(env: Path, dist: Path):
    agents: list[Agent] = [
        build_hello(),
        build_quality(),
        AbstainingStub(),
        standards.build(),
    ]
    governance = Governance(
        make_conductor(env, *agents, remote=False, profile=PERMISSIVE),
        OperatorAssertion(TEST_PRINCIPAL),
    )
    check_fixture("agents-several.json", agents_response(governance, dist))


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
    """The app over the orchestrator and `example.hello`, each reached over in-process A2A, with
    the orchestrator calling back to the app's own routes, under the app's reference profile. It
    keeps no projects."""
    yield delegating_app(env, dist, None)


@pytest.fixture
def in_projects(env: Path, dist: Path) -> Iterator[tuple[Governance, Any]]:
    """As `delegating`, with each conversation started in a project of its own."""
    yield delegating_app(env, dist, ProjectStore(env / "projects"))


def delegating_app(env: Path, dist: Path, projects: ProjectStore | None) -> tuple[Governance, Any]:
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
    governance = Governance(conductor, OperatorAssertion(TEST_PRINCIPAL), projects)
    served["app"] = build_app(governance, dist)
    return governance, served["app"]


def test_the_orchestrator_delegates_through_the_app(delegating: tuple[Governance, Any]):
    _governance, app = delegating
    response = run(TestClient(app), example("director.message"), agent_id="orchestrator.stub")
    assert response.status_code == 200
    envelope = response.json()["envelope"]
    assert envelope["outcome"]["status"] == "succeeded"
    assert [d["delegated_agent_id"] for d in envelope["delegations"]] == ["example.hello"]


def test_the_app_takes_no_a2a_call_but_a_delegation_callback(delegating: tuple[Governance, Any]):
    governance, app = delegating
    card = TestClient(app).get("/.well-known/agent-card.json").json()
    assert card["supportedInterfaces"][0]["url"] == f"{APP_URL}/a2a"
    request = InvocationRequest(agent_id="example.hello", input=example("hello.salutation"))
    task = send_to_harness(app, APP_URL, request)
    assert task.status.state == TaskState.TASK_STATE_FAILED
    assert get_data_parts(task.status.message.parts)[0]["error"] == DELEGATED_ONLY
    assert list(governance.conductor.store.iter_envelopes()) == []


@pytest.fixture
def started(env: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """What `main` built and served, in place of serving it or opening a browser."""
    seen: dict[str, Any] = {}

    def spy_build(governance: Governance, **settings: Any) -> str:
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
# and the server, not the caller, builds its history from the stored turns (docs/specs/app.md).

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


def turn(
    client: TestClient,
    conversation_id: str,
    text: str,
    follows: str | None = None,
    **extra: Any,
) -> Any:
    return client.post(
        f"/api/conversations/{conversation_id}/turns",
        json={"agent_id": "orchestrator.stub", "message_text": text, "follows": follows, **extra},
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


def test_each_turn_is_shown_the_turns_before_it(in_projects: tuple[Governance, Any]):
    governance, app = in_projects
    client = TestClient(app)
    conversation_id = start(client)
    first = turn(client, conversation_id, "hello world")
    assert first.status_code == 200
    second = turn(client, conversation_id, "hello again", first.json()["envelope"]["invocation_id"])
    assert second.status_code == 200
    envelopes = [first.json()["envelope"], second.json()["envelope"]]
    for envelope in envelopes:
        assert envelope["conversation_id"] == conversation_id
        assert envelope["outcome"]["status"] == "succeeded"
        assert [d["delegated_agent_id"] for d in envelope["delegations"]] == ["example.hello"]

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
    # orchestrator.stub writes no title, so the conversation is named by its first message.
    assert (listed["title"], listed["title_source"]) == ("hello world", "message")
    assert listed["project_id"] == found["project_id"]
    check_fixture("conversation-turn.json", normalised_conversation(second.json()))
    check_fixture("conversation.json", normalised_conversation(found))


@pytest.mark.requirement("DD-CONVERSATION")
def test_a_choice_question_is_answered_by_choosing(in_projects: tuple[Governance, Any]):
    governance, app = in_projects
    client = TestClient(app)
    conversation_id = start(client)
    first = turn(client, conversation_id, "hi")
    assert first.status_code == 200
    asked = first.json()["envelope"]
    question = asked["payload"]["reply_question"]
    assert [o["option_value"] for o in question["question_options"]] == ["1", "2", "3"]
    check_fixture(
        "conversation-question.json",
        normalised_conversation(client.get(f"/api/conversations/{conversation_id}").json()),
    )

    def answer(values: list[str], to: str = asked["invocation_id"], **kw: Any) -> Any:
        return turn(
            client,
            conversation_id,
            "Data already collected, being prepared for sharing",
            asked["invocation_id"],
            choice_answer={"answer_to": to, "answer_values": values, **kw},
        )

    refused = answer(["9"])
    assert refused.status_code == 400
    assert "not an option of the question: 9" in refused.json()["detail"]
    assert answer(["1", "2"]).status_code == 400  # one answer only
    assert answer(["2"], answer_other="ours").status_code == 400  # no answer in words
    from_elsewhere = answer(["2"], to="0190a000-0000-7000-8000-000000000000")
    assert "latest turn" in from_elsewhere.json()["detail"]
    assert answer(["2"], answer_to_typo=True).status_code == 400  # not a ChoiceAnswer
    assert len(client.get(f"/api/conversations/{conversation_id}").json()["turns"]) == 1

    answered = answer(["2"])
    assert answered.status_code == 200, answered.json()
    envelope = answered.json()["envelope"]
    stored = governance.conductor.store.get_request(envelope["invocation_id"]) or {}
    assert stored["input"]["choice_answer"] == {
        "answer_to": asked["invocation_id"],
        "answer_values": ["2"],
    }
    assert envelope["outcome"]["statement"].startswith("Listed the steps from entry point 2")
    # The answer reads as a normal message in the history; the question is written after the
    # reply that asked it.
    found = client.get(f"/api/conversations/{conversation_id}").json()
    _, agent, again, _ = found["history"]
    assert agent["turn_text"].endswith("(The researcher was offered these to choose one.)")
    assert again["turn_text"] == "Data already collected, being prepared for sharing"
    check_fixture("conversation-answered.json", normalised_conversation(found))


def a_file_inventory(*paths: str) -> dict[str, Any]:
    """What `dd-inventory` writes for files at `paths`."""
    return {
        "schema_class": "FileInventory",
        "inventory_tool": "dd-inventory",
        "inventory_tool_version": "0.1.0",
        "inventory_made_at": "2026-11-01T09:00:00Z",
        "inventory_files": [
            {
                "file_path": path,
                "file_size": 10,
                "file_sha256": "a" * 64,
                "file_media_type": "text/csv",
                "file_identified_by": "extension",
            }
            for path in paths
        ],
    }


def test_a_conversation_is_started_in_a_project_of_its_own(governance: Governance, dist: Path):
    client = TestClient(build_app(governance, dist))
    first, second = (client.post("/api/conversations").json() for _ in range(2))
    assert first["project_id"] != second["project_id"]
    store = governance.projects
    assert store is not None
    for started in (first, second):
        assert store.project_of(started["conversation_id"]) == started["project_id"]
        events = store.events(started["project_id"])
        assert [e["event"] for e in events] == ["project_created", "conversation_started"]
        assert {e["acted_for"]["principal_id"] for e in events} == {TEST_PRINCIPAL.principal_id}
        found = client.get(f"/api/conversations/{started['conversation_id']}").json()
        assert (found["project_id"], found["inventory"]) == (started["project_id"], None)


def test_a_conversation_is_started_in_the_project_it_names(governance: Governance, dist: Path):
    client = TestClient(build_app(governance, dist))
    first = client.post("/api/conversations").json()
    response = client.post("/api/conversations", json={"project_id": first["project_id"]})
    assert response.status_code == 201
    second = response.json()
    assert second["project_id"] == first["project_id"]
    assert second["conversation_id"] != first["conversation_id"]
    store = governance.projects
    assert store is not None
    assert store.project_of(second["conversation_id"]) == first["project_id"]
    events = store.events(first["project_id"])
    assert [e["event"] for e in events] == [
        "project_created",
        "conversation_started",
        "conversation_started",
    ]
    # A null project is a new one, as no body is.
    other = client.post("/api/conversations", json={"project_id": None}).json()
    assert other["project_id"] != first["project_id"]


def test_a_conversation_is_not_started_in_a_project_the_person_may_not_read(
    governance: Governance, dist: Path
):
    client = TestClient(build_app(governance, dist))
    store = governance.projects
    assert store is not None
    someone = Principal(principal_id="https://orcid.org/0000-0002-1694-233X", name="Someone Else")
    theirs = store.create(acted_for=someone, caused_by="test")
    for project_id in (theirs, str(uuid.uuid4()), "../../etc"):
        response = client.post("/api/conversations", json={"project_id": project_id})
        assert response.status_code == 404
        assert response.json()["type"].endswith("project-not-found")
    assert [e["event"] for e in store.events(theirs)] == ["project_created"]


@pytest.mark.parametrize(
    "body",
    [{"project_id": 7}, {"project_id": None, "title": "x"}, ["a"]],
)
def test_a_conversation_start_with_a_malformed_body_is_refused(
    governance: Governance, dist: Path, body: Any
):
    client = TestClient(build_app(governance, dist))
    response = client.post("/api/conversations", json=body)
    assert response.status_code == 400
    assert response.headers["content-type"] == "application/problem+json"


def test_an_attached_inventory_is_kept_and_the_orchestrator_is_told_of_it(
    in_projects: tuple[Governance, Any],
):
    governance, app = in_projects
    client = TestClient(app)
    conversation_id = start(client)
    # An inventory may be sent with no words.
    first = turn(client, conversation_id, " ", inventory=a_file_inventory("a.csv", "b.csv"))
    assert first.status_code == 200, first.json()
    envelope = first.json()["envelope"]
    project_id = envelope["project_id"]
    store = governance.projects
    assert store is not None
    added = store.events(project_id)[-1]
    assert added["event"] == "inventory_added"
    assert added["caused_by"] == f"POST /api/conversations/{conversation_id}/turns"

    shown = (governance.conductor.store.get_request(envelope["invocation_id"]) or {})["input"]
    assert shown["message_text"] == INVENTORY_ONLY_TEXT
    assert shown["project_inventory"]["inventory_digest"] == added["digest"]
    assert shown["project_inventory"]["inventory_file_count"] == 2

    # Later turns are told of it too, without sending it again.
    second = turn(client, conversation_id, "Draft a README", envelope["invocation_id"])
    later = governance.conductor.store.get_request(second.json()["envelope"]["invocation_id"])
    assert later is not None
    assert later["input"]["project_inventory"] == shown["project_inventory"]
    found = client.get(f"/api/conversations/{conversation_id}").json()
    assert found["inventory"]["file_count"] == 2
    assert found["inventory"]["digest"] == added["digest"]

    # The whole inventory is served for the researcher to read (the shell's inventory dialog).
    kept = client.get(f"/api/projects/{project_id}/inventory")
    assert kept.status_code == 200
    assert [f["file_path"] for f in kept.json()["inventory_files"]] == ["a.csv", "b.csv"]


def test_a_project_without_an_inventory_serves_none(in_projects: tuple[Governance, Any]):
    _governance, app = in_projects
    client = TestClient(app)
    started = client.post("/api/conversations").json()
    none = client.get(f"/api/projects/{started['project_id']}/inventory")
    assert (none.status_code, none.json()["title"]) == (404, "No inventory")
    unknown = client.get(f"/api/projects/{uuid.uuid4()}/inventory")
    assert (unknown.status_code, unknown.json()["title"]) == (404, "No such project")
    assert client.get("/api/projects/..%2F..%2Fetc/inventory").status_code == 404


@pytest.mark.parametrize(
    ("inventory", "detail"),
    [
        ({"schema_class": "FileInventory"}, "not a FileInventory"),
        (["a.csv"], "`inventory` must be"),
    ],
)
def test_an_inventory_that_is_refused_leaves_no_trace_and_nothing_runs(
    in_projects: tuple[Governance, Any], inventory: Any, detail: str
):
    governance, app = in_projects
    client = TestClient(app)
    started = client.post("/api/conversations").json()
    response = turn(client, started["conversation_id"], "hello", inventory=inventory)
    assert response.status_code == 400
    assert detail in response.json()["detail"]
    assert list(governance.conductor.store.iter_envelopes()) == []
    assert governance.projects is not None
    assert governance.projects.summary(started["project_id"])["inventory"] is None


def test_a_person_sees_the_projects_they_started_with_what_each_holds(
    in_projects: tuple[Governance, Any],
):
    governance, app = in_projects
    client = TestClient(app)
    conversation_id = start(client)
    first = turn(client, conversation_id, "My logger data", inventory=a_file_inventory("a.csv"))
    assert first.status_code == 200, first.json()
    project_id = first.json()["envelope"]["project_id"]
    start(client)  # A project with nothing in it yet is not listed.
    store = governance.projects
    assert store is not None
    # Someone else's project, which holds an inventory, is not theirs to read (#389).
    someone = Principal(principal_id="https://orcid.org/0000-0002-1694-233X", name="Someone Else")
    theirs = store.create(acted_for=someone, caused_by="test")
    store.add_inventory(theirs, a_file_inventory("b.csv"), acted_for=someone, caused_by="test")

    response = client.get("/api/projects")
    assert response.status_code == 200
    (listed,) = response.json()
    assert listed["project_id"] == project_id
    assert listed["created_by"]["principal_id"] == TEST_PRINCIPAL.principal_id
    assert listed["inventory"]["file_count"] == 1
    assert listed["documents"] == {"proposed": 0, "approved": 0, "rejected": 0}
    # The app starts projects untitled, so the shell names one by its conversations.
    assert listed["title"] is None
    (conversation,) = listed["conversations"]
    assert (conversation["conversation_id"], conversation["title"]) == (
        conversation_id,
        "My logger data",
    )
    check_fixture("projects.json", normalised_conversation(response.json()))


def test_the_projects_page_is_served_and_lists_nothing_without_projects(
    delegating: tuple[Governance, Any],
):
    _governance, app = delegating
    client = TestClient(app)
    assert client.get("/api/projects").json() == []
    page = client.get("/projects")
    assert page.status_code == 200
    assert "<title>shell</title>" in page.text


def test_an_inventory_needs_a_project_to_keep_it(delegating: tuple[Governance, Any]):
    governance, app = delegating
    client = TestClient(app)
    response = turn(client, start(client), "hello", inventory=a_file_inventory("a.csv"))
    assert response.status_code == 400
    assert "no project" in response.json()["detail"]
    assert list(governance.conductor.store.iter_envelopes()) == []


def test_a_cancelled_turn_still_comes_before_the_next(delegating: tuple[Governance, Any]):
    """A turn cancelled (the client went away) runs on to the end in the conductor's thread. A
    message sent again meanwhile is refused, not run twice (#337); once the first is stored, a
    turn that follows it runs and is shown it."""
    governance, _app = delegating
    conductor = governance.conductor
    entered, release = threading.Event(), threading.Event()
    invoke = conductor.invoke

    def held_first(request: InvocationRequest, **kwargs: Any) -> Any:
        if not entered.is_set():
            entered.set()
            release.wait(timeout=30)
        return invoke(request, **kwargs)

    conductor.invoke = held_first  # type: ignore[method-assign]
    conversation_id = governance.start_conversation(TEST_PRINCIPAL)

    def top_level_turns() -> list[dict[str, Any]]:
        return [e for e in conductor.store.iter_envelopes() if not e.get("parent_invocation_id")]

    async def scenario() -> dict[str, Any]:
        first = asyncio.create_task(
            governance.turn(
                conversation_id, "orchestrator.stub", "hello world", None, TEST_PRINCIPAL
            )
        )
        await asyncio.to_thread(entered.wait, 30)
        first.cancel()
        with pytest.raises(TurnConflictError, match="still running"):
            await governance.turn(
                conversation_id, "orchestrator.stub", "hello world", None, TEST_PRINCIPAL
            )
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await first
        (stored,) = top_level_turns()
        return await governance.turn(
            conversation_id,
            "orchestrator.stub",
            "hello again",
            stored["invocation_id"],
            TEST_PRINCIPAL,
        )

    try:
        second = asyncio.run(scenario())
    finally:
        release.set()
        conductor.close()

    shown = (conductor.store.get_request(second["envelope"]["invocation_id"]) or {})["input"]
    user, _agent = shown["history"]
    assert user["turn_text"] == "hello world"
    assert len(top_level_turns()) == 2  # the resend never ran
    assert governance._turn_locks == {}  # nothing kept for a conversation with no turn running


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"history": []}, "history"),
        (
            {"input": {}},
            "only `agent_id`, `message_text`, `follows`, `inventory` and `choice_answer`",
        ),
        ({"message_text": 3}, "as strings"),
        ({"follows": 3}, "must give `follows`"),
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


def test_a_turn_must_name_the_turn_it_follows(delegating: tuple[Governance, Any]):
    governance, app = delegating
    client = TestClient(app)
    response = client.post(
        f"/api/conversations/{start(client)}/turns",
        json={"agent_id": "orchestrator.stub", "message_text": "hello world"},
    )
    assert response.status_code == 400
    assert "must give `follows`" in response.json()["detail"]
    assert list(governance.conductor.store.iter_envelopes()) == []


@pytest.mark.parametrize("follows", [None, "01900000-0000-7000-8000-000000000001"])
def test_a_turn_that_does_not_follow_the_latest_is_refused_and_nothing_runs(
    delegating: tuple[Governance, Any], follows: str | None
):
    """A message sent again after its first attempt was stored names the turn before it, so it
    is refused rather than run twice (#337, docs/specs/orchestration.md)."""
    governance, app = delegating
    client = TestClient(app)
    conversation_id = start(client)
    assert turn(client, conversation_id, "hello world").status_code == 200
    stored = list(governance.conductor.store.iter_envelopes())
    response = turn(client, conversation_id, "hello world", follows)
    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"].endswith("turn-conflict")
    assert stored[-1]["invocation_id"] in response.json()["detail"]
    assert list(governance.conductor.store.iter_envelopes()) == stored


def test_a_turn_goes_only_to_the_orchestrator_the_profile_names(
    delegating: tuple[Governance, Any],
):
    governance, app = delegating
    client = TestClient(app)
    response = turn(client, start(client), "hello world", agent_id="example.hello")
    assert response.status_code == 400
    assert "'orchestrator.stub', not 'example.hello'" in response.json()["detail"]
    assert list(governance.conductor.store.iter_envelopes()) == []


def test_a_turn_that_is_not_json_is_refused(governance: Governance, dist: Path):
    client = TestClient(build_app(governance, dist))
    response = client.post(f"/api/conversations/{start(client)}/turns", content=b"{")
    assert response.status_code == 400


def test_a_turn_to_an_unknown_agent_is_refused_before_it_runs(governance: Governance, dist: Path):
    client = TestClient(build_app(governance, dist))
    response = client.post(
        f"/api/conversations/{start(client)}/turns",
        json={"agent_id": "no.such.agent", "message_text": "hello", "follows": None},
    )
    assert response.status_code == 400
    assert response.json()["type"].endswith("request-refused")
    assert list(governance.conductor.store.iter_envelopes()) == []
