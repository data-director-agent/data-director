"""The inventory command flags possible personal data where it finds some, never what
(docs/specs/personal-data.md, #470)."""

from __future__ import annotations

import csv
import json
import re
import shutil
from pathlib import Path
from typing import Any

import pytest

from dd_inventory import cli, make_inventory, make_inventory_of
from dd_inventory.personal import (
    TEXT_LIMIT,
    TEXT_SUFFIXES,
    confidence_band,
    proportion_band,
)
from dd_inventory.tables import SAMPLE_ROWS
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
    ConfidenceBand,
    FileInventory,
    FindingTarget,
    PersonalDataKind,
    ProportionBand,
)

Inventory = dict[str, Any]
CORPUS = Path(__file__).parent / "data" / "disclosure"
LABELS: dict[str, Any] = json.loads((CORPUS / "labels.json").read_text(encoding="utf-8"))
VALUE_TARGETS = {FindingTarget.COLUMN.value, FindingTarget.TEXT.value}


# Summary values are values by design, checked by their own rules (test_summaries.py), so the
# findings are tested without them.
@pytest.fixture(scope="module")
def corpus() -> Inventory:
    return make_inventory(CORPUS, summaries=None)


@pytest.fixture(scope="module")
def unchecked() -> Inventory:
    return make_inventory(CORPUS, detector=None, summaries=None)


def _found(inventory: Inventory, file: str, target: str, column: str | None) -> set[str]:
    return {
        f["finding_kind"]
        for f in inventory["inventory_personal_data"]
        if f["finding_file"] == file
        and f["finding_target"] == target
        and f.get("finding_column") == column
    }


def test_an_inventory_with_findings_is_a_core_file_inventory(corpus: Inventory) -> None:
    assert corpus["inventory_personal_data"]
    assert ClassSchema.of(FileInventory).errors(corpus) == []
    FileInventory.model_validate(corpus)


@pytest.mark.parametrize(
    "case",
    [c for c in LABELS["personal_data"] if "needs" not in c],
    ids=lambda c: f"{c['file']}:{c.get('column', c.get('target'))}:{c['kind']}",
)
def test_each_labelled_direct_identifier_is_flagged_where_it_is(
    corpus: Inventory, case: dict[str, str]
) -> None:
    target = "column" if "column" in case else case["target"]
    assert case["kind"] in _found(corpus, case["file"], target, case.get("column"))


def test_a_clean_control_has_no_finding_from_its_values(corpus: Inventory) -> None:
    clean = set(LABELS["clean"])
    assert clean
    assert not [
        f
        for f in corpus["inventory_personal_data"]
        if f["finding_file"] in clean and f["finding_target"] in VALUE_TARGETS
    ]


def test_a_column_finding_says_how_much_was_examined_as_bands(corpus: Inventory) -> None:
    columns = [f for f in corpus["inventory_personal_data"] if f["finding_target"] == "column"]
    assert columns
    for f in columns:
        assert f["finding_proportion"] in {b.value for b in ProportionBand}
        assert f["finding_confidence"] in {b.value for b in ConfidenceBand}
        assert 0 < f["finding_examined"] <= SAMPLE_ROWS


def _sampled_values() -> set[str]:
    """Every value the check could have read: each sampled table cell and each text file's text."""
    values: set[str] = set()
    for path in CORPUS.rglob("*"):
        if path.suffix in {".csv", ".tsv"}:
            delimiter = "\t" if path.suffix == ".tsv" else ","
            with path.open(encoding="utf-8", newline="") as fh:
                rows = list(csv.reader(fh, delimiter=delimiter))[1 : SAMPLE_ROWS + 1]
            values |= {cell for row in rows for cell in row if cell.strip()}
        elif path.suffix in TEXT_SUFFIXES:
            values.add(path.read_text(encoding="utf-8"))
    return values


def _dumped(*inventories: object) -> str:
    """The inventories as JSON, without the time each was made: it is written whatever the data,
    and its digits would match short sampled values, such as `54`, by chance (#1145)."""
    return json.dumps(
        [
            {k: v for k, v in i.items() if k != "inventory_made_at"} if isinstance(i, dict) else i
            for i in inventories
        ],
        ensure_ascii=False,
    )


@pytest.mark.requirement("C2")
def test_no_sampled_value_nor_any_part_of_one_is_written(
    corpus: Inventory, unchecked: Inventory, tmp_path: Path
) -> None:
    """Invariant 1: what the check adds holds no value, nor a token of four or more characters
    from one. Paths and field names are written without the check too, and the check's own
    sentences and bands whatever the data, so those are not counted, nor is the time the
    inventory was made."""
    written = _dumped(corpus)
    enums = (PersonalDataKind, FindingTarget, ProportionBand)
    vocabulary = [e.value for kind in enums for e in kind]
    already = _dumped(unchecked, make_inventory(tmp_path, summaries=None), vocabulary)
    leaked = set()
    for value in _sampled_values():
        tokens = {value, *re.findall(r"[A-Za-z0-9@.+]{4,}", value)}
        leaked |= {t for t in tokens if t in written and t not in already}
    assert not leaked


