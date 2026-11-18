"""A local install describes a folder on its own machine, read only and only under the folders
`DD_INVENTORY_FOLDERS` names; the shared deployment names none (docs/specs/projects.md)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from starlette.testclient import TestClient
from support import JSON_HEADERS, configure_env, dist_dir, new_governance

from dd_app import folder_scan
from dd_app.app import Links, build_app
from dd_app.folder_scan import FolderRefusedError, FolderRoots
from dd_app.governance import Governance
from dd_harness.server import LOOPBACK
from dd_sdk.contract.models import FileInventory
from dd_sdk.credentials import ConfigError


@pytest.fixture
def governance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Governance]:
    configure_env(monkeypatch, tmp_path)
    yield from new_governance()


@pytest.fixture
def data(tmp_path: Path) -> Path:
    """A dataset with a subfolder, a hidden folder, a file, and a link out of it."""
    root = tmp_path / "data"
    (root / "cores" / "site-a").mkdir(parents=True)
    (root / ".cache").mkdir()
    (root / "cores" / "depths.csv").write_text("depth,site\n1,a\n", encoding="utf-8")
    (root / "README.txt").write_text("cores\n", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("not this\n", encoding="utf-8")
    (root / "elsewhere").symlink_to(outside, target_is_directory=True)
    return root


@pytest.fixture
def roots(data: Path) -> FolderRoots:
    found = folder_scan.from_env({folder_scan.VARIABLE: str(data)}, "127.0.0.1", LOOPBACK)
    assert found is not None
    return found


def client_for(governance: Governance, tmp_path: Path, roots: FolderRoots | None) -> TestClient:
    return TestClient(build_app(governance, dist_dir(tmp_path), links=Links(folder_roots=roots)))


def test_listing_gives_subfolders_only_skipping_hidden_ones_and_links(roots: FolderRoots) -> None:
    (name,) = roots.names
    assert roots.subfolders(name) == ["cores"]
    assert roots.subfolders(name, "cores") == ["site-a"]


@pytest.mark.parametrize("path", ["..", "../outside", "cores/../..", "/etc", "elsewhere"])
def test_a_folder_outside_the_listed_ones_is_refused(roots: FolderRoots, path: str) -> None:
    (name,) = roots.names
    with pytest.raises(FolderRefusedError):
        roots.subfolders(name, path)
    with pytest.raises(FolderRefusedError):
        roots.describe(name, path)


def test_an_unknown_root_or_a_file_is_refused(roots: FolderRoots) -> None:
    (name,) = roots.names
    with pytest.raises(FolderRefusedError):
        roots.resolve("not-listed")
    with pytest.raises(FolderRefusedError):
        roots.resolve(name, "README.txt")


def test_describing_a_listed_folder_gives_its_inventory(
    governance: Governance, tmp_path: Path, roots: FolderRoots
) -> None:
    client = client_for(governance, tmp_path, roots)
    (name,) = roots.names
    assert client.get("/api/folders").json() == {"roots": [name]}
    listed = client.get("/api/folders", params={"root": name, "path": "cores"}).json()
    assert listed["folders"] == ["site-a"]

    found = client.post(
        "/api/folders/inventory", json={"root": name, "path": "cores"}, headers=JSON_HEADERS
    )
    assert found.status_code == 200, found.json()
    inventory = FileInventory.model_validate(found.json())
    assert [f.file_path for f in inventory.inventory_files] == ["depths.csv"]


def test_a_refused_folder_answers_not_found(
    governance: Governance, tmp_path: Path, roots: FolderRoots
) -> None:
    client = client_for(governance, tmp_path, roots)
    (name,) = roots.names
    listed = client.get("/api/folders", params={"root": name, "path": ".."})
    assert listed.status_code == 404
    described = client.post(
        "/api/folders/inventory", json={"root": name, "path": "elsewhere"}, headers=JSON_HEADERS
    )
    assert described.status_code == 404


def test_without_listed_folders_nothing_is_offered(governance: Governance, tmp_path: Path) -> None:
    client = client_for(governance, tmp_path, None)
    assert client.get("/api/about").json()["server_folders"] is False
    assert client.get("/api/folders").status_code == 404
    found = client.post("/api/folders/inventory", json={"root": "x"}, headers=JSON_HEADERS)
    assert found.status_code == 404


def test_about_says_folders_are_offered(
    governance: Governance, tmp_path: Path, roots: FolderRoots
) -> None:
    assert client_for(governance, tmp_path, roots).get("/api/about").json()["server_folders"]


def test_an_app_beyond_loopback_may_not_list_folders(data: Path) -> None:
    with pytest.raises(ConfigError):
        folder_scan.from_env({folder_scan.VARIABLE: str(data)}, "0.0.0.0", LOOPBACK)
    assert folder_scan.from_env({}, "0.0.0.0", LOOPBACK) is None


@pytest.mark.parametrize("entry", ["relative/path", "/no/such/folder"])
def test_a_listed_folder_must_be_an_absolute_existing_folder(entry: str) -> None:
    with pytest.raises(ConfigError):
        folder_scan.from_env({folder_scan.VARIABLE: entry}, "127.0.0.1", LOOPBACK)


def test_folders_with_one_name_are_told_apart(tmp_path: Path) -> None:
    a, b = tmp_path / "a" / "data", tmp_path / "b" / "data"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    found = folder_scan.from_env(
        {folder_scan.VARIABLE: os.pathsep.join([str(a), str(b)])}, "localhost", LOOPBACK
    )
    assert found is not None
    assert len(set(found.names)) == 2
    assert {found.resolve(n) for n in found.names} == {a.resolve(), b.resolve()}
