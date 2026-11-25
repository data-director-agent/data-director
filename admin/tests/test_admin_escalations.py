"""The admin service's Escalations page (docs/guide/operations/admin.md): each steward team's live
escalations from the project store, how long each has waited, and that a researcher's note is
never shown and nothing can be changed."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from starlette.testclient import TestClient

from dd_admin import escalation_queue, policy_view
from dd_admin.agents import Agents
from dd_admin.app import Admin, build_app
from dd_admin.settings import AdminSettings
from dd_admin.system import System
from dd_harness.projects import ProjectStore
from dd_harness.projects.escalations import NewEscalation
from dd_harness.testing.fixtures import TEST_PRINCIPAL
from dd_sdk.contract.models import Principal

STEWARD = Principal(principal_id="https://orcid.org/0000-0002-1825-0097", name="A Steward")
NOTE = "the researcher's private words, not to be shown"

PROFILE = f"""
profile_id: test-institution
version: 1
agents:
  orchestrator.stub: advise
orchestrator: orchestrator.stub
stewardship:
  reroute_after: P3D
  teams:
    - id: library-rdm
      name: Library Research Data Team
      members:
        - {STEWARD.principal_id}
    - id: ethics
      name: Ethics Team
      members:
        - {STEWARD.principal_id}
"""


def escalate(store: ProjectStore, team: str = "library-rdm") -> tuple[str, str]:
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    opened = store.open_escalation(
        project_id,
        NewEscalation(team_id=team, origin={"kind": "researcher"}, note=NOTE),
        acted_for=TEST_PRINCIPAL,
        caused_by="test",
    )
    return project_id, opened["escalation_id"]


def take(store: ProjectStore, project_id: str, escalation_id: str) -> None:
    store.move_escalation(
        project_id, escalation_id, "take", side="steward", acted_for=STEWARD, caused_by="test"
    )


def profile_view(tmp_path: Path) -> policy_view.PolicyView:
    (tmp_path / "profile.yaml").write_text(PROFILE)
    return policy_view.read(AdminSettings(etc=tmp_path), System(), Agents(), None)


def client(tmp_path: Path, store: ProjectStore | None) -> TestClient:
    (tmp_path / "profile.yaml").write_text(PROFILE)
    admin = Admin(AdminSettings(etc=tmp_path), System(), projects=store)
    return TestClient(build_app(admin), base_url="http://localhost:8200")


def test_the_page_answers_get_and_nothing_that_could_change_state(tmp_path: Path) -> None:
    http = client(tmp_path, ProjectStore(tmp_path / "projects"))
    assert http.get("/escalations").status_code == 200
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert http.request(method, "/escalations").status_code == 405


def test_each_teams_live_escalations_are_counted_and_the_note_is_not_shown(
    tmp_path: Path,
) -> None:
    store = ProjectStore(tmp_path / "projects")
    escalate(store)
    taken_project, taken = escalate(store)
    take(store, taken_project, taken)
    escalate(store, "ethics")
    found = escalation_queue.read(store, profile_view(tmp_path))
    rows = {t.team_id: t for t in found.teams}
    assert (rows["library-rdm"].open, rows["library-rdm"].taken) == (1, 1)
    assert (rows["ethics"].open, rows["ethics"].taken) == (1, 0)
    assert len(found.items) == 3 and found.open == 2
    page = client(tmp_path, store).get("/escalations").text
    assert "Library Research Data Team" in page and "A Steward" in page
    assert NOTE not in page


def test_an_open_escalation_past_the_reroute_time_is_overdue(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "projects")
    escalate(store)
    soon = escalation_queue.read(store, profile_view(tmp_path))
    later = escalation_queue.read(
        store, profile_view(tmp_path), now=datetime.now(UTC) + timedelta(days=4)
    )
    assert soon.overdue == 0 and later.overdue == 1
    assert later.items[0].overdue


def test_a_taken_escalation_is_never_overdue(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "projects")
    project_id, escalation_id = escalate(store)
    take(store, project_id, escalation_id)
    later = datetime.now(UTC) + timedelta(days=30)
    assert escalation_queue.read(store, profile_view(tmp_path), now=later).overdue == 0


def test_without_a_project_store_or_a_profile_it_says_what_is_missing(tmp_path: Path) -> None:
    assert escalation_queue.read(None, profile_view(tmp_path)).reason == "DD_PROJECTS_DIR"
    empty = policy_view.PolicyView(configured=True, error="no profile")
    found = escalation_queue.read(ProjectStore(tmp_path / "projects"), empty)
    assert not found.configured and "profile" in (found.reason or "")
    assert "DD_PROJECTS_DIR" in client(tmp_path, None).get("/escalations").text


def test_a_team_whose_projects_cannot_be_read_is_named_and_the_other_still_shows(
    tmp_path: Path,
) -> None:
    store = ProjectStore(tmp_path / "projects")
    escalate(store, "ethics")

    class Broken(ProjectStore):
        def logs_naming(self, principal_id: str) -> dict[str, list[dict[str, object]]]:
            if principal_id.endswith("library-rdm"):
                raise OSError("disk gone")
            return super().logs_naming(principal_id)

    broken = Broken(tmp_path / "projects")
    found = escalation_queue.read(broken, profile_view(tmp_path))
    assert len(found.problems) == 1 and "Library Research Data Team" in found.problems[0]
    assert {t.team_id: t.open for t in found.teams} == {"library-rdm": 0, "ethics": 1}


def test_a_span_is_shown_in_its_largest_whole_unit() -> None:
    from dd_admin.app import _duration

    assert _duration(timedelta(days=3)) == "3 days"
    assert _duration(timedelta(hours=36)) == "36 hours"
    assert _duration(timedelta(minutes=1)) == "1 minute"
    assert _duration(None) == "—"
