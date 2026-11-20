"""Projects: listing, creating, paging, access, deletion and restoring through the routes."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from support import (
    JSON_HEADERS,
    a_file_inventory,
    check_fixture,
    configure_env,
    delegating_app,
    dist_dir,
    new_governance,
    normalised_conversation,
    start,
    turn,
)

from dd_app.app import build_app
from dd_app.governance import (
    Governance,
)
from dd_app.routes.projects import DeletedProject, ProjectSummary
from dd_harness.project_access import Role
from dd_harness.projects import PROJECT_CREATED, TITLE_MAX_LENGTH, ProjectStore
from dd_harness.testing import (
    TEST_PRINCIPAL,
)
from dd_sdk.contract.models import Principal


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


@pytest.fixture
def in_projects(env: Path, dist: Path) -> Iterator[tuple[Governance, Any]]:
    """As `delegating`, with each conversation started in a project of its own."""
    yield delegating_app(env, dist, ProjectStore(env / "projects"))


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
    check_fixture(
        "projects.json",
        normalised_conversation(response.json()),
        model=list[ProjectSummary],
    )


def test_the_projects_list_reads_the_run_store_once_whatever_the_number_of_projects(
    in_projects: tuple[Governance, Any], monkeypatch: pytest.MonkeyPatch
):
    governance, app = in_projects
    client = TestClient(app)
    for n in range(3):
        conversation_id = start(client)
        assert turn(client, conversation_id, f"Question {n}").status_code == 200
    store = governance.conductor.store
    reads: list[str] = []
    for name in (
        "iter_envelopes",
        "list_conversations",
        "list_runs",
        "get",
        "get_request",
        "get_many",
    ):
        real = getattr(store, name)

        def counted(*args: Any, _name: str = name, _real: Any = real, **kwargs: Any) -> Any:
            reads.append(_name)
            return _real(*args, **kwargs)

        monkeypatch.setattr(store, name, counted)

    response = client.get("/api/projects")

    assert response.status_code == 200
    assert sorted(c["title"] for p in response.json() for c in p["conversations"]) == [
        "Question 0",
        "Question 1",
        "Question 2",
    ]
    # One scan for the listing, and the titles in one read each, not one per conversation.
    assert reads.count("list_conversations") == 1
    assert reads.count("iter_envelopes") == 1  # The file store's own scan, made by that listing.
    assert "get" not in reads and "get_request" not in reads
    assert reads.count("get_many") <= 2


def test_a_person_creates_a_project_with_no_conversation(in_projects: tuple[Governance, Any]):
    """Docs/specs/app.md, rule 27: **New project** creates the project on its own, for the person
    signed in, and it is listed before it holds anything."""
    governance, app = in_projects
    store = governance.projects
    assert store is not None
    client = TestClient(app)

    named = client.post("/api/projects", json={"title": "  Soil cores  "})
    assert named.status_code == 201
    body = named.json()
    assert body["title"] == "Soil cores"
    assert body["title_source"] == "researcher"
    assert body["created_by"]["principal_id"] == TEST_PRINCIPAL.principal_id
    assert body["conversations"] == []
    (created,) = store.events(body["project_id"])
    assert created["event"] == PROJECT_CREATED
    assert created["caused_by"] == "POST /api/projects"
    check_fixture("project-created.json", normalised_conversation(body), model=ProjectSummary)

    for unnamed in ({}, {"title": "   "}, {"title": None}):
        response = client.post("/api/projects", json=unnamed)
        assert response.status_code == 201
        assert response.json()["title"] is None

    # Listed as created, the one created last first; a project the app made for a
    # conversation and nothing else is still left out.
    store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    listed = client.get("/api/projects").json()
    assert len(listed) == 4
    assert listed[-1] == body


@pytest.mark.parametrize(
    "content",
    [
        b"not json",
        b"[]",
        b'{"title": 3}',
        b'{"name": "Soil cores"}',
        b'{"title": "Soil cores", "acted_for": "someone"}',
        json.dumps({"title": "x" * (TITLE_MAX_LENGTH + 1)}).encode(),
    ],
)
def test_a_project_is_not_created_from_a_malformed_body(
    in_projects: tuple[Governance, Any], content: bytes
):
    governance, app = in_projects
    store = governance.projects
    assert store is not None
    response = TestClient(app).post("/api/projects", content=content, headers=JSON_HEADERS)
    assert response.status_code == 400
    assert response.json()["title"] == "Data Director could not create this project"
    assert store.projects() == []


def test_a_server_that_keeps_no_projects_creates_none(delegating: tuple[Governance, Any]):
    _governance, app = delegating
    response = TestClient(app).post("/api/projects", json={})
    assert response.status_code == 404
    assert response.json()["type"].endswith("project-not-found")


def test_projects_are_paged_the_one_created_last_first(
    in_projects: tuple[Governance, Any],
):
    governance, app = in_projects
    client = TestClient(app)
    store = governance.projects
    assert store is not None
    created = []
    for n in range(3):
        project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
        store.add_inventory(
            project_id, a_file_inventory(f"{n}.csv"), acted_for=TEST_PRINCIPAL, caused_by="test"
        )
        created.append(project_id)
        store.create(acted_for=TEST_PRINCIPAL, caused_by="test")  # empty, so not listed
    newest_first = list(reversed(created))
    assert [p["project_id"] for p in client.get("/api/projects").json()] == newest_first
    listed: list[str] = []
    url: str | None = "/api/projects?limit=2"
    while url:
        response = client.get(url)
        assert len(response.json()) <= 2
        listed += [p["project_id"] for p in response.json()]
        url = response.links.get("next", {}).get("url")
    assert listed == newest_first
    for refused in ("0", "x", "201"):
        response = client.get(f"/api/projects?limit={refused}")
        assert response.status_code == 400
        assert response.json()["type"].endswith("/request-refused")
    # A cursor that names no project the person may read names an empty page.
    someone = Principal(principal_id="https://orcid.org/0000-0002-1694-233X", name="Someone Else")
    theirs = store.create(acted_for=someone, caused_by="test")
    for cursor in ("nonsense", theirs):
        assert client.get(f"/api/projects?before={cursor}").json() == []


def test_every_project_route_answers_someone_elses_project_as_one_that_does_not_exist(
    in_projects: tuple[Governance, Any],
):
    """Docs/specs/projects.md, invariant 17: a person with no role in a project can neither read
    nor change it by any route, even knowing its identifier, and is told no more than for a
    project that does not exist. The routes are read from the server, so a new one is covered."""
    governance, app = in_projects
    client = TestClient(app)
    store = governance.projects
    assert store is not None
    someone = Principal(principal_id="https://orcid.org/0000-0002-1694-233X", name="Someone Else")
    theirs = store.create(acted_for=someone, caused_by="test")
    store.add_inventory(theirs, a_file_inventory("b.csv"), acted_for=someone, caused_by="test")
    before = store.events(theirs)
    params = {
        "project_id": theirs,
        "document_id": str(uuid.UUID(int=0x0190_0000_0000_7000_8000_0000_0000_0000)),
        "digest": "a" * 64,
        "step_id": "anything",
        "question_id": "intake.entry",
        "item_id": "0" * 24,
    }

    checked = []
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/projects/{project_id}"):
            continue
        for method in sorted(set(route.methods) - {"HEAD"}):
            url = path.format(**params)
            body: dict[str, Any] | None = None if method == "GET" else {}
            response = client.request(method, url, json=body)
            missing = client.request(
                method, path.format(**{**params, "project_id": str(uuid.uuid4())}), json=body
            )
            assert (response.status_code, method, path) == (404, method, path)
            assert response.json()["type"] == missing.json()["type"]
            assert response.json()["type"].endswith("project-not-found")
            checked.append((method, path))
    assert checked
    assert store.events(theirs) == before


def test_a_server_that_keeps_no_projects_answers_every_project_route_with_404(
    delegating: tuple[Governance, Any],
):
    governance, app = delegating
    assert governance.projects is None
    client = TestClient(app)
    response = client.get(f"/api/projects/{uuid.uuid4()}/documents")
    assert response.status_code == 404
    assert response.json()["type"].endswith("project-not-found")


def test_a_deleted_projects_conversations_leave_the_list_and_come_back_when_it_is_restored(
    in_projects: tuple[Governance, Any],
):
    """Docs/specs/projects.md, invariant 23: a project's conversations follow it."""
    _governance, app = in_projects
    client = TestClient(app)
    conversation_id = start(client)
    assert turn(client, conversation_id, "Hello").status_code == 200
    (listed,) = client.get("/api/conversations").json()
    project_id = listed["project_id"]
    title = client.get("/api/projects").json()[0]["title"] or project_id
    deleted = client.request("DELETE", f"/api/projects/{project_id}", json={"title": title})
    assert deleted.status_code == 200
    assert client.get("/api/conversations").json() == []
    assert client.get("/api/runs").json() == []
    assert client.post(f"/api/projects/{project_id}/restore", json={}).status_code == 200
    assert [c["conversation_id"] for c in client.get("/api/conversations").json()] == [
        conversation_id
    ]


