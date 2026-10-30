"""The inventory command describes a dataset's files without their content (ADR-0034)."""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from dd_inventory import cli, identify, make_inventory, scan
from dd_inventory.identify import ExtensionIdentifier, FidoUnavailableError
from dd_inventory.tables import TableError
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import FileInventory

Inventory = dict[str, Any]
FIXTURE = Path(__file__).parent / "data" / "soil-survey"


@pytest.fixture(scope="module")
def inventory() -> Inventory:
    return make_inventory(FIXTURE)


def _by_path(inventory: Inventory) -> dict[str, dict[str, Any]]:
    return {f["file_path"]: f for f in inventory["inventory_files"]}


@pytest.fixture
def dataset(tmp_path: Path) -> Path:
    root = tmp_path / "soil-survey"
    shutil.copytree(FIXTURE, root)
    return root


def test_the_inventory_is_a_core_file_inventory(inventory: Inventory) -> None:
    assert ClassSchema.of(FileInventory).errors(inventory) == []
    FileInventory.model_validate(inventory)
    assert inventory["inventory_tool"] == "dd-inventory"
    assert inventory["inventory_identified_with"].startswith("fido 1.6.1 with PRONOM signatures v")


def test_every_file_is_listed_by_relative_path_in_order_with_its_size_and_digest(
    inventory: Inventory,
) -> None:
    files = inventory["inventory_files"]
    paths = [f["file_path"] for f in files]
    assert paths == sorted(paths)
    assert set(paths) == {
        "README.md",
        "data/readings.csv",
        "data/sites.tsv",
        "docs/protocol.pdf",
        "docs/site-map.png",
    }
    for f in files:
        data = (FIXTURE / f["file_path"]).read_bytes()
        assert f["file_size"] == len(data)
        assert f["file_sha256"] == hashlib.sha256(data).hexdigest()


def test_no_file_content_and_no_absolute_path_is_written(inventory: Inventory) -> None:
    text = json.dumps(inventory)
    assert str(FIXTURE.resolve()) not in text
    assert "Crookes" not in text  # a value from sites.tsv
    assert "nitrate" in text  # a field name is a fact about the table, and is kept


def test_formats_with_a_byte_signature_are_identified_from_content(inventory: Inventory) -> None:
    files = _by_path(inventory)
    assert files["docs/protocol.pdf"]["file_pronom_ids"] == ["fmt/18"]  # PDF 1.4
    assert files["docs/protocol.pdf"]["file_identified_by"] == "signature"
    assert files["docs/protocol.pdf"]["file_media_type"] == "application/pdf"
    assert files["docs/site-map.png"]["file_identified_by"] == "signature"
    assert files["data/readings.csv"]["file_pronom_ids"] == ["x-fmt/18"]
    assert files["data/readings.csv"]["file_identified_by"] == "extension"


def test_an_ambiguous_match_keeps_every_candidate(dataset: Path) -> None:
    (dataset / "old-notes.doc").write_bytes(b"not a Word document")
    found = _by_path(make_inventory(dataset))["old-notes.doc"]
    assert found["file_identified_by"] == "extension"
    assert len(found["file_pronom_ids"]) > 1


def test_a_file_nothing_recognises_has_no_identifier(dataset: Path) -> None:
    (dataset / "readings.xyzzy").write_bytes(b"\x00\x01\x02")
    found = _by_path(make_inventory(dataset))["readings.xyzzy"]
    assert found["file_pronom_ids"] == []
    assert found["file_identified_by"] == "none"
    assert "file_media_type" not in found


def test_a_table_has_its_fields_inferred(inventory: Inventory) -> None:
    files = _by_path(inventory)
    assert files["data/readings.csv"]["file_fields"] == [
        {"name": "site", "field_type": "string"},
        {"name": "sampled_on", "field_type": "date"},
        {"name": "ph", "field_type": "number"},
        {"name": "nitrate_mg_kg", "field_type": "number"},
    ]
    assert [f["name"] for f in files["data/sites.tsv"]["file_fields"]] == [
        "site",
        "latitude",
        "longitude",
        "name",
    ]
    assert "file_fields" not in files["docs/protocol.pdf"]


