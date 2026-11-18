"""The Data Director app's server: its reference configuration, what `GET /api/agents` tells the
shell, start-up, and the fixture the shell's tests are drawn from.

An alpha substantiates no requirement, so these tests carry no requirement marker.
"""

from __future__ import annotations

import webbrowser
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import pytest
import uvicorn
from a2a.helpers import get_data_parts
from a2a.types import TaskState
from starlette.testclient import TestClient
from support import (
    APP_URL,
    STANDARDS_AGENT_ID,
    check_fixture,
    configure_env,
    delegating_app,
    dist_dir,
    example,
    new_governance,
    run,
    with_standards,
)

from dd_agent_advisor_quality.agent import build as build_quality
from dd_agent_advisor_standards import factory as standards
from dd_agent_example_hello.agent import build as build_hello
from dd_app import app as dd_app
from dd_app.app import ShellNotBuiltError, build_app
from dd_app.config import DEFAULT_AGENTS_CONFIG, DEFAULT_PROFILE, settings_from_env
from dd_app.governance import (
    Governance,
)
from dd_harness.identity import IdentityError, OperatorAssertion
from dd_harness.policy import load_profile
from dd_harness.registry import load_config
from dd_harness.remote import RemoteAgent, RemoteAgentError
from dd_harness.settings import SettingsError
from dd_harness.testing import (
    PERMISSIVE,
    RESTRICTIVE,
    TEST_PRINCIPAL,
    AbstainingStub,
    make_conductor,
    send_to_harness,
)
from dd_harness.transport.a2a import DELEGATED_ONLY
from dd_sdk.agent import Agent
from dd_sdk.contract.models import InvocationRequest
from dd_sdk.process_flow import ENTRIES, PHASES


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    return configure_env(monkeypatch, tmp_path)


@pytest.fixture
def governance(env: Path) -> Iterator[Governance]:
    yield from new_governance()


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    return dist_dir(tmp_path)


@pytest.fixture
def delegating(env: Path, dist: Path) -> Iterator[tuple[Governance, Any]]:
    """The app over the orchestrator and `example.hello`, each reached over in-process A2A, with
    the orchestrator calling back to the app's own routes, under the app's reference profile. It
    keeps no projects."""
    yield delegating_app(env, dist, None)


# The fixtures (`support.check_fixture`): `agents.json` is the reference set;
# `agents-several.json` is five agents of different grounding modes and payload shapes under the
# permissive test profile, which does not list the standards advisor.


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
    # scripts/check_members.py checks that the list names every in-tree agent; here, that each
    # has a port of its own on this machine and that the reference profile enables each one.
    entries = load_config(DEFAULT_AGENTS_CONFIG)
    names = [e["name"] for e in entries]
    urls = [urlsplit(e["url"]) for e in entries]
    assert {"example-hello", "orchestrator-stub"} <= set(names)
    assert len(set(names)) == len(names)
    assert {url.hostname for url in urls} == {"127.0.0.1"}
    assert len({url.port for url in urls}) == len(urls)
    # An agent id is its directory's name with the first hyphen a dot (agents/README.md).
    enabled = [name.replace("-", ".", 1) for name in names]
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
    assert body["profile"]["ref"] == "profile:data-director-app@v9"
    assert body["profile"]["orchestrator"] == "orchestrator.stub"
    assert body["profile"]["attached_documents"] == "allowed"
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
        "prompt": PHASES[0].steps[1].prompt,
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


# Delegation (#129): the app is the conductor's callback, and its A2A routes take delegation
# callbacks and nothing else.


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
