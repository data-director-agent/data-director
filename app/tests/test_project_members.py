"""A project's members through the app's server (docs/specs/projects.md, Roles and invariants 16,
17 and 19; #391): an owner lists, adds, re-roles and removes members; a member may only leave;
what the page may offer is said by the server; and a refused change is a `409` naming why."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from support import JSON_HEADERS, OTHER, check_fixture, configure_env, dist_dir, new_governance

from dd_app.app import build_app
from dd_app.governance import CREATED_BY_ROUTE, Governance
from dd_app.problems import ProblemDetails
from dd_app.project_service import ProjectService
from dd_app.routes.members import ProjectMembers
from dd_harness.projects import MEMBER_ADDED
from dd_harness.storage import ProjectStorage
from dd_harness.testing import SAMPLE_ID, TEST_PRINCIPAL, FakeOrcidRegistry, sample_record

COLLEAGUE_ID = "0000-0002-1694-233X"
COLLEAGUE = f"https://orcid.org/{COLLEAGUE_ID}"
SINCE = "2026-01-01T00:00:00+00:00"


@pytest.fixture
def governance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Governance]:
    configure_env(monkeypatch, tmp_path)
    yield from new_governance()


@pytest.fixture
def registry() -> FakeOrcidRegistry:
    return FakeOrcidRegistry(
        issuer="https://orcid.org", records={SAMPLE_ID: sample_record(host="orcid.org")}
    )


@pytest.fixture
def client(governance: Governance, tmp_path: Path, registry: FakeOrcidRegistry) -> TestClient:
    return TestClient(
        build_app(governance, dist_dir(tmp_path), orcid_transport=registry.transport())
    )


@pytest.fixture
def store(governance: Governance) -> ProjectStorage:
    assert governance.projects is not None
    return governance.projects


@pytest.fixture
def owned(store: ProjectStorage) -> str:
    """A project the signed-in person created, and so owns."""
    return store.create(acted_for=TEST_PRINCIPAL, caused_by=CREATED_BY_ROUTE, title="Soil")


@pytest.fixture
def joined(store: ProjectStorage) -> str:
    """A project someone else owns, to which they added the signed-in person as a member."""
    project_id = store.create(acted_for=OTHER, caused_by=CREATED_BY_ROUTE, title="Peat")
    store.add_member(project_id, TEST_PRINCIPAL.principal_id, acted_for=OTHER, caused_by="test")
    return project_id


def path(project_id: str) -> str:
    return f"/api/projects/{project_id}/members"


def fixed(body: Any) -> Any:
    """`body` with each member's `member_since` fixed, for a fixture."""
    return {**body, "members": [{**m, "member_since": SINCE} for m in body["members"]]}


def listed(body: Any) -> list[tuple[str, str]]:
    return [(m["member_id"], m["role"]) for m in body["members"]]


def test_an_owner_sees_the_members_and_may_manage_them(client: TestClient, owned: str) -> None:
    response = client.get(path(owned))
    assert response.status_code == 200
    body = response.json()
    assert listed(body) == [(TEST_PRINCIPAL.principal_id, "owner")]
    assert body["your_role"] == "owner"
    assert body["may_manage"] is True
    # The last owner may neither leave nor be removed.
    assert body["may_leave"] is False
    assert body["members"][0]["is_you"] is True
    assert body["members"][0]["removable"] is False


def test_an_owner_adds_a_member_by_bare_orcid_id(
    client: TestClient, store: ProjectStorage, owned: str
) -> None:
    added = client.post(path(owned), json={"member": f" {COLLEAGUE_ID} "})
    assert added.status_code == 201
    body = added.json()
    assert listed(body) == [(TEST_PRINCIPAL.principal_id, "owner"), (COLLEAGUE, "member")]
    assert body["members"][1]["removable"] is True
    assert [m["role_changeable"] for m in body["members"]] == [False, True]
    check_fixture("project-members.json", fixed(body), model=ProjectMembers)
    event = store.events(owned)[-1]
    assert event["event"] == MEMBER_ADDED
    assert event["caused_by"] == f"POST /api/projects/{owned}/members"


def test_an_owner_changes_a_role_and_then_may_leave(client: TestClient, owned: str) -> None:
    client.post(path(owned), json={"member": COLLEAGUE, "role": "member"})
    changed = client.patch(path(owned), json={"member_id": COLLEAGUE, "role": "owner"})
    assert changed.status_code == 200
    assert listed(changed.json())[1] == (COLLEAGUE, "owner")
    assert changed.json()["may_leave"] is True
    left = client.delete(
        path(owned), params={"member_id": TEST_PRINCIPAL.principal_id}, headers=JSON_HEADERS
    )
    assert left.status_code == 204
    assert client.get(path(owned)).status_code == 404


def test_a_removed_member_can_no_longer_read_the_project(
    client: TestClient, store: ProjectStorage, owned: str
) -> None:
    client.post(path(owned), json={"member": COLLEAGUE})
    removed = client.delete(path(owned), params={"member_id": COLLEAGUE}, headers=JSON_HEADERS)
    assert removed.status_code == 200
    assert listed(removed.json()) == [(TEST_PRINCIPAL.principal_id, "owner")]
    assert [m["member_id"] for m in store.members(owned)] == [TEST_PRINCIPAL.principal_id]


