"""Reading the head of a delimited file — the only code that touches file content.

§1.4 constrains this rather than merely recommending it: the parts that read file contents run
locally with no model involved, and only derived column *metadata* — names, inferred types,
counts — is ever sent to a model. Sample values are not. That is a constraint on the design, not
a note about this prototype's test data.

Two consequences visible here. `read_head` stops after `max_rows` and reports `bytes_read`, so a
test can assert that a large file was not consumed. And the stdlib `csv` module is used rather
than a dataframe library, because head-only reading is the natural thing to do with `csv` and a
thing you have to fight a dataframe library about.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

# Bytes handed to the delimiter sniffer. Enough for several rows of a typical research CSV.
SNIFF_BYTES = 8192

# Delimiters the sniffer is allowed to choose between. Left unbounded it will happily decide a
# prose column makes a file space-delimited.
CANDIDATE_DELIMITERS = ",\t;|"


@dataclass(frozen=True)
class TabularHead:
    """The head of one delimited file, and evidence of how little of it was read."""

    headers: list[str]
    columns: dict[str, list[str]]
    rows_read: int
    bytes_read: int
    delimiter: str
    delimiter_sniffed: bool
    notes: list[str] = field(default_factory=list)


class _CountingText:
    """A text-file wrapper that records how many characters were consumed.

    `csv.reader` reads through the iterator lazily, so wrapping the file rather than the reader
    is what makes "we stopped early" measurable instead of merely intended.
    """

    def __init__(self, handle: object) -> None:
        self._handle = handle
        self.chars_read = 0

    def __iter__(self) -> _CountingText:
        return self

    def __next__(self) -> str:
        line = next(self._handle)  # type: ignore[call-overload]
        self.chars_read += len(line)
        return str(line)


def sniff_delimiter(sample: str) -> tuple[str, bool]:
    """Return `(delimiter, was_sniffed)`, falling back to a comma.

    A failed sniff is not an error. It happens on a single-column file, and a comma is the
    right answer there anyway.
    """
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=CANDIDATE_DELIMITERS)
    except csv.Error:
        return ",", False
    return str(dialect.delimiter), True


def read_head(path: Path, max_rows: int) -> TabularHead:
    """Read at most `max_rows` data rows from a delimited file.

    Raises nothing for a ragged file: a short row is padded and a long one truncated, both with
    a note. A researcher's CSV being slightly malformed is a fact about the dataset, not a
    reason to abandon the run.
    """
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(SNIFF_BYTES)
        delimiter, sniffed = sniff_delimiter(sample)
        handle.seek(0)

        counter = _CountingText(handle)
        reader = csv.reader(counter, delimiter=delimiter)

        notes: list[str] = []
        if not sniffed:
            notes.append("delimiter could not be sniffed; assumed a comma")

        try:
            headers = [name.strip() for name in next(reader)]
        except StopIteration:
            return TabularHead(
                headers=[],
                columns={},
                rows_read=0,
                bytes_read=counter.chars_read,
                delimiter=delimiter,
                delimiter_sniffed=sniffed,
                notes=[*notes, "file is empty"],
            )

        headers = _deduplicate(headers, notes)
        columns: dict[str, list[str]] = {name: [] for name in headers}

        rows_read = 0
        ragged_short = 0
        ragged_long = 0
        for row in reader:
            if rows_read >= max_rows:
                notes.append(
                    f"stopped after {max_rows} rows; the rest of the file was not read (§1.4)"
                )
                break
            if len(row) < len(headers):
                ragged_short += 1
                row = [*row, *([""] * (len(headers) - len(row)))]
            elif len(row) > len(headers):
                ragged_long += 1
                row = row[: len(headers)]
            for name, value in zip(headers, row, strict=True):
                columns[name].append(value)
            rows_read += 1

    if ragged_short:
        notes.append(f"{ragged_short} row(s) had fewer fields than the header; padded")
    if ragged_long:
        notes.append(f"{ragged_long} row(s) had more fields than the header; truncated")

    return TabularHead(
        headers=headers,
        columns=columns,
        rows_read=rows_read,
        bytes_read=counter.chars_read,
        delimiter=delimiter,
        delimiter_sniffed=sniffed,
        notes=notes,
    )


def _deduplicate(headers: list[str], notes: list[str]) -> list[str]:
    """Make header names unique, since they key the column map.

    Duplicate headers are common in spreadsheets exported to CSV. Renaming rather than
    collapsing keeps both columns visible, and the note says it happened.
    """
    seen: dict[str, int] = {}
    result: list[str] = []
    for index, name in enumerate(headers):
        label = name or f"column_{index + 1}"
        if not name:
            notes.append(f"column {index + 1} has an empty header; named {label!r}")
        if label in seen:
            seen[label] += 1
            renamed = f"{label}__{seen[label]}"
            notes.append(f"duplicate header {label!r} renamed to {renamed!r}")
            label = renamed
        else:
            seen[label] = 1
        result.append(label)
    return result
