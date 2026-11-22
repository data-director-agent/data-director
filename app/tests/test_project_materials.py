"""What a project holds of a researcher's files: inventories and documents, attached to a turn
or added outside one."""

from __future__ import annotations

import base64
import json
import uuid
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from support import (
    FIXTURES,
    JSON_HEADERS,
    PROTOCOL,
    a_document,
    a_file_inventory,
    configure_env,
    delegating_app,
    dist_dir,
    new_governance,
    start,
    turn,
)

from dd_app.governance import (
    BOTH_ONLY_TEXT,
    DOCUMENTATION_ONLY_TEXT,
    INVENTORY_ONLY_TEXT,
    Governance,
)
from dd_harness.project_access import Role
from dd_harness.projects import ProjectStore
from dd_harness.projects.extract import PDF
from dd_harness.storage import ProjectStorage
from dd_harness.testing import (
    TEST_PRINCIPAL,
)
from dd_harness.testing.documents import PROTOCOL as DOCUMENT_TEXT
from dd_harness.testing.documents import pdf_file


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


def test_what_the_researcher_left_out_of_an_inventory_is_kept_nowhere(
    in_projects: tuple[Governance, Any],
):
    """The shell sends an inventory without what the researcher left out when checking it
    (#472); `inventory-left-out.json` holds it as attached and as sent, and
    `ConversationHome.test.tsx` checks the shell sends exactly `sent`. Nothing left out is in
    any file the project keeps, and the agent is told that something was left out."""
    governance, app = in_projects
    fixture = json.loads((FIXTURES / "inventory-left-out.json").read_text(encoding="utf-8"))
    client = TestClient(app)
    conversation_id = start(client)
    response = turn(client, conversation_id, " ", inventory=fixture["sent"])
    assert response.status_code == 200, response.json()
    envelope = response.json()["envelope"]
    store = governance.projects
    assert isinstance(store, ProjectStore)
    added = store.events(envelope["project_id"])[-1]
    assert added["event"] == "inventory_added"
    assert added["file_count"] == 1

    kept = [p for p in (store.root / envelope["project_id"]).rglob("*") if p.is_file()]
    assert kept
    for path in kept:
        text = path.read_text(encoding="utf-8")
        for name in fixture["left_out"]:
            assert name not in text, f"{name!r} is in {path.name}"
    served = client.get(f"/api/projects/{envelope['project_id']}/inventory").json()
    assert served == fixture["sent"]

    shown = (governance.conductor.store.get_request(envelope["invocation_id"]) or {})["input"]
    assert shown["project_inventory"]["inventory_limitations"][-1].startswith(
        "Before this inventory was added, the researcher left out 1 file and 1 column."
    )


def test_a_member_revises_the_projects_inventory_outside_a_turn(
    in_projects: tuple[Governance, Any], monkeypatch: pytest.MonkeyPatch
):
    governance, app = in_projects
    client = TestClient(app)
    store = governance.projects
    assert store is not None
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    monkeypatch.setattr(governance, "role", lambda _project_id, _principal: Role.MEMBER)
    url = f"/api/projects/{project_id}/inventory"

    first = client.post(url, json={"inventory": a_file_inventory("a.csv")})
    assert first.status_code == 201, first.json()
    assert first.json()["revises"] is None
    revised = a_file_inventory("a.csv")
    revised["inventory_files"][0] |= {"file_description": "Readings", "file_role": "data"}
    second = client.post(url, json={"inventory": revised})
    assert second.status_code == 201, second.json()
    assert second.json()["revises"] == first.json()["digest"]
    added = store.events(project_id)[-1]
    assert added["caused_by"] == f"POST {url}"
    assert client.get(url).json() == revised


