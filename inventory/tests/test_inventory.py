"""The inventory command describes a dataset's files without their content
(docs/specs/projects.md)."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import types
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from packaging.version import Version

from dd_inventory import FileProgress, cli, identify, make_inventory, make_inventory_of, scan
from dd_inventory.identify import ExtensionIdentifier, FidoUnavailableError
from dd_inventory.tables import TableError
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import FileInventory, inventory_part_problems

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


def test_missing_value_markers_do_not_make_a_number_a_string(dataset: Path) -> None:
    # #1070: `NA` gaps in a numeric column, and a column empty for the whole sample.
    rows = ["ts,rh,pm25"] + [f"{i},{'NA' if i % 7 == 0 else 50.5},," for i in range(1100)]
    rows += [f"{i},51.5,{i / 10}" for i in range(1100, 1200)]
    (dataset / "data" / "loggers.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    made = make_inventory(dataset)
    types_ = {f["name"]: f["field_type"] for f in _by_path(made)["data/loggers.csv"]["file_fields"]}
    assert types_["rh"] == "number"
    assert types_["pm25"] == "any"
    said = [n for n in made["inventory_limitations"] if "data/loggers.csv" in n]
    assert any("`NA`" in n for n in said)
    assert any("`pm25`" in n for n in said)


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


def test_progress_is_reported_once_per_file_in_order(inventory: Inventory) -> None:
    seen: list[FileProgress] = []
    made = make_inventory(FIXTURE, on_file=seen.append)
    files = inventory["inventory_files"]
    assert [(p.path, p.size) for p in seen] == [(f["file_path"], f["file_size"]) for f in files]
    assert [p.done for p in seen] == list(range(1, len(files) + 1))
    assert {p.total for p in seen} == {len(files)}
    assert made["inventory_files"] == files


def test_a_file_that_cannot_be_read_still_reports_progress(
    dataset: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = scan.sha256

    def flaky(path: Path) -> str:
        if path.name == "sites.tsv":
            raise PermissionError(13, "Permission denied")
        return real(path)

    monkeypatch.setattr(scan, "sha256", flaky)
    seen: list[FileProgress] = []
    made = make_inventory(dataset, on_file=seen.append)
    assert "data/sites.tsv" not in _by_path(made)
    assert FileProgress("data/sites.tsv", 0, 3, 5) in seen
    assert [p.done for p in seen] == [1, 2, 3, 4, 5]


def test_a_native_inventory_names_no_runtime(inventory: Inventory) -> None:
    assert inventory["inventory_tool"] == "dd-inventory"
    assert inventory["inventory_tool_version"] == scan.tool_version()
    assert Version(inventory["inventory_tool_version"]).local is None


def test_a_runtime_passed_in_is_a_local_version_label() -> None:
    made = make_inventory(FIXTURE, runtime="pyodide.314.0.7")
    assert made["inventory_tool"] == "dd-inventory"
    assert made["inventory_tool_version"] == f"{scan.tool_version()}+pyodide.314.0.7"
    assert Version(made["inventory_tool_version"]).local == "pyodide.314.0.7"
    assert ClassSchema.of(FileInventory).errors(made) == []


def test_under_pyodide_the_runtime_is_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "emscripten")
    monkeypatch.setitem(sys.modules, "pyodide", types.SimpleNamespace(__version__="314.0.7"))
    made = make_inventory(FIXTURE)
    assert Version(made["inventory_tool_version"]).local == "pyodide.314.0.7"
    assert make_inventory(FIXTURE, runtime=None)["inventory_tool_version"] == scan.tool_version()


def test_a_runtime_version_is_made_a_valid_label(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "emscripten")
    monkeypatch.setitem(sys.modules, "pyodide", types.SimpleNamespace(__version__="0.29.0-dev"))
    assert scan.detect_runtime() == "pyodide.0.29.0.dev"
    monkeypatch.setitem(sys.modules, "pyodide", None)  # cannot be imported
    assert scan.detect_runtime() == "emscripten"


def test_several_folders_make_one_inventory_with_a_part_for_each(
    dataset: Path, tmp_path: Path
) -> None:
    other = tmp_path / "instrument"
    other.mkdir()
    (other / "run1.csv").write_text("t,v\n1,2\n", encoding="utf-8")
    seen: list[FileProgress] = []
    inventory = make_inventory_of(
        {"lab": dataset, "instrument": other},
        now=datetime(2026, 11, 1, tzinfo=UTC),
        on_file=seen.append,
    )
    assert ClassSchema.of(FileInventory).errors(inventory) == []
    assert inventory_part_problems(inventory) == []
    FileInventory.model_validate(inventory)
    paths = [f["file_path"] for f in inventory["inventory_files"]]
    assert paths == sorted(paths)
    assert "instrument/run1.csv" in paths
    alone = make_inventory(dataset, now=datetime(2026, 11, 1, tzinfo=UTC))
    assert {p for p in paths if p.startswith("lab/")} == {
        "lab/" + f["file_path"] for f in alone["inventory_files"]
    }
    assert [p["part_folder"] for p in inventory["inventory_parts"]] == ["instrument", "lab"]
    assert all(
        s.startswith(("In instrument: ", "In lab: ")) for s in inventory["inventory_limitations"]
    )
    assert [p.done for p in seen] == list(range(1, len(paths) + 1))
    assert {p.total for p in seen} == {len(paths)}


@pytest.mark.parametrize("names", [["raw", "raw/2024"], ["a/../b", "c"], ["", "c"], ["/abs", "c"]])
def test_folder_names_that_overlap_or_climb_are_refused(names: list[str], dataset: Path) -> None:
    with pytest.raises(ValueError):
        make_inventory_of(dict(zip(names, [dataset, dataset], strict=True)))


def test_the_command_takes_several_folders_and_names_them(dataset: Path, tmp_path: Path) -> None:
    other = tmp_path / "copy" / "soil-survey"
    shutil.copytree(dataset, other)
    out = tmp_path / "inventory.json"
    # Two folders of the same name need names of their own.
    assert cli.main([str(dataset), str(other), "-o", str(out)]) == cli.EXIT_USAGE
    assert cli.main([str(dataset), str(other), "--as", "2024"]) == cli.EXIT_USAGE
    args = [str(dataset), str(other), "--as", "2024", "--as", "2025", "-o", str(out)]
    assert cli.main(args) == cli.EXIT_OK
    written = json.loads(out.read_text("utf-8"))
    assert [p["part_folder"] for p in written["inventory_parts"]] == ["2024", "2025"]
    assert ClassSchema.of(FileInventory).errors(written) == []


# The sample folder both runtimes describe: natively here, and under Pyodide in the browser
# bundle's parity check (inventory/browser/README.md), which compares the two slot by slot.
MIXED = Path(__file__).parent / "data" / "mixed"


@pytest.fixture(scope="module")
def mixed() -> Inventory:
    return make_inventory(MIXED)


def test_the_mixed_sample_is_a_core_file_inventory(mixed: Inventory) -> None:
    assert ClassSchema.of(FileInventory).errors(mixed) == []


def test_the_mixed_sample_needs_signature_container_and_extension(mixed: Inventory) -> None:
    files = _by_path(mixed)
    assert files["images/plot-map.png"]["file_identified_by"] == "signature"
    assert files["reports/report.docx"]["file_identified_by"] == "container"
    assert files["reports/report.docx"]["file_pronom_ids"] == ["fmt/412"]
    assert files["tables/plots.csv"]["file_identified_by"] == "extension"


def test_the_mixed_sample_has_a_misleading_extension(mixed: Inventory) -> None:
    misnamed = _by_path(mixed)["misnamed.csv"]
    assert misnamed["file_identified_by"] == "signature"
    assert misnamed["file_pronom_ids"] == _by_path(mixed)["images/plot-map.png"]["file_pronom_ids"]
    assert "file_fields" not in misnamed
    assert any("misnamed.csv" in note for note in mixed["inventory_limitations"])


def test_the_mixed_sample_has_tables_of_every_simple_field_type(mixed: Inventory) -> None:
    files = _by_path(mixed)
    for table in ("tables/plots.csv", "tables/nested/readings.tsv"):
        types_ = {f["field_type"] for f in files[table]["file_fields"]}
        assert types_ == {"integer", "number", "boolean", "date", "string"}


def test_the_mixed_sample_has_an_empty_file_and_hidden_ones_left_out(mixed: Inventory) -> None:
    files = _by_path(mixed)
    assert files["empty.txt"]["file_size"] == 0
    assert not any(part.startswith(".") for p in files for part in p.split("/"))
    assert (MIXED / ".DS_Store").is_file()
    assert (MIXED / ".hidden").is_dir()
