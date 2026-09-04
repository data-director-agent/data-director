"""§1.4 — the profiler reads the *head* of a data file, not whole files.

This is a design constraint rather than an optimisation: the parts that read file contents run
locally, and the reason they may is that only derived column metadata ever moves on. A profiler
that quietly read whole files would still satisfy the letter of that, but it would make the
"runs on a laptop" claim false and would be a surprise nobody had agreed to.

So it is asserted with a byte count, not just a row count. A row limit that still consumed the
whole file would pass a row-count assertion.
"""

from __future__ import annotations

from pathlib import Path

from standards_advisor.profiling.tabular import read_head

ROWS_IN_FILE = 20_000
MAX_ROWS = 100


def _big_csv(path: Path) -> Path:
    lines = ["sample_id,value,notes"]
    lines.extend(
        f"PDS-{index:06d},{index * 1.5},"
        f"a reasonably long note to make each row substantial number {index}"
        for index in range(ROWS_IN_FILE)
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_only_the_requested_rows_are_read(tmp_path: Path):
    path = _big_csv(tmp_path / "big.csv")
    head = read_head(path, max_rows=MAX_ROWS)

    assert head.rows_read == MAX_ROWS
    assert all(len(values) == MAX_ROWS for values in head.columns.values())


def test_most_of_the_file_is_never_touched(tmp_path: Path):
    path = _big_csv(tmp_path / "big.csv")
    total_bytes = path.stat().st_size
    head = read_head(path, max_rows=MAX_ROWS)

    # The sniffer reads a fixed 8 KiB sample and the reader then re-reads from the start, so
    # the floor is a few KiB regardless of the row limit. What matters is that consumption is
    # bounded by the row limit rather than by the size of the file.
    assert head.bytes_read < total_bytes / 10, (
        f"read {head.bytes_read} of {total_bytes} bytes; the head-only constraint is not holding"
    )


def test_stopping_early_is_recorded_in_the_notes(tmp_path: Path):
    """A profile built from a sample should say so, not look like a complete picture."""
    path = _big_csv(tmp_path / "big.csv")
    head = read_head(path, max_rows=MAX_ROWS)
    assert any("stopped after" in note for note in head.notes)


def test_a_short_file_is_read_completely_without_a_note(tmp_path: Path):
    path = tmp_path / "small.csv"
    path.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
    head = read_head(path, max_rows=MAX_ROWS)
    assert head.rows_read == 2
    assert not any("stopped after" in note for note in head.notes)