@pytest.mark.parametrize(
    "body",
    [
        {"inventory": {"schema_class": "FileInventory"}},
        {"inventory": ["a.csv"]},
        ["a.csv"],
    ],
)
def test_a_revision_that_is_not_an_inventory_is_refused(
    in_projects: tuple[Governance, Any], body: Any
):
    governance, app = in_projects
    client = TestClient(app)
    store = governance.projects
    assert store is not None
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    refused = client.post(f"/api/projects/{project_id}/inventory", json=body)
    assert refused.status_code == 400
    assert store.inventory(project_id) is None
    unknown = client.post(
        f"/api/projects/{uuid.uuid4()}/inventory", json={"inventory": a_file_inventory("a")}
    )
    assert unknown.status_code == 404


def test_a_project_without_an_inventory_serves_none(in_projects: tuple[Governance, Any]):
    _governance, app = in_projects
    client = TestClient(app)
    started = client.post("/api/conversations", headers=JSON_HEADERS).json()
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
    started = client.post("/api/conversations", headers=JSON_HEADERS).json()
    response = turn(client, started["conversation_id"], "hello", inventory=inventory)
    assert response.status_code == 400
    assert detail in response.json()["detail"]
    assert list(governance.conductor.store.iter_envelopes()) == []
    assert governance.projects is not None
    assert governance.projects.summary(started["project_id"])["inventory"] is None


def test_an_attached_document_is_kept_and_the_orchestrator_is_told_of_it_without_its_text(
    in_projects: tuple[Governance, Any],
):
    governance, app = in_projects
    client = TestClient(app)
    conversation_id = start(client)
    # A document may be sent with no words.
    first = turn(client, conversation_id, " ", documentation=a_document())
    assert first.status_code == 200, first.json()
    envelope = first.json()["envelope"]
    project_id = envelope["project_id"]
    store = governance.projects
    assert store is not None
    added = store.events(project_id)[-1]
    assert added["event"] == "documentation_added"
    assert added["caused_by"] == f"POST /api/conversations/{conversation_id}/turns"

    shown = (governance.conductor.store.get_request(envelope["invocation_id"]) or {})["input"]
    assert shown["message_text"] == DOCUMENTATION_ONLY_TEXT
    [listed] = shown["project_documentation"]
    assert listed["documentation_name"] == "protocol.md"
    assert listed["documentation_digest"] == added["digest"]
    assert "Sediment cores" not in json.dumps(shown)

    # Later turns are told of it too, without sending it again.
    second = turn(client, conversation_id, "Draft a README", envelope["invocation_id"])
    later = governance.conductor.store.get_request(second.json()["envelope"]["invocation_id"])
    assert later is not None
    assert later["input"]["project_documentation"] == shown["project_documentation"]

    # The list and the text are served for the researcher to read.
    assert client.get(f"/api/projects/{project_id}/documentation").json() == [listed]
    text = client.get(f"/api/projects/{project_id}/documentation/{added['digest']}")
    assert text.status_code == 200
    assert text.headers["content-type"].startswith("text/plain")
    assert text.text == PROTOCOL
    # A document attached as text was read from no file.
    no_file = client.get(f"/api/projects/{project_id}/documentation/{added['digest']}?original")
    assert no_file.status_code == 404


def test_a_turn_may_attach_an_inventory_and_a_document_together(
    in_projects: tuple[Governance, Any],
):
    governance, app = in_projects
    client = TestClient(app)
    response = turn(
        client,
        start(client),
        "",
        inventory=a_file_inventory("a.csv"),
        documentation=a_document(),
    )
    assert response.status_code == 200, response.json()
    envelope = response.json()["envelope"]
    assert governance.projects is not None
    kinds = [e["event"] for e in governance.projects.events(envelope["project_id"])]
    assert kinds[-2:] == ["inventory_added", "documentation_added"]
    shown = (governance.conductor.store.get_request(envelope["invocation_id"]) or {})["input"]
    assert shown["message_text"] == BOTH_ONLY_TEXT
    assert shown["project_inventory"] and shown["project_documentation"]


