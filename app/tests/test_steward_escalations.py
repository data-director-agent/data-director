"""Escalation to a data steward through the app's server (docs/specs/stewardship.md, invariants
4, 5 and 11; #373): a member opens one, replies to, withdraws and re-opens it; a steward reads
their teams' queue and moves the escalations routed to them; and what the rules refuse is a
`409` naming why. A steward also reads the project, and writes, pauses and decides in it
(invariants 2, 3 and 6 to 8; #374). The signed-in person is `TEST_PRINCIPAL`, a steward of the
library team."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from starlette.testclient import TestClient
from support import JSON_HEADERS, OTHER, check_fixture, configure_env, dist_dir, new_governance

from dd_app.app import build_app
from dd_app.config import EXAMPLE_PROFILE
from dd_app.governance import CREATED_BY_ROUTE, Governance
from dd_app.routes.escalations import Escalation, ProjectEscalations, StewardQueue
from dd_app.routes.stewarding import ProjectStewarding, ProjectView
from dd_harness.projects.escalations import NewEscalation
from dd_harness.storage import ProjectStorage
from dd_harness.testing import TEST_PRINCIPAL

FIXED = "2026-01-01T00:00:00+00:00"
LIBRARY = {
    "id": "library-rdm",
    "name": "Library Research Data Team",
    "members": [TEST_PRINCIPAL.principal_id],
    "supports": ["faculty-of-science"],
    "contact": "https://example.ac.uk/rdm",
    "response_time": "3 working days",
}
FACULTY = {"id": "faculty", "name": "Faculty Data Team", "members": [OTHER.principal_id]}


def with_teams(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *teams: dict[str, Any]) -> None:
    body = yaml.safe_load(EXAMPLE_PROFILE.read_text())
    if teams:
        body["stewardship"] = {"teams": list(teams)}
    profile = tmp_path / "profile.yaml"
    profile.write_text(yaml.safe_dump(body))
    monkeypatch.setenv("DD_PROFILE", str(profile))


@pytest.fixture
def governance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Governance]:
    configure_env(monkeypatch, tmp_path)
    with_teams(monkeypatch, tmp_path, LIBRARY)
    yield from new_governance()


@pytest.fixture
def client(governance: Governance, tmp_path: Path) -> TestClient:
    return TestClient(build_app(governance, dist_dir(tmp_path)))


@pytest.fixture
def store(governance: Governance) -> ProjectStorage:
    assert governance.projects is not None
    return governance.projects


@pytest.fixture
def owned(store: ProjectStorage) -> str:
    return store.create(acted_for=TEST_PRINCIPAL, caused_by=CREATED_BY_ROUTE, title="Soil")


@pytest.fixture
def theirs(store: ProjectStorage) -> str:
    """A project someone else owns, with an escalation they sent to the library team."""
    project_id = store.create(acted_for=OTHER, caused_by=CREATED_BY_ROUTE, title="Peat")
    store.open_escalation(
        project_id,
        NewEscalation(
            team_id="library-rdm",
            origin={"kind": "researcher"},
            note="May I share the interview transcripts?",
            scope_shared=["The project's title"],
        ),
        acted_for=OTHER,
        caused_by="test",
    )
    return project_id


def fixed(escalation: dict[str, Any]) -> dict[str, Any]:
    """`escalation` with its identifiers and times fixed, for a fixture."""
    return {
        **escalation,
        "escalation_id": "019a0000-0000-7000-8000-0000000000e1",
        "opened_at": FIXED,
        "updated_at": FIXED,
        "history": [{**h, "at": FIXED} for h in escalation["history"]],
        **(
            {"project_id": "019a0000-0000-7000-8000-0000000000a1"}
            if "project_id" in escalation
            else {}
        ),
    }


def stewarding_fixed(shown: ProjectStewarding) -> dict[str, Any]:
    """What a project shows of its stewards, with its times fixed, for a fixture."""
    body = shown.model_dump(mode="json")
    pause = body["paused"]
    return {
        **body,
        "messages": [{**m, "at": FIXED} for m in body["messages"]],
        "views": [{**v, "at": FIXED} for v in body["views"]],
        "gate_decisions": [{**g, "at": FIXED} for g in body["gate_decisions"]],
        "paused": pause and {**pause, "at": FIXED},
    }


def send(client: TestClient, project_id: str, **body: Any) -> Any:
    return client.post(
        f"/api/projects/{project_id}/escalations",
        json={"note": "Can I share this?", "scope_shared": ["The project's title"], **body},
        headers=JSON_HEADERS,
    )


def test_a_member_sends_a_matter_and_sees_where_it_went(client: TestClient, owned: str) -> None:
    before = client.get(f"/api/projects/{owned}/escalations").json()
    assert before["routes_to"] == "library-rdm" and before["unrouted"] is None
    assert before["escalations"] == []
    sent = send(client, owned)
    assert sent.status_code == 201
    (escalation,) = sent.json()["escalations"]
    assert escalation["state"] == "open"
    assert escalation["team_name"] == "Library Research Data Team"
    assert escalation["origin"] == {"kind": "researcher"}
    body = client.get(f"/api/projects/{owned}/escalations").json()
    check_fixture(
        "escalations.json",
        {**body, "escalations": [fixed(e) for e in body["escalations"]]},
        model=ProjectEscalations,
    )


def test_a_member_withdraws_and_cannot_make_a_stewards_move(client: TestClient, owned: str) -> None:
    (escalation,) = send(client, owned).json()["escalations"]
    url = f"/api/projects/{owned}/escalations/{escalation['escalation_id']}"
    taken = client.post(url, json={"move": "take"}, headers=JSON_HEADERS)
    assert taken.status_code == 409 and taken.json()["type"].endswith("not-your-move")
    withdrawn = client.post(url, json={"move": "withdraw"}, headers=JSON_HEADERS)
    assert withdrawn.status_code == 200 and withdrawn.json()["state"] == "withdrawn"
    again = client.post(url, json={"move": "reopen", "note": "Again"}, headers=JSON_HEADERS)
    assert again.status_code == 409 and again.json()["type"].endswith("move-not-allowed")


def test_a_referral_that_names_no_run_of_the_project_is_refused(
    client: TestClient, owned: str
) -> None:
    origin = {"kind": "policy_gate", "invocation_id": "019a0000-0000-7000-8000-000000000001"}
    refused = send(client, owned, origin=origin)
    assert refused.status_code == 409 and refused.json()["type"].endswith("origin-mismatch")


def test_a_steward_reads_the_queue_and_takes_and_resolves(client: TestClient, theirs: str) -> None:
    queue = client.get("/api/steward/escalations")
    assert queue.status_code == 200
    (row,) = queue.json()["escalations"]
    assert row["project_id"] == theirs and row["project_title"] == "Peat"
    assert row["member_of_project"] is False
    assert [(m["move"], m["permitted"]) for m in row["permitted_moves"]] == [("take", True)]
    check_fixture("steward-queue.json", {"escalations": [fixed(row)]}, model=StewardQueue)
    url = f"/api/steward/escalations/{theirs}/{row['escalation_id']}"
    taken = client.post(url, json={"move": "take"}, headers=JSON_HEADERS)
    assert taken.status_code == 200
    assert taken.json()["taken_by"]["principal_id"] == TEST_PRINCIPAL.principal_id
    assert taken.json()["history"][-1]["acting_as"] == "steward"
    assert {m["move"]: m["note"] for m in taken.json()["permitted_moves"]}["resolve"] == "required"
    no_note = client.post(url, json={"move": "resolve"}, headers=JSON_HEADERS)
    assert no_note.status_code == 409 and no_note.json()["type"].endswith("note-required")
    resolved = client.post(
        url, json={"move": "resolve", "note": "Yes, once anonymised."}, headers=JSON_HEADERS
    )
    check_fixture("escalation-resolved.json", fixed(resolved.json()), model=Escalation)
    assert client.get("/api/steward/escalations").json()["escalations"] == []
    assert len(client.get("/api/steward/escalations?state=resolved").json()["escalations"]) == 1


def test_a_steward_reaches_the_escalation_and_reads_the_project(
    client: TestClient, store: ProjectStorage, theirs: str
) -> None:
    read = client.get(f"/api/projects/{theirs}/escalations")
    assert read.status_code == 200
    (shown,) = read.json()["escalations"]
    assert [m["move"] for m in shown["permitted_moves"] if m["permitted"]] == ["take"]
    viewed = [e for e in store.events(theirs) if e["event"] == "steward_viewed"]
    assert [e["acted_for"]["principal_id"] for e in viewed] == [TEST_PRINCIPAL.principal_id]
    (row,) = client.get("/api/steward/escalations").json()["escalations"]
    # A researcher's move by the steward's route is refused as not theirs.
    url = f"/api/steward/escalations/{theirs}/{row['escalation_id']}"
    refused = client.post(url, json={"move": "withdraw"}, headers=JSON_HEADERS)
    assert refused.status_code == 409 and refused.json()["type"].endswith("not-your-move")


def test_the_steward_route_answers_404_for_what_is_not_the_stewards(
    client: TestClient, owned: str, theirs: str
) -> None:
    (escalation,) = send(client, owned).json()["escalations"]
    # The steward is a member of `owned`, so acts there as a member.
    url = f"/api/steward/escalations/{owned}/{escalation['escalation_id']}"
    queue = client.get("/api/steward/escalations").json()["escalations"]
    (queued,) = [row for row in queue if row["project_id"] == owned]
    assert queued["permitted_moves"] == [
        {"move": "take", "permitted": False, "note": "none", "refusal": "member-of-project"}
    ]
    member = client.post(url, json={"move": "take"}, headers=JSON_HEADERS)
    assert member.status_code == 409 and member.json()["type"].endswith("member-of-project")
    unknown = f"/api/steward/escalations/{theirs}/019a0000-0000-7000-8000-00000000ffff"
    assert client.post(unknown, json={"move": "take"}, headers=JSON_HEADERS).status_code == 404


def test_without_a_steward_team_the_project_says_so(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    configure_env(monkeypatch, tmp_path)
    with_teams(monkeypatch, tmp_path)
    for governance in new_governance():
        client = TestClient(build_app(governance, dist_dir(tmp_path)))
        assert governance.projects is not None
        project_id = governance.projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
        shown = client.get(f"/api/projects/{project_id}/escalations").json()
        assert shown["routes_to"] is None and shown["unrouted"] == "no-steward-team"
        refused = send(client, project_id)
        assert refused.status_code == 409 and refused.json()["type"].endswith("no-steward-team")
        assert client.get("/api/steward/escalations").json() == {"escalations": []}


def test_an_owner_chooses_the_support_team(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    configure_env(monkeypatch, tmp_path)
    with_teams(monkeypatch, tmp_path, LIBRARY, FACULTY)
    for governance in new_governance():
        client = TestClient(build_app(governance, dist_dir(tmp_path)))
        assert governance.projects is not None
        project_id = governance.projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
        assert (
            client.get(f"/api/projects/{project_id}/escalations").json()["unrouted"]
            == "team-required"
        )
        assert send(client, project_id).json()["type"].endswith("team-required")
        url = f"/api/projects/{project_id}/support-team"
        bad = client.put(url, json={"team_id": "nowhere"}, headers=JSON_HEADERS)
        assert bad.status_code == 409 and bad.json()["type"].endswith("unknown-team")
        chosen = client.put(url, json={"team_id": "faculty"}, headers=JSON_HEADERS)
        assert chosen.status_code == 200 and chosen.json()["support_team"] == "faculty"
        assert send(client, project_id).json()["escalations"][0]["team_id"] == "faculty"


def steward_post(client: TestClient, project_id: str, path: str, **body: Any) -> Any:
    return client.post(
        f"/api/projects/{project_id}/steward/{path}", json=body, headers=JSON_HEADERS
    )


@pytest.mark.requirement("C13.6")
def test_a_steward_opens_the_project_and_sees_what_they_may_do(
    client: TestClient, owned: str, theirs: str
) -> None:
    opened = client.get(f"/api/projects/{theirs}")
    assert opened.status_code == 200
    view = ProjectView.model_validate(opened.json())
    permitted = {a.action: a.permitted for a in view.permitted_actions.actions}
    assert view.permitted_actions.acting_as == "steward"
    assert permitted["pause"] and permitted["message"] and not permitted["decide"]
    check_fixture(
        "project-steward-view.json",
        {
            **opened.json(),
            "project_id": "019a0000-0000-7000-8000-0000000000a1",
            "created_at": FIXED,
        },
        model=ProjectView,
    )
    mine = ProjectView.model_validate(client.get(f"/api/projects/{owned}").json())
    assert mine.permitted_actions.acting_as == "member"
    assert {a.action: a.permitted for a in mine.permitted_actions.actions}["manage"]


@pytest.mark.requirement("C13.6")
def test_a_steward_changes_nothing_through_a_researchers_route(
    client: TestClient, theirs: str
) -> None:
    sent = send(client, theirs)
    assert sent.status_code == 404
    renamed = client.put(
        f"/api/projects/{theirs}/title", json={"title": "Mine now"}, headers=JSON_HEADERS
    )
    assert renamed.status_code == 404


@pytest.mark.requirement("C13.6")
def test_a_steward_writes_pauses_and_lifts_the_pause(
    client: TestClient, store: ProjectStorage, theirs: str
) -> None:
    assert steward_post(client, theirs, "messages", note="I am looking at this.").status_code == 200
    paused = steward_post(client, theirs, "pause", note="Checking consent forms")
    assert paused.status_code == 200
    again = steward_post(client, theirs, "pause", note="Again")
    assert again.status_code == 409 and again.json()["type"].endswith("already-paused")
    shown = ProjectStewarding.model_validate(
        client.get(f"/api/projects/{theirs}/stewarding").json()
    )
    assert shown.paused is not None and shown.paused.team_id == "library-rdm"
    assert [m.by["principal_id"] for m in shown.messages] == [TEST_PRINCIPAL.principal_id]
    check_fixture("stewarding.json", stewarding_fixed(shown), model=ProjectStewarding)
    resumed = steward_post(client, theirs, "resume", note="Consent confirmed")
    assert resumed.status_code == 200 and resumed.json()["paused"] is None
    kinds = [e["event"] for e in store.events(theirs)]
    assert {"steward_message", "project_paused", "project_resumed"} <= set(kinds)


@pytest.mark.requirement("C13.6")
def test_a_steward_route_refuses_a_member_and_hides_a_project_from_others(
    client: TestClient, owned: str, store: ProjectStorage
) -> None:
    send(client, owned)
    member = steward_post(client, owned, "pause", note="Not mine to pause")
    assert member.status_code == 403 and member.json()["type"].endswith("member-of-project")
    hidden = store.create(acted_for=OTHER, caused_by=CREATED_BY_ROUTE, title="Hidden")
    assert steward_post(client, hidden, "messages", note="Hello").status_code == 404
    assert client.get(f"/api/projects/{hidden}").status_code == 404
    assert client.get(f"/api/projects/{hidden}/stewarding").status_code == 404


def test_a_gate_decision_must_name_a_referred_run(client: TestClient, theirs: str) -> None:
    refused = steward_post(
        client, theirs, "gates/019a0000-0000-7000-8000-00000000ffff", verdict="cleared", note="OK"
    )
    assert refused.status_code == 409 and refused.json()["type"].endswith("run-not-referred")
