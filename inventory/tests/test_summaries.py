"""The inventory command writes summary values of table fields only after disclosure control
(docs/specs/personal-data.md, #611): no raw extreme, no count below the threshold, no mean that
one or two values dominate, and no category from a column holding possible personal data."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest

from dd_inventory import SummaryRules, cli, make_inventory
from dd_inventory.summaries import MISSING_CODES
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import FileInventory

Inventory = dict[str, Any]
CORPUS = Path(__file__).parent / "data" / "disclosure"
LABELS: dict[str, Any] = json.loads((CORPUS / "labels.json").read_text(encoding="utf-8"))
K = 10


@pytest.fixture(scope="module")
def corpus() -> Inventory:
    return make_inventory(CORPUS)


def _fields(inventory: Inventory, file: str) -> dict[str, dict[str, Any]]:
    entry = next(f for f in inventory["inventory_files"] if f["file_path"] == file)
    return {f["name"]: f for f in entry.get("file_fields", [])}


def _column(file: str, column: str) -> list[str]:
    path = CORPUS / file
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t" if path.suffix == ".tsv" else ",")
        return [row[column].strip() for row in reader]


def _numbers(file: str, column: str) -> list[float]:
    return sorted(float(v) for v in _column(file, column) if v and v not in MISSING_CODES)


def _table(folder: Path, name: str, header: str, rows: list[str]) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    return folder


def test_an_inventory_with_summaries_is_a_core_file_inventory(corpus: Inventory) -> None:
    assert ClassSchema.of(FileInventory).errors(corpus) == []
    FileInventory.model_validate(corpus)


@pytest.mark.requirement("C2")
@pytest.mark.parametrize("column", ["age", "income"])
def test_no_raw_extreme_is_written(corpus: Inventory, column: str) -> None:
    """Invariant 6: each bound has at least k values at or beyond it, so the cohort's one extreme
    age and one extreme income are written nowhere."""
    numbers = _numbers("summaries/cohort.csv", column)
    summary = _fields(corpus, "summaries/cohort.csv")[column]["field_summary"]
    low, high = float(summary["summary_range_low"]), float(summary["summary_range_high"])
    assert sum(n <= low for n in numbers) >= K
    assert sum(n >= high for n in numbers) >= K
    written = json.dumps(corpus)
    for extreme in (numbers[0], numbers[-1]):
        assert f'"{extreme:g}"' not in written and f'"{extreme}"' not in written


@pytest.mark.requirement("C2")
def test_a_rare_category_is_left_out_and_counted(corpus: Inventory) -> None:
    field = _fields(corpus, "summaries/cohort.csv")["diagnosis"]
    written = {c["category_value"] for c in field["field_summary"]["summary_categories"]}
    assert written == {"asthma", "eczema", "hay fever"}
    assert "Fabry disease" not in json.dumps(corpus)
    assert field["field_disclosure_check"]["check_suppressed"] == 1


def test_a_missing_value_code_is_kept(corpus: Inventory) -> None:
    summary = _fields(corpus, "summaries/cohort.csv")["age"]["field_summary"]
    assert summary["summary_missing_codes"] == [{"missing_code": "-99", "missing_code_count": 30}]
    # The code is left out of the range and the mean.
    assert float(summary["summary_range_low"]) > 0
    assert summary["summary_mean"] > 0


def test_the_control_cohort_keeps_every_summary(corpus: Inventory) -> None:
    fields = _fields(corpus, "summaries/cohort-control.csv")
    for column in ("age", "income", "diagnosis"):
        assert fields[column]["field_disclosure_check"]["check_suppressed"] == 0
    assert {"summary_range_low", "summary_range_high", "summary_mean"} <= set(
        fields["age"]["field_summary"]
    )


@pytest.mark.requirement("C2")
def test_every_count_passes_the_threshold_and_is_rounded(corpus: Inventory) -> None:
    """Invariant 7."""
    counts = []
    for entry in corpus["inventory_files"]:
        for field in entry.get("file_fields", []):
            summary = field["field_summary"]
            counts += [
                summary[s] for s in ("summary_rows_read", "summary_null_count") if s in summary
            ]
            counts += [c["category_count"] for c in summary.get("summary_categories", [])]
            counts += [c["missing_code_count"] for c in summary.get("summary_missing_codes", [])]
    assert counts
    assert all(c >= K and c % 5 == 0 for c in counts)


@pytest.mark.requirement("C2")
def test_no_category_comes_from_a_column_holding_possible_personal_data(
    corpus: Inventory,
) -> None:
    for label in LABELS["personal_data"]:
        if "column" in label:
            field = _fields(corpus, label["file"])[label["column"]]
            assert "summary_categories" not in field["field_summary"], label


@pytest.mark.requirement("C2")
def test_a_mean_one_value_dominates_is_left_out(tmp_path: Path) -> None:
    rows = [f"P{i:03d},1" for i in range(30)] + ["P999,1000000000"]
    made = make_inventory(_table(tmp_path, "t.csv", "id,amount", rows))
    field = _fields(made, "t.csv")["amount"]
    assert "summary_mean" not in field["field_summary"]
    assert field["field_disclosure_check"]["check_suppressed"] >= 1
    assert "1000000000" not in json.dumps(made)


def test_a_range_needs_twice_the_threshold(tmp_path: Path) -> None:
    made = make_inventory(_table(tmp_path, "t.csv", "x", [str(i) for i in range(2 * K - 1)]))
    field = _fields(made, "t.csv")["x"]
    assert "summary_range_low" not in field["field_summary"]
    assert field["field_disclosure_check"]["check_suppressed"] >= 1


def test_a_date_range_is_the_kth_dates(tmp_path: Path) -> None:
    dates = [f"2024-01-{d:02d}" for d in range(1, 31)]
    made = make_inventory(_table(tmp_path, "t.csv", "visit", dates))
    summary = _fields(made, "t.csv")["visit"]["field_summary"]
    assert (summary["summary_range_low"], summary["summary_range_high"]) == (
        "2024-01-10",
        "2024-01-21",
    )
    assert "summary_mean" not in summary


def test_a_higher_threshold_tightens_the_range(tmp_path: Path) -> None:
    folder = _table(tmp_path, "t.csv", "x", [str(i) for i in range(1, 101)])
    made = make_inventory(folder, summaries=SummaryRules(threshold=20, rounding_base=10))
    field = _fields(made, "t.csv")["x"]
    assert field["field_summary"]["summary_range_low"] == "20"
    assert field["field_summary"]["summary_range_high"] == "81"
    assert field["field_disclosure_check"]["check_threshold"] == 20
    assert field["field_disclosure_check"]["check_rounding_base"] == 10


@pytest.mark.parametrize(("threshold", "base"), [(9, 5), (10, 4)])
def test_the_rules_may_not_be_relaxed(threshold: int, base: int) -> None:
    """Invariant 8."""
    with pytest.raises(ValueError):
        SummaryRules(threshold=threshold, rounding_base=base)


def test_rows_beyond_the_cap_are_not_read_and_said_so(tmp_path: Path) -> None:
    folder = _table(tmp_path, "t.csv", "x", [str(i) for i in range(200)])
    made = make_inventory(folder, summaries=SummaryRules(row_cap=50))
    whole = make_inventory(folder)
    assert _fields(made, "t.csv")["x"]["field_summary"]["summary_rows_read"] == 50
    assert len(made["inventory_limitations"]) == len(whole["inventory_limitations"]) + 1


@pytest.fixture(scope="module")
def summarised() -> Inventory:
    return make_inventory(CORPUS / "summaries", runtime=None)


def _says_why_not(made: Inventory, summarised: Inventory) -> None:
    """An inventory without summaries says something in their place: as many limitations as one
    with them, but not the same ones."""
    assert len(made["inventory_limitations"]) == len(summarised["inventory_limitations"])
    assert set(made["inventory_limitations"]) != set(summarised["inventory_limitations"])


def test_turned_off_the_summaries_are_absent_and_said_so(summarised: Inventory) -> None:
    made = make_inventory(CORPUS / "summaries", summaries=None)
    for field in _fields(made, "cohort.csv").values():
        assert "field_summary" not in field and "field_disclosure_check" not in field
    _says_why_not(made, summarised)


def test_in_the_browser_the_summaries_are_absent_and_said_so(
    monkeypatch: pytest.MonkeyPatch, summarised: Inventory
) -> None:
    monkeypatch.setattr("dd_inventory.scan.detect_runtime", lambda: "pyodide.314.0.7")
    made = make_inventory(CORPUS / "summaries", runtime=None)
    assert all("field_summary" not in f for f in _fields(made, "cohort.csv").values())
    _says_why_not(made, summarised)


def test_the_command_refuses_a_lower_threshold(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([str(CORPUS / "summaries"), "--threshold", "5"]) == cli.EXIT_USAGE
    assert capsys.readouterr().err


def test_the_command_can_leave_summaries_out(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "inventory.json"
    assert cli.main([str(CORPUS / "summaries"), "--no-summaries", "-o", str(out)]) == cli.EXIT_OK
    assert "field_summary" not in out.read_text(encoding="utf-8")


def test_a_category_holding_quotes_is_counted(tmp_path: Path) -> None:
    """ACRO builds queries from labels, so it is never given a value as one."""
    rows = ['"it\'s ""wet"""'] * 12 + ["dry"] * 12
    made = make_inventory(_table(tmp_path, "t.csv", "ground", rows))
    categories = _fields(made, "t.csv")["ground"]["field_summary"]["summary_categories"]
    assert {c["category_value"] for c in categories} == {'it\'s "wet"', "dry"}


def test_a_table_whose_summaries_fail_is_listed_and_said_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*_: object, **__: object) -> None:
        raise RuntimeError("an unexpected table")

    folder = _table(tmp_path, "t.csv", "x", [str(i) for i in range(30)])
    whole = make_inventory(folder)
    monkeypatch.setattr("dd_inventory.summaries._field", fail)
    made = make_inventory(folder)
    assert all("field_summary" not in f for f in _fields(made, "t.csv").values())
    assert len(made["inventory_limitations"]) == len(whole["inventory_limitations"]) + 1
    assert "an unexpected table" not in json.dumps(made)