def test_a_table_whose_fields_cannot_be_inferred_is_listed_and_said_so(
    dataset: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unreadable(path: Path) -> list[dict[str, Any]]:
        raise TableError(f"{path.name}: not a table")

    monkeypatch.setattr(scan, "table_fields", unreadable)
    (dataset / "data" / "broken.csv").write_bytes(b"\xff\xfe\x00\x00" * 4)
    made = make_inventory(dataset)
    assert "data/broken.csv" in _by_path(made)
    assert "file_fields" not in _by_path(made)["data/broken.csv"]
    assert any("data/broken.csv" in note for note in made["inventory_limitations"])


def test_hidden_files_and_links_are_skipped_and_counted(dataset: Path) -> None:
    (dataset / ".DS_Store").write_bytes(b"\x00")
    (dataset / ".git").mkdir()
    (dataset / ".git" / "config").write_text("[core]\n")
    (dataset / "elsewhere.csv").symlink_to(FIXTURE / "data" / "readings.csv")
    made = make_inventory(dataset)
    paths = set(_by_path(made))
    assert not {p for p in paths if p.startswith(".") or "/." in p}
    assert "elsewhere.csv" not in paths
    notes = " ".join(made["inventory_limitations"])
    assert "2 hidden" in notes
    assert "1 symbolic link" in notes


def test_without_fido_formats_are_guessed_from_extensions(
    dataset: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable() -> None:
        raise FidoUnavailableError("fido could not be loaded: no signatures")

    monkeypatch.setattr(identify, "FidoIdentifier", unavailable)
    made = make_inventory(dataset, now=datetime(2026, 10, 30, tzinfo=UTC))
    assert ClassSchema.of(FileInventory).errors(made) == []
    assert made["inventory_identified_with"] == ExtensionIdentifier.description
    assert made["inventory_made_at"] == "2026-10-30T00:00:00+00:00"
    pdf = _by_path(made)["docs/protocol.pdf"]
    assert pdf == {**pdf, "file_pronom_ids": [], "file_identified_by": "extension"}
    assert pdf["file_media_type"] == "application/pdf"
    assert "fido could not be loaded" in made["inventory_limitations"][0]


def test_the_command_writes_the_inventory_to_a_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "inventory.json"
    assert cli.main([str(FIXTURE), "-o", str(out)]) == cli.EXIT_OK
    assert json.loads(out.read_text("utf-8"))["schema_class"] == "FileInventory"
    assert capsys.readouterr().out == ""


def test_the_command_writes_to_standard_output_by_default(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main([str(FIXTURE)]) == cli.EXIT_OK
    assert len(json.loads(capsys.readouterr().out)["inventory_files"]) == 5


def test_the_command_refuses_a_root_that_is_not_a_folder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main([str(tmp_path / "missing")]) == cli.EXIT_USAGE
    assert "is not a folder" in capsys.readouterr().err
    with pytest.raises(NotADirectoryError):
        make_inventory(FIXTURE / "README.md")


WORD_CONTENT_TYPES = (
    '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/'
    'content-types"><Override PartName="/word/document.xml" ContentType="application/'
    'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'
)


def test_a_zip_based_format_is_identified_by_its_container_signature(dataset: Path) -> None:
    with zipfile.ZipFile(dataset / "docs" / "consent-form.docx", "w") as docx:
        docx.writestr("[Content_Types].xml", WORD_CONTENT_TYPES)
        docx.writestr("word/document.xml", '<?xml version="1.0"?><document/>')
    found = _by_path(make_inventory(dataset))["docs/consent-form.docx"]
    assert found["file_identified_by"] == "container"
    assert found["file_pronom_ids"] == ["fmt/412"]  # Microsoft Word for Windows 2007 onwards
