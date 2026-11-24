"""A record read with its standard's definition: its values by property, and the pivot, the graph of
existing terms that a record in any standard is checked and described in
(docs/specs/metadata-standards.md, The pivot).

The record is the record of truth. The pivot is derived from it each time it is needed, and is
never kept or edited.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

from dd_metadata_records.definition import Definition, Property


@dataclass(frozen=True)
class Node:
    """One value of the pivot: the entry of a property a term holds, with the property's path in
    the standard, its value as text if it has one, and its parts under their own terms. A literal
    is a node with no parts. A node whose value is None is an entry with no value, such as a gap."""

    path: str
    value: str | None
    parts: Mapping[str, tuple[Node, ...]] = field(default_factory=dict)

    def part(self, term: str) -> list[str]:
        """The values of the parts under `term`, as text."""
        return [node.value for node in self.parts.get(term, ()) if node.value is not None]


class Pivot(Mapping[str, tuple[Node, ...]]):
    """The pivot of one record: each term, as an IRI, with the nodes it holds, in the order the
    definition lists its properties. `unmapped` names, by their keys, the values the record has
    that no term holds, so that a reader can say what it could not place."""

    def __init__(self, terms: Mapping[str, tuple[Node, ...]], unmapped: tuple[str, ...]) -> None:
        self._terms = dict(terms)
        self.unmapped = unmapped

    def __getitem__(self, term: str) -> tuple[Node, ...]:
        return self._terms[term]

    def __iter__(self) -> Iterator[str]:
        return iter(self._terms)

    def __len__(self) -> int:
        return len(self._terms)

    def values_of(self, term: str) -> list[str]:
        """The values the nodes under `term` have, as text."""
        return [node.value for node in self._terms.get(term, ()) if node.value is not None]


@dataclass(frozen=True)
class Record:
    """A record's logical tree, read with its standard's definition."""

    definition: Definition
    media_type: str
    tree: Mapping[str, Any]

    def values(self, path: str, qualifier: Mapping[str, Any] | None = None) -> list[str]:
        """The values of a requirement field of `path` and `qualifier`: each entry of the property
        that matches the qualifier, as text. An absent, empty or null value is no value, and so is
        a gap (invariant 6)."""
        head, _, rest = path.partition(".")
        value = self.tree.get(head)
        if rest:
            entries = [value.get(rest) if isinstance(value, dict) else None]
        else:
            entries = value if isinstance(value, list) else [value]
        found = self.definition.property(head)
        value_key = (found.value if found else None) or ""
        wanted = qualifier or {}
        values = []
        for entry in entries:
            if isinstance(entry, dict):
                if any(entry.get(key) != given for key, given in wanted.items()):
                    continue
                entry = entry.get(value_key)
            elif wanted:
                continue
            if isinstance(entry, str | int | float) and str(entry).strip():
                values.append(str(entry).strip())
        return values

    def pivot(self) -> Pivot:
        """The record as the pivot: each property's entries under the term the definition gives
        them, and the keys of what no term holds."""
        terms: dict[str, list[Node]] = {}
        for prop in self.definition.properties.values():
            for term, node in _nodes(prop, _lookup(self.tree, prop.path)):
                terms.setdefault(term, []).append(node)
        termed = {
            prop.path.partition(".")[0]
            for prop in self.definition.properties.values()
            if prop.terms()
        }
        unmapped = tuple(key for key, value in self.tree.items() if value and key not in termed)
        return Pivot({term: tuple(nodes) for term, nodes in terms.items()}, unmapped)


def _lookup(tree: Mapping[str, Any], path: str) -> Any:
    value: Any = tree
    for key in path.split("."):
        value = value.get(key) if isinstance(value, dict) else None
    return value


def _text(value: Any) -> str | None:
    if isinstance(value, str | int | float) and not isinstance(value, bool):
        text = str(value).strip()
        return text or None
    return None


def _nodes(prop: Property, value: Any) -> Iterator[tuple[str, Node]]:
    """Each entry of `value` as a node, with the term it is held under."""
    if value is None or value == "" or value == [] or value == {}:
        return
    for entry in value if isinstance(value, list) else [value]:
        if isinstance(entry, dict):
            term = prop.term_for(entry)
            given = _text(entry.get(prop.value)) if prop.value else None
            node = Node(prop.path, given, _parts(prop, entry))
        else:
            term, text = prop.term, _text(entry)
            if text is None:
                continue
            node = Node(prop.path, text)
        if term:
            yield term, node


def _parts(prop: Property, entry: Mapping[str, Any]) -> dict[str, tuple[Node, ...]]:
    parts: dict[str, list[Node]] = {}
    for key, part in prop.parts.items():
        for term, node in _nodes(part, entry.get(key)):
            parts.setdefault(term, []).append(node)
    return {term: tuple(nodes) for term, nodes in parts.items()}
