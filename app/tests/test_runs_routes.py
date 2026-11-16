"""Runs (`POST /api/runs`, `GET /api/runs`, `GET /api/runs/{id}`) and examples.

An alpha substantiates no requirement, so these tests carry no requirement marker."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from support import (
    STANDARDS_AGENT_ID,
    check_fixture,
    configure_env,
    dist_dir,
    example,
    new_governance,
    normalised,
    run,
)

from dd_app.app import build_app
from dd_app.governance import (
    Governance,
)
from dd_harness.testing import (
    TEST_PRINCIPAL,
)


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    return configure_env(monkeypatch, tmp_path)


@pytest.fixture
def governance(env: Path) -> Iterator[Governance]:
    yield from new_governance()


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    return dist_dir(tmp_path)


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


def test_the_history_is_paged_with_a_link_to_the_next_page(governance: Governance, dist: Path):
    client = TestClient(build_app(governance, dist))
    stored = [run(client, example("empty.profile")).json()["envelope"] for _ in range(3)]
    newest_first = [e["invocation_id"] for e in reversed(stored)]
    assert [r["invocation_id"] for r in client.get("/api/runs").json()] == newest_first
    listed: list[str] = []
    url: str | None = "/api/runs?limit=2"
    while url:
        response = client.get(url)
        assert len(response.json()) <= 2
        listed += [r["invocation_id"] for r in response.json()]
        url = response.links.get("next", {}).get("url")
    assert listed == newest_first
    for refused in ("0", "-1", "x", "201"):
        response = client.get(f"/api/runs?limit={refused}")
        assert response.status_code == 400
        assert response.json()["type"].endswith("/request-refused")
    assert client.get("/api/runs?before=nonsense").json() == []


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