@pytest.mark.requirement("C2")
def test_every_string_a_finding_holds_comes_from_a_closed_set(corpus: Inventory) -> None:
    """A finding names a kind, a band, the detector, a path or a column, and nothing else."""
    files = {f["file_path"] for f in corpus["inventory_files"]}
    folders = {"/".join(p.split("/")[:i]) + "/" for p in files for i in range(1, p.count("/") + 1)}
    columns = {fld["name"] for f in corpus["inventory_files"] for fld in f.get("file_fields", [])}
    allowed = {
        "finding_kind": {k.value for k in PersonalDataKind},
        "finding_file": files | folders,
        "finding_target": {t.value for t in FindingTarget},
        "finding_column": columns,
        "finding_proportion": {b.value for b in ProportionBand},
        "finding_confidence": {b.value for b in ConfidenceBand},
    }
    for finding in corpus["inventory_personal_data"]:
        for slot, value in finding.items():
            if slot in allowed:
                assert value in allowed[slot], (slot, finding)
            else:
                assert slot in {"finding_detector", "finding_examined"}, slot


def test_without_a_detector_the_findings_are_absent_not_empty(unchecked: Inventory) -> None:
    assert "inventory_personal_data" not in unchecked
    assert FileInventory.model_validate(unchecked).inventory_personal_data is None


def test_a_dataset_with_nothing_found_has_an_empty_list(tmp_path: Path) -> None:
    (tmp_path / "readings.csv").write_text("depth,ph\n" + "20,7.1\n" * 50, encoding="utf-8")
    made = make_inventory(tmp_path)
    assert made["inventory_personal_data"] == []
    assert FileInventory.model_validate(made).inventory_personal_data == []


def test_an_inventory_made_before_findings_still_validates_and_reads_as_unchecked(
    unchecked: Inventory,
) -> None:
    before = {k: v for k, v in unchecked.items() if k != "inventory_personal_data"}
    assert ClassSchema.of(FileInventory).errors(before) == []
    assert FileInventory.model_validate(before).inventory_personal_data is None


def test_the_check_says_what_it_looked_for_and_the_command_can_skip_it(
    corpus: Inventory, unchecked: Inventory
) -> None:
    assert len(corpus["inventory_limitations"]) > len(unchecked["inventory_limitations"]) - 1
    assert corpus["inventory_limitations"] != unchecked["inventory_limitations"]


def test_the_command_writes_no_findings_when_told_not_to_detect(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "inventory.json"
    assert cli.main([str(CORPUS / "direct"), "--no-detect", "-o", str(out)]) == 0
    assert "inventory_personal_data" not in json.loads(out.read_text(encoding="utf-8"))
    assert cli.main([str(CORPUS / "direct"), "-o", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["inventory_personal_data"]


def test_a_large_text_file_is_not_read_and_the_limitations_say_so(tmp_path: Path) -> None:
    (tmp_path / "small.txt").write_text("Write to someone@example.org.\n", encoding="utf-8")
    (tmp_path / "large.txt").write_text(
        "someone@example.org\n" * (TEXT_LIMIT // 10), encoding="utf-8"
    )
    made = make_inventory(tmp_path)
    assert {f["finding_file"] for f in made["inventory_personal_data"]} == {"small.txt"}
    plain = make_inventory(tmp_path, detector=None)
    assert len(made["inventory_limitations"]) - len(plain["inventory_limitations"]) == 1


def test_folder_and_file_names_are_checked_once_each(tmp_path: Path) -> None:
    for name in ("a.csv", "b.csv"):
        path = tmp_path / "addresses" / name
        path.parent.mkdir(exist_ok=True)
        path.write_text("depth\n20\n", encoding="utf-8")
    (tmp_path / "health-notes.md").write_text("Nothing here.\n", encoding="utf-8")
    places = [
        (f["finding_file"], f["finding_kind"])
        for f in make_inventory(tmp_path)["inventory_personal_data"]
        if f["finding_target"] == "file name"
    ]
    assert places.count(("addresses/", "direct identifier")) == 0  # "addresses" is not a keyword
    assert ("health-notes.md", "special category") in places
    assert len(places) == len(set(places))


def test_each_part_keeps_its_findings_under_its_name(tmp_path: Path) -> None:
    shutil.copytree(CORPUS / "direct", tmp_path / "direct")
    shutil.copytree(CORPUS / "summaries", tmp_path / "summaries")
    made = make_inventory_of({"people": tmp_path / "direct", "cohort": tmp_path / "summaries"})
    assert ClassSchema.of(FileInventory).errors(made) == []
    FileInventory.model_validate(made)
    for part in made["inventory_parts"]:
        assert all(
            f["finding_file"].startswith(part["part_folder"] + "/")
            for f in part["part_personal_data"]
        )
    assert made["inventory_personal_data"] == [
        f for p in made["inventory_parts"] for f in p["part_personal_data"]
    ]
    unchecked = make_inventory_of({"people": tmp_path / "direct"}, detector=None)
    assert "inventory_personal_data" not in unchecked
    assert "part_personal_data" not in unchecked["inventory_parts"][0]


@pytest.mark.parametrize(
    ("score", "band"),
    [(0.0, "low"), (0.49, "low"), (0.5, "medium"), (0.84, "medium"), (0.85, "high"), (1.0, "high")],
)
def test_a_score_falls_in_one_confidence_band(score: float, band: str) -> None:
    assert confidence_band(score) == band


@pytest.mark.parametrize(
    ("matched", "examined", "band"),
    [
        (1, 1000, "under 1%"),
        (10, 1000, "1 to 10%"),
        (100, 1000, "1 to 10%"),
        (101, 1000, "10 to 50%"),
        (500, 1000, "10 to 50%"),
        (501, 1000, "over 50%"),
    ],
)
def test_a_share_falls_in_one_proportion_band(matched: int, examined: int, band: str) -> None:
    assert proportion_band(matched, examined) == band
