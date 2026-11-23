"""Steward teams through the app's server (docs/specs/stewardship.md, invariant 4;
docs/ui/steward-escalation-flows.md, Flow G; #1308): a steward reassigns an escalation to a
colleague in the team, or transfers it to another team, choosing from the targets the queue
offers; and what the harness refuses is a `409` naming why. The signed-in person is
`TEST_PRINCIPAL`, a steward of the library team."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from support import OTHER, check_fixture, configure_env, dist_dir, new_governance
from test_steward_escalations import FACULTY, LIBRARY, fixed, with_teams

from dd_app.app import build_app
from dd_app.governance import CREATED_BY_ROUTE, Governance
from dd_app.routes.escalations import Escalation
from dd_harness.projects.escalations import NewEscalation
from dd_harness.storage import ProjectStorage

pytestmark = pytest.mark.requirement("C13.6")

COVER = "https://orcid.org/0000-0003-1415-9269"


@pytest.fixture
def governance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Governance]:
    configure_env(monkeypatch, tmp_path)
    with_teams(monkeypatch, tmp_path, {**LIBRARY, "members": [*LIBRARY["members"], COVER]}, FACULTY)
    yield from new_governance()


@pytest.fixture
def client(governance: Governance, tmp_path: Path) -> TestClient:
    return TestClient(build_app(governance, dist_dir(tmp_path)))


@pytest.fixture
def escalated(governance: Governance) -> tuple[str, str]:
    """A project someone else owns, and the escalation they sent to the library team."""
    store: ProjectStorage | None = governance.projects
    assert store is not None
    project_id = store.create(acted_for=OTHER, caused_by=CREATED_BY_ROUTE, title="Peat")
    opened = store.open_escalation(
        project_id,
        NewEscalation(team_id="library-rdm", origin={"kind": "researcher"}, note="Help, please"),
        acted_for=OTHER,
        caused_by="test",
    )
    return project_id, opened["escalation_id"]


def move(client: TestClient, escalated: tuple[str, str], **body: Any) -> Any:
    project_id, escalation_id = escalated
    return client.post(f"/api/steward/escalations/{project_id}/{escalation_id}", json=body)


def offered(client: TestClient, name: str) -> list[str] | None:
    (row,) = client.get("/api/steward/escalations").json()["escalations"]
    listed = next((m for m in row["permitted_moves"] if m["move"] == name), None)
    return None if listed is None else [t["id"] for t in listed["targets"]]


def test_a_steward_reassigns_to_a_colleague_the_queue_offers(
    client: TestClient, escalated: tuple[str, str]
) -> None:
    assert move(client, escalated, move="take").status_code == 200
    assert offered(client, "reassign") == [COVER]
    refused = move(client, escalated, move="reassign", to=OTHER.principal_id)
    assert (refused.status_code, refused.json()["type"].rsplit("/", 1)[-1]) == (409, "not-in-team")
    moved = move(client, escalated, move="reassign", to=COVER)
    assert moved.status_code == 200
    body = moved.json()
    assert body["state"] == "taken"
    assert body["taken_by"]["principal_id"] == COVER
    assert body["history"][-1]["to_steward"]["principal_id"] == COVER


def test_a_steward_transfers_to_another_team_with_a_note(
    client: TestClient, escalated: tuple[str, str]
) -> None:
    assert offered(client, "transfer") == ["faculty"]
    for body, slug in [
        ({"to": "faculty"}, "note-required"),
        ({"to": "nowhere", "note": "Not ours"}, "unknown-team"),
        ({"note": "Not ours"}, "target-required"),
    ]:
        refused = move(client, escalated, move="transfer", **body)
        assert (refused.status_code, refused.json()["type"].rsplit("/", 1)[-1]) == (409, slug)
    moved = move(client, escalated, move="transfer", to="faculty", note="A faculty matter")
    assert moved.status_code == 200
    body = moved.json()
    assert (body["state"], body["team_id"], body["team_name"]) == (
        "open",
        "faculty",
        FACULTY["name"],
    )
    # The library steward may make no move on it now.
    assert body["permitted_moves"] == []
    check_fixture("escalation-transferred.json", fixed(body), model=Escalation)
    # It has left the library team's queue.
    assert client.get("/api/steward/escalations").json()["escalations"] == []
