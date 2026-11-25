"""A record in one standard written in another, through the pivot
(docs/specs/metadata-standards.md, invariant 9, Converting a record).

Each value of the source record is read under its pivot term, and written into the property of
the target that is read under the same term, in the target's own keys (`tree.entry`). n standards
need n definitions, not n² converters. A conversion copies values and invents none. It reports
every value it could not place (`unplaced`), and every one it placed less precisely
(`reduced`): a structured value whose parts the target has no place for, or a second value where
the target holds one. A property the target asks for and the source has no value for is left out:
whether that is acceptable is for the target's requirements to say.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from dd_metadata_records.definition import ANY, Definition, Property
from dd_metadata_records.record import Node, Pivot, Record
from dd_metadata_records.tree import entry, set_path


@dataclass(frozen=True)
class Reduced:
    """A value placed less precisely than the source gave it: its property's path in the source,
    and why."""

    path: str
    reason: str


@dataclass(frozen=True)
class Conversion:
    """A record converted to another standard: its logical tree in the target, and what was lost
    on the way."""

    tree: dict[str, Any]
    unplaced: tuple[str, ...]
    reduced: tuple[Reduced, ...]


def unplaced(pivot: Pivot, target: Definition) -> tuple[str, ...]:
    """The paths, in the source standard, of every value in `pivot` that `target` has no property
    for: those under a term no property of the target is read under, and those no term holds at
    all. Each is named once, in order of path."""
    placed = {term for prop in target.properties.values() for term in prop.terms()}
    lost = {node.path for term, nodes in pivot.items() if term not in placed for node in nodes}
    return tuple(sorted(lost | set(pivot.unmapped)))


def convert(record: Record, target: Definition) -> Conversion:
    """`record` written as a logical tree of `target`, with what it could not place or placed
    less precisely. A gap in the source is not copied."""
    pivot = record.pivot()
    waiting = {term: [node for node in nodes if _has_value(node)] for term, nodes in pivot.items()}
    tree: dict[str, Any] = {}
    reduced: list[Reduced] = []
    for prop in target.properties.values():
        written = []
        for term, qualifier in _terms(prop):
            nodes = waiting.get(term) or []
            taken = nodes if prop.repeats else nodes[:1]
            waiting[term] = nodes[len(taken) :]
            for node in taken:
                written.append(_written(prop, node, qualifier))
                if lost := _lost_parts(prop, node):
                    reduced.append(Reduced(node.path, _no_place(lost, target.name)))
        if written:
            set_path(tree, prop.path, written if prop.repeats else written[0])
    read = {term for prop in target.properties.values() for term in prop.terms()}
    for term, nodes in waiting.items():
        if term not in read:
            continue  # reported as unplaced
        for node in nodes:
            reason = f"{target.name} holds one value where the source gives several"
            reduced.append(Reduced(node.path, reason))
    return Conversion(tree, unplaced(pivot, target), tuple(dict.fromkeys(reduced)))


def _has_value(node: Node) -> bool:
    return node.value is not None or bool(node.parts)


def _terms(prop: Property) -> Iterator[tuple[str, dict[str, str]]]:
    """The terms a target property is written from, each with the qualifier an entry written
    from it carries: none for its own term, the values a qualified term's rule names for it."""
    if prop.term:
        yield prop.term, {}
    for rule in prop.qualified:
        concrete = {key: value for key, value in rule.when.items() if value != ANY}
        yield rule.term, concrete


def _written(prop: Property, node: Node, qualifier: dict[str, str]) -> Any:
    written = entry(prop, node)
    if qualifier and isinstance(written, dict):
        written.update(qualifier)
    return written


def _no_place(parts: list[str], standard: str) -> str:
    named = parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} and {parts[-1]}"
    verb = "has" if len(parts) == 1 else "have"
    return f"its {named} {verb} no place in {standard}"


def _lost_parts(prop: Property, node: Node) -> list[str]:
    """The parts of `node` the target property has no place for, by their term's local name."""
    kept = {part.term for part in prop.parts.values()}
    return sorted(
        {term.rsplit("/", 1)[-1].rsplit("#", 1)[-1] for term in node.parts if term not in kept}
    )
