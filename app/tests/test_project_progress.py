"""Where a project is in the process flow, through the app's server (docs/specs/orchestration.md):
the researcher's word on it goes to the harness with the principal the authenticator names, and
the server answers with the progress derived anew from the project log."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from starlette.testclient import TestClient
from support import configure_env, dist_dir, new_governance

from dd_app.app import build_app
from dd_app.governance import Governance
from dd_harness.progress import ENTRY_CHOSEN, STEP_MARKED
from dd_harness.storage import ProjectStorage
from dd_harness.testing import TEST_PRINCIPAL, file_inventory
from dd_sdk.process_flow import OUT_OF_SCOPE


@pytest.fixture
def governance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Governance]:
    configure_env(monkeypatch, tmp_path)
    yield from new_governance()


@pytest.fixture
def client(governance: Governance, tmp_path: Path) -> TestClient:
    return TestClient(build_app(governance, dist_dir(tmp_path)))


@pytest.fixture
def store(governance: Governance) -> ProjectStorage:
    assert governance.projects is not None
    return governance.projects


def test_progress_is_derived_from_the_project_and_changed_by_the_researchers_word(
    client: TestClient, store: ProjectStorage
) -> None:
    project = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    store.add_inventory(project, file_inventory("a.csv"), acted_for=TEST_PRINCIPAL, caused_by="t")
    found = client.get(f"/api/projects/{project}/progress")
    assert found.status_code == 200
    assert found.json()["entry"] is None
    assert found.json()["steps"] == {"preparation.files": "done"}
    assert found.json()["suggested"] == "setup.documentation"

    chosen = client.put(f"/api/projects/{project}/progress/entry", json={"entry": 2})
    assert chosen.status_code == 201 and chosen.json()["entry"] == 2
    marked = client.put(
        f"/api/projects/{project}/progress/steps/governance.embargo", json={"mark": "skipped"}
    )
    assert marked.status_code == 201
    assert marked.json()["steps"]["governance.embargo"] == "skipped"
    reopened = client.put(
        f"/api/projects/{project}/progress/steps/governance.embargo", json={"mark": "open"}
    )
    assert "governance.embargo" not in reopened.json()["steps"]

    events = [e for e in store.events(project) if e["event"] in (ENTRY_CHOSEN, STEP_MARKED)]
    assert len(events) == 3
    assert all(e["caused_by"].startswith("PUT /api/projects/") for e in events)


def test_what_is_no_entry_step_or_mark_is_refused_and_records_nothing(
    client: TestClient, store: ProjectStorage
) -> None:
    project = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    before = store.events(project)
    for path, body in (
        ("entry", {"entry": 4}),
        ("entry", {"entry": "2"}),
        ("entry", {"entry": True}),
        ("steps/R5", {"mark": "done"}),
        (f"steps/{next(iter(OUT_OF_SCOPE))}", {"mark": "done"}),
        ("steps/governance.embargo", {"mark": "maybe"}),
        ("steps/governance.embargo", {}),
    ):
        refused = client.put(f"/api/projects/{project}/progress/{path}", json=body)
        assert refused.status_code == 400, path
    assert store.events(project) == before
    assert (
        client.get("/api/projects/01900000-0000-7000-8000-000000000001/progress").status_code == 404
    )
