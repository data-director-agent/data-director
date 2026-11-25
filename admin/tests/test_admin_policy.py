"""The admin service's Policy page (docs/guide/operations/admin.md): the institutional profile as
the harness parses it, the agents it allows against the roster and `deployment.yaml`, and a profile
the harness would refuse, which is reported and not guessed at."""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from dd_admin import policy_view
from dd_admin.agents import Agents, AgentState
from dd_admin.app import Admin, build_app
from dd_admin.settings import AdminSettings
from dd_admin.system import System

STEWARD = "https://orcid.org/0000-0002-1825-0097"
ADMIN = "https://orcid.org/0000-0001-5000-0007"
BLOCKED = "https://orcid.org/0000-0003-1415-9269"

PROFILE = f"""
profile_id: test-institution
version: 3
description: A test profile.
agents:
  advisor.standards: advise
  advisor.policy: write
  orchestrator.stub: advise
orchestrator: orchestrator.stub
actions_requiring_approval: [write]
hosted_models: [inventory]
tool_servers:
  advisor.standards: [pid]
administrators:
  - {ADMIN}
access:
  admit: listed
  block:
    - {BLOCKED}
stewardship:
  reroute_after: P3D
  teams:
    - id: library-rdm
      name: Library Research Data Team
      members:
        - {STEWARD}
      supports: [faculty-of-science]
      response_time: 3 working days
"""


def card(name: str, state: str = "up") -> AgentState:
    return AgentState(name, f"http://127.0.0.1:81/{name}", state)


def etc_with(tmp_path: Path, profile: str = PROFILE, deployment: str = "") -> Path:
    (tmp_path / "profile.yaml").write_text(profile)
    if deployment:
        (tmp_path / "deployment.yaml").write_text(deployment)
    return tmp_path


def client(etc: Path | None, about: object = None) -> TestClient:
    class Fake(System):
        def get_json(self, url: str, headers: object = None) -> object | None:
            return about if url.endswith("/api/about") else None

    admin = Admin.open(AdminSettings(etc=etc), Fake())
    return TestClient(build_app(admin), base_url="http://localhost:8200")


# --- The page ------------------------------------------------------------------------------------


def test_the_page_answers_get_and_nothing_that_could_change_state(tmp_path: Path) -> None:
    http = client(etc_with(tmp_path))
    assert http.get("/policy").status_code == 200
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert http.request(method, "/policy").status_code == 405


def test_it_shows_what_the_harness_parsed(tmp_path: Path) -> None:
    page = client(etc_with(tmp_path)).get("/policy").text.split("<main", 1)[1]
    for shown in (
        "test-institution",
        "advisor.policy",
        "Library Research Data Team",
        "faculty-of-science",
        ADMIN,
        BLOCKED,
        "pid",
    ):
        assert shown in page


def test_without_a_directory_it_names_the_setting() -> None:
    page = client(None).get("/policy").text
    assert "DD_ADMIN_ETC" in page


def test_a_profile_the_harness_refuses_is_reported_not_shown(tmp_path: Path) -> None:
    http = client(etc_with(tmp_path, "profile_id: x\nunknown_key: 1\n"))
    response = http.get("/policy")
    assert response.status_code == 200
    assert "would refuse" in response.text and "unknown_key" in response.text


def test_a_missing_profile_is_reported(tmp_path: Path) -> None:
    response = client(tmp_path).get("/policy")
    assert response.status_code == 200 and "cannot be read" in response.text


def test_a_running_app_on_another_version_is_flagged(tmp_path: Path) -> None:
    about = {"profile": {"id": "test-institution", "version": 2}}
    stale = client(etc_with(tmp_path), about).get("/policy").text
    current = client(etc_with(tmp_path), {"profile": {"id": "test-institution", "version": 3}})
    assert "not the file" in stale
    assert "not the file" not in current.get("/policy").text


# --- The comparison ------------------------------------------------------------------------------


def view(tmp_path: Path, agents: Agents, deployment: str = "") -> policy_view.PolicyView:
    settings = AdminSettings(etc=etc_with(tmp_path, deployment=deployment))
    return policy_view.read(settings, System(), agents, None)


def test_the_roster_is_compared_with_the_profile(tmp_path: Path) -> None:
    agents = Agents(agents=[card("advisor-standards"), card("advisor-quality", "down")])
    rows = {r.agent_id: r for r in view(tmp_path, agents).agents}
    assert rows["advisor.standards"].problem is None
    assert rows["advisor.standards"].tool_servers == ("pid",)
    assert rows["advisor.policy"].problem and not rows["advisor.policy"].in_roster
    assert rows["advisor.policy"].needs_approval and not rows["advisor.standards"].needs_approval
    assert rows["advisor.quality"].action_class is None and rows["advisor.quality"].problem
    assert rows["orchestrator.stub"].orchestrator


def test_what_deployment_yaml_turns_off_is_listed(tmp_path: Path) -> None:
    found = view(tmp_path, Agents(), "disabled: [advisor-policy, advisor-ethics]\n")
    assert found.disabled == ["advisor-ethics", "advisor-policy"]


@pytest.mark.parametrize("deployment", ["not: [valid", "- a list\n", "disabled: nope\n"])
def test_an_unreadable_deployment_file_is_not_an_error(tmp_path: Path, deployment: str) -> None:
    found = view(tmp_path, Agents(), deployment)
    assert found.error is None and found.disabled == []
