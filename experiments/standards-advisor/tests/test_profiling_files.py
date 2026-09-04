"""Format detection, and which signal decided (§5.1 tier 1)."""

from __future__ import annotations

from pathlib import Path

from standards_advisor.models.common import Derivation
from standards_advisor.profiling.files import is_tabular, resolve_format


def _write(path: Path, content: bytes) -> Path:
    path.write_bytes(content)
    return path


def test_text_formats_come_from_the_extension(tmp_path: Path):
    path = _write(tmp_path / "data.csv", b"a,b\n1,2\n")
    label, derivation, notes = resolve_format(path)
    assert label == "csv"
    assert derivation is Derivation.FILE_EXTENSION
    assert notes == []


def test_leading_bytes_beat_the_extension(tmp_path: Path):
    """A `.csv` that is really a PDF is not a CSV, and the note must say so.

    Silently trusting the extension here would send a binary file to the tabular profiler and
    produce a profile full of nonsense columns.
    """
    path = _write(tmp_path / "data.csv", b"%PDF-1.7\n...")
    label, derivation, notes = resolve_format(path)
    assert label == "pdf"
    assert derivation is Derivation.FILE_MAGIC
    assert any("extension suggests" in note for note in notes)


def test_a_known_specialisation_of_a_container_keeps_the_extension(tmp_path: Path):
    """An `.xlsx` really is a zip, and calling it `zip_container` would be true but useless."""
    path = _write(tmp_path / "book.xlsx", b"PK\x03\x04rest")
    label, derivation, notes = resolve_format(path)
    assert label == "xlsx"
    assert derivation is Derivation.FILE_EXTENSION
    assert any("consistent with detected container" in note for note in notes)


def test_parquet_is_detected_from_its_signature(tmp_path: Path):
    path = _write(tmp_path / "part.parquet", b"PAR1....")
    label, derivation, _ = resolve_format(path)
    assert label == "parquet"
    # Both signals agree, and the more reliable one is credited.
    assert derivation is Derivation.FILE_MAGIC


def test_an_unrecognised_file_reports_nothing_rather_than_guessing(tmp_path: Path):
    path = _write(tmp_path / "mystery.qqq", b"\x01\x02\x03\x04")
    label, derivation, _ = resolve_format(path)
    assert label is None
    assert derivation is None


def test_only_delimited_text_is_treated_as_tabular():
    assert is_tabular("csv")
    assert is_tabular("tsv")
    assert not is_tabular("xlsx")
    assert not is_tabular("parquet")
    assert not is_tabular(None)
