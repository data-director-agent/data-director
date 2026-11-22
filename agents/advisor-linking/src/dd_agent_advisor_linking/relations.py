"""The DataCite relationType suggested for a resolved DOI, from what its record names (R11).

`relations.yaml` is the whole table: each row gives a relation, the record types it suits, in
DataCite's resourceTypeGeneral and Crossref's work types, and the advice that goes with it. A type
no row lists has no suggestion here, so the link keeps the scheme's default (`schemes.yaml`).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml

RELATIONS = Path(__file__).with_name("relations.yaml")


@dataclass(frozen=True)
class Relation:
    """A suggested relation, or None where the work is not a related identifier, and why."""

    relation: str | None
    types: tuple[str, ...]
    advice: str


def load_relations(path: Path = RELATIONS) -> tuple[Relation, ...]:
    with path.open(encoding="utf-8") as fh:
        rows = yaml.safe_load(fh)
    return tuple(
        Relation(
            relation=row.get("relation"),
            types=tuple(str(t) for t in row["types"]),
            advice=" ".join(str(row["advice"]).split()),
        )
        for row in rows
    )


@cache
def _by_type() -> dict[str, Relation]:
    return {t: row for row in load_relations() for t in row.types}


def for_type(record_type: str | None) -> Relation | None:
    """The row for a record's type, or None when the type is absent or no row lists it."""
    return _by_type().get(record_type) if record_type else None
