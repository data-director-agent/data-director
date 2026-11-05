"""Infer a table's fields as a Frictionless Table Schema.

Only delimited text is described: CSV and TSV. Frictionless infers each field's type and format
from a sample of rows, so a type is a guess that later rows may contradict.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Rows Frictionless reads to infer types; its own default is 100.
SAMPLE_ROWS = 1000
TABLE_SUFFIXES = {".csv": ",", ".tsv": "\t", ".tab": "\t"}


class TableError(Exception):
    """The file looked like a table but its fields could not be inferred."""


def is_table(path: Path) -> bool:
    return path.suffix.lower() in TABLE_SUFFIXES


def table_fields(path: Path) -> list[dict[str, Any]]:
    """The table's fields as `TableField` objects: name, field_type and, if any, field_format."""
    from frictionless import Detector, Dialect, Resource, formats

    control = formats.CsvControl(delimiter=TABLE_SUFFIXES[path.suffix.lower()])
    try:
        resource = Resource(
            path=path.name,
            basepath=str(path.parent),
            format="csv",
            dialect=Dialect(controls=[control]),
            detector=Detector(sample_size=SAMPLE_ROWS),
        )
        resource.infer()
        schema = resource.schema
    except Exception as exc:  # Frictionless raises its own errors and the reader's
        raise TableError(f"{path.name}: {exc}") from exc
    fields = []
    for f in schema.fields:
        entry: dict[str, Any] = {"name": f.name, "field_type": f.type}
        if f.format and f.format != "default":
            entry["field_format"] = f.format
        fields.append(entry)
    return fields