def test_the_projects_an_owner_deleted_are_listed_for_restoring(governance: Governance, dist: Path):
    """Docs/specs/projects.md, invariant 23: an owner finds a deleted project only under
    "recently deleted", with when, by whom and until when; the shell's fixture."""
    client = TestClient(build_app(governance, dist))
    project_id = client.post("/api/projects", json={"title": "Soil cores"}).json()["project_id"]
    deleted = client.request("DELETE", f"/api/projects/{project_id}", json={"title": "Soil cores"})
    assert deleted.status_code == 200
    assert client.get("/api/projects").json() == []
    response = client.get("/api/projects/deleted")
    (listed,) = response.json()
    assert listed["project_id"] == project_id
    assert listed["deleted"]["by"]["principal_id"] == TEST_PRINCIPAL.principal_id
    check_fixture(
        "projects-deleted.json",
        normalised_conversation(response.json()),
        model=list[DeletedProject],
    )


def test_a_member_asking_for_an_owners_action_is_forbidden_and_may_still_read(
    in_projects: tuple[Governance, Any], monkeypatch: pytest.MonkeyPatch
):
    """Docs/specs/projects.md, invariant 17: a member is told an owner's action is not theirs
    (403), not that the project is missing. No one is a plain member until membership events are
    built (#389), so the role the check reads is stood in for here."""
    governance, app = in_projects
    client = TestClient(app)
    store = governance.projects
    assert store is not None
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    before = store.events(project_id)
    monkeypatch.setattr(governance, "role", lambda _project_id, _principal: Role.MEMBER)
    document_id = str(uuid.UUID(int=0x0190_0000_0000_7000_8000_0000_0000_0000))

    decided = client.post(f"/api/projects/{project_id}/documents/{document_id}/decisions", json={})
    assert decided.status_code == 403
    assert decided.json()["type"].endswith("project-action-forbidden")
    assert client.get(f"/api/projects/{project_id}/documents").status_code == 200
    assert store.events(project_id) == before


def test_the_projects_page_is_served_and_lists_nothing_without_projects(
    delegating: tuple[Governance, Any],
):
    _governance, app = delegating
    client = TestClient(app)
    assert client.get("/api/projects").json() == []
    page = client.get("/projects")
    assert page.status_code == 200
    assert "<title>shell</title>" in page.text
