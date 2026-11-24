"""What a record in one standard would lose in another: the start of a conversion through the pivot
(docs/specs/metadata-standards.md, invariant 9). The conversion itself is TODO(#1363).
"""

from __future__ import annotations

from dd_metadata_records.definition import Definition
from dd_metadata_records.record import Pivot


def unplaced(pivot: Pivot, target: Definition) -> tuple[str, ...]:
    """The paths, in the source standard, of every value in `pivot` that `target` has no property
    for: those under a term no property of the target is read under, and those no term holds at
    all. Each is named once, in order of path."""
    placed = {term for prop in target.properties.values() for term in prop.terms()}
    lost = {node.path for term, nodes in pivot.items() if term not in placed for node in nodes}
    return tuple(sorted(lost | set(pivot.unmapped)))
