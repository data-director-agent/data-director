"""Infer a table's fields as a Frictionless Table Schema.

Only delimited text is described: CSV and TSV. Frictionless infers each field's type and format
from a sample of rows, so a type is a guess that later rows may contradict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Rows Frictionless reads to infer types; its own default is 100.
SAMPLE_ROWS = 1000
# Cells read as missing rather than as values, so that a numeric column with gaps written `NA` is
# not typed as a string (#1070). Frictionless's own default is the empty cell alone.
MISSING_VALUES = ("", "NA", "N/A", "NaN", "null")
TABLE_SUFFIXES = {".csv": ",", ".tsv": "\t", ".tab": "\t"}


class TableError(Exception):
    """The file looked like a table but its fields could not be inferred."""


def is_table(path: Path) -> bool:
    return path.suffix.lower() in TABLE_SUFFIXES


@dataclass(frozen=True)
class Table:
    """What one read of a table gives: its fields as `TableField` objects (name, field_type and,
    if any, field_format), and the sampled values of each column, by column name. The values are
    for the personal-data check alone: they are never written to the inventory."""

    fields: list[dict[str, Any]]
    columns: dict[str, list[str]] = field(default_factory=dict, repr=False)
    # The missing-value markers other than the empty cell that the sample held.
    missing_seen: tuple[str, ...] = ()
    # The fields with no value in the sample, whose type is therefore not known (`any`).
    no_values: tuple[str, ...] = ()
    # How many rows at the top of the file are headers, for a later read of the rows.
    header_rows: int = 1

    def limitations(self, relative: str) -> list[str]:
        """What a reader of the inventory should know about this table's inferred types."""
        said = []
        if self.missing_seen:
            markers = ", ".join(f"`{m}`" for m in self.missing_seen)
            said.append(f"In {relative}, cells holding {markers} were read as missing values.")
        if self.no_values:
            names = ", ".join(f"`{n}`" for n in self.no_values)
            its = "its type is" if len(self.no_values) == 1 else "their types are"
            said.append(
                f"In {relative}, the first {SAMPLE_ROWS} rows hold no value for {names}, so "
                f"{its} not known (`any`)."
            )
        return said


def table_fields(path: Path) -> Table:
    """The table's fields, and the values of the rows sampled to infer them."""
    from frictionless import Detector, Dialect, Resource, formats
    from frictionless.resources import TableResource

    control = formats.CsvControl(delimiter=TABLE_SUFFIXES[path.suffix.lower()])
    try:
        resource = Resource(
            path=path.name,
            basepath=str(path.parent),
            format="csv",
            dialect=Dialect(controls=[control]),
            detector=Detector(sample_size=SAMPLE_ROWS, field_missing_values=list(MISSING_VALUES)),
        )
        if not isinstance(resource, TableResource):
            raise TableError(f"{path.name}: not read as a table")
        resource.infer()
        schema = resource.schema
        headers = len(resource.dialect.header_rows) if resource.dialect.header else 0
        sample = resource.sample[headers:]
    except TableError:
        raise
    except Exception as exc:  # Frictionless raises its own errors and the reader's
        raise TableError(f"{path.name}: {exc}") from exc
    fields = []
    for f in schema.fields:
        entry: dict[str, Any] = {"name": f.name, "field_type": f.type}
        if f.format and f.format != "default":
            entry["field_format"] = f.format
        fields.append(entry)
    names = [f.name for f in schema.fields]
    columns: dict[str, list[str]] = {name: [] for name in names}
    seen: set[str] = set()
    for row in sample:
        for name, cell in zip(names, row, strict=False):
            text = "" if cell is None else str(cell).strip()
            if text in MISSING_VALUES:
                seen.add(text)
            else:
                columns[name].append(str(cell))
    return Table(
        fields,
        columns,
        missing_seen=tuple(m for m in MISSING_VALUES if m and m in seen),
        no_values=tuple(name for name in names if not columns[name]),
        header_rows=headers,
    )