def test_a_member_may_read_and_leave_but_not_manage(
    client: TestClient, store: ProjectStorage, joined: str
) -> None:
    body = client.get(path(joined)).json()
    assert body["your_role"] == "member"
    assert body["may_manage"] is False
    assert body["may_leave"] is True
    assert [(m["is_you"], m["removable"]) for m in body["members"]] == [
        (False, False),
        (True, True),
    ]
    before = store.events(joined)
    forbidden = [
        client.post(path(joined), json={"member": COLLEAGUE}),
        client.patch(path(joined), json={"member_id": OTHER.principal_id, "role": "member"}),
        client.delete(path(joined), params={"member_id": OTHER.principal_id}, headers=JSON_HEADERS),
    ]
    assert [r.status_code for r in forbidden] == [403, 403, 403]
    assert all(r.json()["type"].endswith("project-action-forbidden") for r in forbidden)
    assert store.events(joined) == before
    left = client.delete(
        path(joined), params={"member_id": TEST_PRINCIPAL.principal_id}, headers=JSON_HEADERS
    )
    assert left.status_code == 204
    assert client.get(path(joined)).status_code == 404


def test_someone_who_is_not_a_member_is_answered_as_for_no_project(
    client: TestClient, store: ProjectStorage
) -> None:
    theirs = store.create(acted_for=OTHER, caused_by=CREATED_BY_ROUTE)
    assert client.get(path(theirs)).status_code == 404
    assert client.post(path(theirs), json={"member": COLLEAGUE}).status_code == 404
    assert (
        client.delete(
            path(theirs), params={"member_id": OTHER.principal_id}, headers=JSON_HEADERS
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    ("request_", "slug"),
    [
        (
            (
                "delete",
                {"params": {"member_id": TEST_PRINCIPAL.principal_id}, "headers": JSON_HEADERS},
            ),
            "last-owner",
        ),
        (
            ("patch", {"json": {"member_id": TEST_PRINCIPAL.principal_id, "role": "member"}}),
            "last-owner",
        ),
        (("post", {"json": {"member": TEST_PRINCIPAL.principal_id}}), "already-member"),
        (("patch", {"json": {"member_id": COLLEAGUE, "role": "owner"}}), "not-a-member"),
    ],
)
def test_a_change_the_rules_refuse_is_409_naming_why(
    client: TestClient,
    store: ProjectStorage,
    owned: str,
    request_: tuple[str, dict[str, Any]],
    slug: str,
) -> None:
    method, kwargs = request_
    before = store.events(owned)
    refused = getattr(client, method)(path(owned), **kwargs)
    assert refused.status_code == 409
    assert refused.json()["type"].endswith(slug)
    assert store.events(owned) == before
    if slug == "last-owner" and method == "delete":
        check_fixture("project-members-last-owner.json", refused.json(), model=ProblemDetails)


@pytest.mark.parametrize(
    "body", [{"member": "not an identifier"}, {"member": COLLEAGUE, "role": "admin"}, {}]
)
def test_a_malformed_addition_is_400(client: TestClient, owned: str, body: Any) -> None:
    response = client.post(path(owned), json=body)
    assert response.status_code == 400


def test_removing_names_the_member(client: TestClient, owned: str) -> None:
    response = client.delete(path(owned), headers=JSON_HEADERS)
    assert response.status_code == 400


def test_a_member_is_named_by_the_name_they_kept_from_orcid(client: TestClient, owned: str) -> None:
    kept = client.put(
        f"/api/projects/{owned}/researchers/me",
        json={"keep": {"sections": ["researcher_name"]}},
    )
    assert kept.status_code == 201
    name = kept.json()[0]["researcher_name"]
    (member,) = client.get(path(owned)).json()["members"]
    assert member["researcher_name"] == name


def test_a_member_who_kept_no_name_is_named_from_their_public_record(
    client: TestClient, owned: str, registry: FakeOrcidRegistry
) -> None:
    assert client.post(path(owned), json={"member": COLLEAGUE}).status_code == 201
    me, colleague = client.get(path(owned)).json()["members"]
    assert me["public_name"]
    assert "researcher_name" not in me
    # ORCID has no public name for the colleague, so they are shown by their iD.
    assert "public_name" not in colleague
    # Names are held for a while, not read again for every answer.
    before = registry.requests
    client.get(path(owned))
    assert registry.requests == before


def test_a_kept_name_needs_no_lookup(
    client: TestClient, owned: str, registry: FakeOrcidRegistry
) -> None:
    kept = client.put(
        f"/api/projects/{owned}/researchers/me",
        json={"keep": {"sections": ["researcher_name"]}},
    )
    assert kept.status_code == 201
    before = registry.requests
    (member,) = client.get(path(owned)).json()["members"]
    assert registry.requests == before
    assert "public_name" not in member
    assert member["record"]["orcid_id"] == member["member_id"]


def test_members_are_listed_when_orcid_is_down(
    client: TestClient, owned: str, registry: FakeOrcidRegistry
) -> None:
    registry.failing = 503
    response = client.get(path(owned))
    assert response.status_code == 200
    (member,) = response.json()["members"]
    assert "public_name" not in member
    assert "researcher_name" not in member


def test_a_former_members_record_is_still_listed(
    client: TestClient, governance: Governance, store: ProjectStorage, joined: str
) -> None:
    kept = client.put(
        f"/api/projects/{joined}/researchers/me",
        json={"keep": {"sections": ["researcher_name"]}},
    )
    assert kept.status_code == 201
    store.remove_member(joined, TEST_PRINCIPAL.principal_id, acted_for=OTHER, caused_by="test")
    # The person removed may no longer read the project; its owner sees what they kept.
    body = ProjectService.over(governance).members.members(joined, OTHER)
    assert [m["member_id"] for m in body["members"]] == [OTHER.principal_id]
    assert [r["orcid_id"] for r in body["former_researchers"]] == [TEST_PRINCIPAL.principal_id]


def test_a_deleted_project_takes_no_new_member(client: TestClient, owned: str) -> None:
    assert client.request("DELETE", f"/api/projects/{owned}", json={"title": "Soil"}).is_success
    assert client.post(path(owned), json={"member": COLLEAGUE}).status_code == 409