@pytest.mark.parametrize(
    ("documentation", "detail"),
    [
        ({"name": "data.csv", "media_type": "text/csv", "text": "a,b"}, "not 'text/csv'"),
        (a_document(name="../protocol.md"), "without any folder"),
        (a_document(text="x" * (256 * 1024 + 1)), "at most"),
        (a_document(text=" "), "blank"),
        ({"name": "protocol.md", "text": "x"}, "`documentation` must be"),
        ({**a_document(), "path": "/home"}, "`documentation` must be"),
        ("protocol.md", "`documentation` must be"),
    ],
)
def test_a_document_that_is_refused_leaves_no_trace_and_nothing_runs(
    in_projects: tuple[Governance, Any], documentation: Any, detail: str
):
    governance, app = in_projects
    client = TestClient(app)
    started = client.post("/api/conversations", headers=JSON_HEADERS).json()
    # Sent with an inventory the project would keep: that is refused with it.
    response = turn(
        client,
        started["conversation_id"],
        "hello",
        inventory=a_file_inventory("a.csv"),
        documentation=documentation,
    )
    assert response.status_code == 400
    assert detail in response.json()["detail"]
    assert list(governance.conductor.store.iter_envelopes()) == []
    assert governance.projects is not None
    assert governance.projects.summary(started["project_id"])["inventory"] is None
    assert governance.projects.documentation(started["project_id"]) == []


@pytest.mark.requirement("DD-POLICY")
def test_a_profile_that_refuses_documents_refuses_a_turn_that_attaches_one(
    in_projects: tuple[Governance, Any],
):
    """Under `attached_documents: refused` the turn is refused before anything is kept or run,
    and the agent directory says so, so the shell does not offer it (docs/specs/projects.md)."""
    governance, app = in_projects
    profile = governance.conductor.profile
    governance.conductor.profile = replace(profile, attached_documents="refused")
    client = TestClient(app)
    started = client.post("/api/conversations", headers=JSON_HEADERS).json()

    response = turn(client, started["conversation_id"], "hello", documentation=a_document())

    assert response.status_code == 400
    assert list(governance.conductor.store.iter_envelopes()) == []
    assert governance.projects is not None
    assert governance.projects.documentation(started["project_id"]) == []
    listing = client.get("/api/agents", headers=JSON_HEADERS).json()
    assert listing["profile"]["attached_documents"] == "refused"


def a_pdf(data: bytes | None = None) -> dict[str, str]:
    """A PDF a turn attaches as the file, base64."""
    raw = pdf_file() if data is None else data
    return {"name": "plan.pdf", "media_type": PDF, "data": base64.b64encode(raw).decode()}


def test_a_pdf_is_kept_as_the_file_and_its_text_and_the_agent_is_told_of_it(
    in_projects: tuple[Governance, Any],
):
    """A Word document or PDF is read inside the deployment; the project keeps the file beside
    the text, and an agent is told of it as of any document (#961, docs/specs/projects.md)."""
    governance, app = in_projects
    client = TestClient(app)
    conversation_id = start(client)

    response = turn(client, conversation_id, " ", documentation=a_pdf())

    assert response.status_code == 200, response.json()
    envelope = response.json()["envelope"]
    project_id = envelope["project_id"]
    shown = (governance.conductor.store.get_request(envelope["invocation_id"]) or {})["input"]
    [listed] = shown["project_documentation"]
    assert listed["documentation_source_media_type"] == PDF
    digest = listed["documentation_digest"]
    text = client.get(f"/api/projects/{project_id}/documentation/{digest}")
    assert DOCUMENT_TEXT in text.text
    original = client.get(f"/api/projects/{project_id}/documentation/{digest}?original")
    assert original.status_code == 200
    assert original.headers["content-type"].startswith(PDF)
    assert original.content == pdf_file()


