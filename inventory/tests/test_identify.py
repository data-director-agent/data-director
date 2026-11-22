"""fido identifies formats against the PRONOM release pinned in `dd_inventory/pronom/`, and the
extension fallback takes over when the pinned copy cannot be trusted
(docs/specs/dependencies.md)."""

from __future__ import annotations

import json
import re
import shutil
from importlib.resources import files
from pathlib import Path

import pytest

from dd_inventory import identify
from dd_inventory.identify import (
    ExtensionIdentifier,
    FidoIdentifier,
    PinnedSignatures,
    default_identifier,
)

PINNED = Path(str(files("dd_inventory") / "pronom"))
MANIFEST = json.loads((PINNED / "manifest.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def fido() -> FidoIdentifier:
    return FidoIdentifier()


def test_the_pinned_files_match_the_manifest() -> None:
    pinned = PinnedSignatures.load()
    assert pinned.pronom_version == MANIFEST["pronom_version"]
    assert pinned.formats.startswith(b"<formats")
    assert pinned.container_date == MANIFEST["container"]["date"]


def test_the_identifier_names_the_pinned_release(fido: FidoIdentifier) -> None:
    named = re.search(r"PRONOM signatures v(\d+)", fido.description)
    assert named is not None
    assert int(named.group(1)) == MANIFEST["pronom_version"]
    assert MANIFEST["container"]["date"] in fido.description


@pytest.mark.parametrize(
    ("name", "content", "puid"),
    [
        # Research formats added to PRONOM after v109, the release fido ships.
        ("mesh.vtk", b"# vtk DataFile Version 2.0\nmesh\nASCII\n", "fmt/2011"),
        ("run.bag", b"#ROSBAG V2.0\n" + bytes(64), "fmt/2093"),
    ],
)
def test_a_format_added_after_fidos_own_release_is_identified(
    fido: FidoIdentifier, tmp_path: Path, name: str, content: bytes, puid: str
) -> None:
    path = tmp_path / name
    path.write_bytes(content)
    assert puid in fido.identify(path).pronom_ids


def _pinned_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    copy = tmp_path / "dd_inventory" / "pronom"
    shutil.copytree(PINNED, copy)
    monkeypatch.setattr(identify, "files", lambda _package: copy.parent)
    return copy


def test_a_pinned_file_that_does_not_match_its_hash_is_not_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    copy = _pinned_copy(tmp_path, monkeypatch)
    container = copy / MANIFEST["container"]["file"]
    container.write_bytes(container.read_bytes() + b"\n")
    identifier, unavailable = default_identifier()
    assert isinstance(identifier, ExtensionIdentifier)
    assert unavailable is not None
    assert MANIFEST["container"]["file"] in unavailable


def test_a_missing_pinned_file_falls_back_to_extensions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    copy = _pinned_copy(tmp_path, monkeypatch)
    (copy / MANIFEST["formats"]["file"]).unlink()
    identifier, unavailable = default_identifier()
    assert isinstance(identifier, ExtensionIdentifier)
    assert unavailable is not None
