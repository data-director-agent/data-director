"""The Data Director app's server: its reference configuration, what `GET /api/agents` tells the
shell, start-up, and the fixture the shell's tests are drawn from.

An alpha substantiates no requirement, so these tests carry no requirement marker.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from dd_agent_factcheck.agent import build as build_factcheck
from dd_agent_hello.agent import build as build_hello
from dd_agent_quality.agent import build as build_quality
from dd_agent_r3 import factory as r3
from dd_agent_stub.agent import build as build_stub
from dd_app.app import ShellNotBuiltError, build_app
from dd_app.config import settings_from_env
from dd_app.governance import R3_AGENT_ID, Governance
from dd_harness.identity import IdentityError
from dd_harness.testing import PERMISSIVE, RESTRICTIVE, TEST_PRINCIPAL, make_conductor
from dd_sdk.agent import Agent

PATH_VARIABLES = ("DD_PROFILE", "DD_AGENTS_CONFIG", "DD_SOURCES_CONFIG")
# The shell's component and browser tests are drawn from these, so each must be what the server
# says. `DD_WRITE_FIXTURES=1 uv run pytest app/tests` rewrites them. `agents.json` is the
# reference set; `agents-several.json` is five agents of different grounding modes and payload
# shapes under the permissive test profile, which does not list R3.
FIXTURES = Path(__file__).resolve().parents[1] / "web/fixtures"


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """The app's reference set, a principal, and runs written under `tmp_path`."""
    for variable in PATH_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    for variable in ("DD_R3_RETRIEVAL", "DD_R3_EXPLAINER", "DD_SNAPSHOT_PATH"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("DD_PRINCIPAL_ID", TEST_PRINCIPAL.principal_id)
    monkeypatch.setenv("DD_PRINCIPAL_NAME", TEST_PRINCIPAL.name)
    monkeypatch.setenv("DD_RUNS_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def governance(env: Path) -> Iterator[Governance]:
    governance = Governance.create(settings_from_env())
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


def test_the_reference_set_registers_r3_alone(governance: Governance):
    conductor = governance.conductor
    assert conductor.registry.ids() == [R3_AGENT_ID]
    assert conductor.profile.profile_id == "data-director-app"
    assert governance.acting_for == TEST_PRINCIPAL


def test_api_agents_gives_each_manifest_beside_what_the_profile_assigns(
    governance: Governance, dist: Path
):
    body = agents_response(governance, dist)
    (r3,) = body["agents"]
    assert r3["agent_id"] == R3_AGENT_ID
    assert r3["action_class"] == "advise"  # what the card declares
    assert r3["assigned_action_class"] == "advise"  # what the steward assigns
    assert r3["requires_approval"] is False
    assert r3["grounding_mode"] == "retrieval"
    assert body["unavailable"] == {} and body["incompatible"] == {}
    assert body["profile"]["ref"] == "profile:data-director-app@v1"
    assert body["acting_for"] == {"name": TEST_PRINCIPAL.name, "assurance": "asserted"}


def test_an_agent_the_profile_does_not_list_is_shown_unassigned(
    env: Path, dist: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("DD_PROFILE", str(RESTRICTIVE))
    governance = Governance.create(settings_from_env())
    try:
        (r3,) = agents_response(governance, dist)["agents"]
    finally:
        governance.worker.shutdown()
    assert r3["assigned_action_class"] is None
    assert r3["requires_approval"] is False


def test_every_other_path_serves_the_built_shell(governance: Governance, dist: Path):
    response = TestClient(build_app(governance, dist)).get("/")
    assert response.status_code == 200
    assert "<title>shell</title>" in response.text


def test_an_unbuilt_shell_stops_start_up(governance: Governance, tmp_path: Path):
    with pytest.raises(ShellNotBuiltError, match="npm ci && npm run build"):
        build_app(governance, tmp_path / "missing")


def test_no_principal_stops_start_up(env: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DD_PRINCIPAL_ID")
    with pytest.raises(IdentityError, match="DD_PRINCIPAL_ID"):
        Governance.create(settings_from_env())


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
        build_factcheck(),
        build_stub(),
        r3.build(),
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