@pytest.mark.parametrize(
    "documentation",
    [
        {**a_pdf(), "data": "not base64!"},
        {**a_pdf(), "media_type": "application/msword"},
        a_pdf(pdf_file(None)),  # a scan, with no text layer
    ],
    ids=["not-base64", "other-type", "no-text"],
)
def test_a_file_that_cannot_be_read_is_refused_and_nothing_is_kept(
    in_projects: tuple[Governance, Any], documentation: dict[str, str]
):
    governance, app = in_projects
    client = TestClient(app)
    started = client.post("/api/conversations", headers=JSON_HEADERS).json()

    response = turn(client, started["conversation_id"], "hello", documentation=documentation)

    assert response.status_code == 400
    assert list(governance.conductor.store.iter_envelopes()) == []
    assert governance.projects is not None
    assert governance.projects.documentation(started["project_id"]) == []


def test_a_file_is_read_for_checking_and_nothing_is_kept(in_projects: tuple[Governance, Any]):
    governance, app = in_projects
    client = TestClient(app)
    started = client.post("/api/conversations", headers=JSON_HEADERS).json()

    response = client.post("/api/documentation/extract", json=a_pdf(), headers=JSON_HEADERS)

    assert response.status_code == 200, response.json()
    assert DOCUMENT_TEXT in response.json()["text"]
    assert governance.projects is not None
    assert governance.projects.documentation(started["project_id"]) == []
    unread = client.post(
        "/api/documentation/extract", json=a_pdf(pdf_file(None)), headers=JSON_HEADERS
    )
    assert unread.status_code == 400
    not_base64 = {**a_pdf(), "data": "not base64!"}
    garbled = client.post("/api/documentation/extract", json=not_base64, headers=JSON_HEADERS)
    assert garbled.status_code == 400
    profile = governance.conductor.profile
    governance.conductor.profile = replace(profile, attached_documents="refused")
    refused = client.post("/api/documentation/extract", json=a_pdf(), headers=JSON_HEADERS)
    assert refused.status_code == 400


def test_a_document_needs_a_project_to_keep_it(delegating: tuple[Governance, Any]):
    governance, app = delegating
    client = TestClient(app)
    response = turn(client, start(client), "hello", documentation=a_document())
    assert response.status_code == 400
    assert "no project" in response.json()["detail"]
    assert list(governance.conductor.store.iter_envelopes()) == []


def test_a_project_serves_only_the_documents_it_holds(in_projects: tuple[Governance, Any]):
    _governance, app = in_projects
    client = TestClient(app)
    started = client.post("/api/conversations", headers=JSON_HEADERS).json()
    project_id = started["project_id"]
    assert client.get(f"/api/projects/{project_id}/documentation").json() == []
    none = client.get(f"/api/projects/{project_id}/documentation/{'0' * 64}")
    assert (none.status_code, none.json()["title"]) == (404, "No such document")
    unknown = client.get(f"/api/projects/{uuid.uuid4()}/documentation")
    assert (unknown.status_code, unknown.json()["title"]) == (404, "No such project")


def test_an_inventory_needs_a_project_to_keep_it(delegating: tuple[Governance, Any]):
    governance, app = delegating
    client = TestClient(app)
    response = turn(client, start(client), "hello", inventory=a_file_inventory("a.csv"))
    assert response.status_code == 400
    assert "no project" in response.json()["detail"]
    assert list(governance.conductor.store.iter_envelopes()) == []


def a_member_in_a_project(
    in_projects: tuple[Governance, Any], monkeypatch: pytest.MonkeyPatch
) -> tuple[TestClient, ProjectStorage, str]:
    governance, app = in_projects
    store = governance.projects
    assert store is not None
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    monkeypatch.setattr(governance, "role", lambda _project_id, _principal: Role.MEMBER)
    return TestClient(app), store, project_id


