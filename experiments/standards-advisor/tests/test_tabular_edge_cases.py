"""Reading delimited files that are not tidy.

A researcher's CSV being slightly malformed is a fact about the dataset, not a reason to abandon
the run — so each of these is recorded in the notes and carried on with, in keeping with the
errors-as-data rule in `errors`.
"""

from __future__ import annotations

from pathlib import Path

from standards_advisor.profiling.tabular import read_head


def test_tabs_are_sniffed(tmp_path: Path):
    path = tmp_path / "data.tsv"
    path.write_text("a\tb\n1\t2\n3\t4\n", encoding="utf-8")
    head = read_head(path, max_rows=10)
    assert head.delimiter == "\t"
    assert head.headers == ["a", "b"]


def test_quoted_commas_stay_in_one_field(tmp_path: Path):
    path = tmp_path / "data.csv"
    path.write_text('a,notes\n1,"Deep peat, boundary indistinct"\n', encoding="utf-8")
    head = read_head(path, max_rows=10)
    assert head.columns["notes"] == ["Deep peat, boundary indistinct"]


def test_a_byte_order_mark_is_not_part_of_the_first_header(tmp_path: Path):
    """Spreadsheet exports routinely carry one, and it would corrupt the first column name."""
    path = tmp_path / "data.csv"
    path.write_bytes("﻿sample_id,value\nA,1\n".encode())
    head = read_head(path, max_rows=10)
    assert head.headers == ["sample_id", "value"]


def test_ragged_rows_are_padded_and_noted(tmp_path: Path):
    path = tmp_path / "data.csv"
    path.write_text("a,b,c\n1,2\n1,2,3,4\n", encoding="utf-8")
    head = read_head(path, max_rows=10)
    assert head.rows_read == 2
    assert head.columns["c"] == ["", "3"]
    assert any("fewer fields" in note for note in head.notes)
    assert any("more fields" in note for note in head.notes)


def test_duplicate_headers_are_renamed_not_collapsed(tmp_path: Path):
    """Both columns stay visible; collapsing them would silently lose data."""
    path = tmp_path / "data.csv"
    path.write_text("value,value\n1,2\n", encoding="utf-8")
    head = read_head(path, max_rows=10)
    assert head.headers == ["value", "value__2"]
    assert any("duplicate header" in note for note in head.notes)


def test_an_empty_header_gets_a_positional_name(tmp_path: Path):
    path = tmp_path / "data.csv"
    path.write_text("a,,c\n1,2,3\n", encoding="utf-8")
    head = read_head(path, max_rows=10)
    assert head.headers == ["a", "column_2", "c"]


def test_an_empty_file_is_a_note_not_a_crash(tmp_path: Path):
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")
    head = read_head(path, max_rows=10)
    assert head.headers == []
    assert head.rows_read == 0
    assert any("empty" in note for note in head.notes)


def test_a_header_only_file_yields_columns_with_no_values(tmp_path: Path):
    path = tmp_path / "headers.csv"
    path.write_text("a,b,c\n", encoding="utf-8")
    head = read_head(path, max_rows=10)
    assert head.headers == ["a", "b", "c"]
    assert head.rows_read == 0
    assert head.columns == {"a": [], "b": [], "c": []}