def test_a_member_attaches_a_document_outside_a_turn(
    in_projects: tuple[Governance, Any], monkeypatch: pytest.MonkeyPatch
):
    client, store, project_id = a_member_in_a_project(in_projects, monkeypatch)
    url = f"/api/projects/{project_id}/documentation"

    added = client.post(url, json=a_document())

    assert added.status_code == 201, added.json()
    [listed] = added.json()
    assert listed["documentation_name"] == "protocol.md"
    assert client.get(url).json() == added.json()
    text = client.get(f"{url}/{listed['documentation_digest']}")
    assert text.text == PROTOCOL
    event = store.events(project_id)[-1]
    assert event["event"] == "documentation_added"
    assert event["caused_by"] == f"POST {url}"


def test_a_member_attaches_a_pdf_outside_a_turn_and_the_project_keeps_the_file(
    in_projects: tuple[Governance, Any], monkeypatch: pytest.MonkeyPatch
):
    client, _store, project_id = a_member_in_a_project(in_projects, monkeypatch)
    url = f"/api/projects/{project_id}/documentation"

    added = client.post(url, json=a_pdf())

    assert added.status_code == 201, added.json()
    [listed] = added.json()
    assert listed["documentation_source_media_type"] == PDF
    original = client.get(f"{url}/{listed['documentation_digest']}?original")
    assert original.content == pdf_file()


def test_a_document_that_may_hold_personal_data_is_kept_only_once_confirmed(
    in_projects: tuple[Governance, Any], monkeypatch: pytest.MonkeyPatch
):
    client, store, project_id = a_member_in_a_project(in_projects, monkeypatch)
    url = f"/api/projects/{project_id}/documentation"
    contact = a_document("Questions to jane.doe@example.org about the cores.", "contact.md")

    held = client.post(url, json=contact)

    assert held.status_code == 409, held.json()
    assert held.json()["type"].endswith("/documentation-held")
    kinds = held.json()["kinds"]
    assert kinds
    assert "jane.doe" not in held.text
    assert store.documentation(project_id) == []
    kept = client.post(url, json={**contact, "confirmed": kinds})
    assert kept.status_code == 201, kept.json()
    assert [d["documentation_name"] for d in kept.json()] == ["contact.md"]


@pytest.mark.parametrize(
    "body",
    [
        ["protocol.md"],
        {"name": "protocol.md", "media_type": "text/markdown"},
        {**a_document(), "data": "AAAA"},
        {"name": "plan.pdf", "media_type": PDF, "data": "not base64!"},
        {**a_document(), "confirmed": "email address"},
        a_document(" ", "blank.md"),
        a_document("Cores", "data.csv") | {"media_type": "text/csv"},
        a_document("Cores", "folder/protocol.md"),
    ],
)
def test_a_document_the_project_would_not_keep_is_refused_and_leaves_no_trace(
    in_projects: tuple[Governance, Any], monkeypatch: pytest.MonkeyPatch, body: Any
):
    client, store, project_id = a_member_in_a_project(in_projects, monkeypatch)
    before = store.events(project_id)

    refused = client.post(f"/api/projects/{project_id}/documentation", json=body)

    assert refused.status_code == 400, refused.json()
    assert store.events(project_id) == before


def test_a_document_for_a_project_that_is_not_there_is_refused(in_projects: tuple[Governance, Any]):
    _, app = in_projects

    unknown = TestClient(app).post(f"/api/projects/{uuid.uuid4()}/documentation", json=a_document())

    assert unknown.status_code == 404


def test_someone_with_no_part_in_the_project_cannot_attach_a_document(
    in_projects: tuple[Governance, Any], monkeypatch: pytest.MonkeyPatch
):
    client, store, project_id = a_member_in_a_project(in_projects, monkeypatch)
    governance, _ = in_projects
    monkeypatch.setattr(governance, "role", lambda _project_id, _principal: None)

    forbidden = client.post(f"/api/projects/{project_id}/documentation", json=a_document())

    assert forbidden.status_code == 404
    assert store.documentation(project_id) == []
