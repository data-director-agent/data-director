"""A record's logical tree: a property's value by its path, and an entry written from a node of
the pivot (docs/specs/metadata-standards.md, invariant 5).

A path names a property by its keys joined with full stops, such as `types.resourceTypeGeneral`,
the same in every serialisation. `entry` is the inverse of reading an entry into the pivot: it
writes a node, given in pivot terms, as an entry of a property in the standard's own keys, so that
a drafter names no key of any standard.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dd_metadata_records.definition import Property
from dd_metadata_records.record import Node


def get_path(tree: Mapping[str, Any], path: str) -> Any:
    """The value at `path`, or None if any key on the way is absent."""
    value: Any = tree
    for key in path.split("."):
        value = value.get(key) if isinstance(value, Mapping) else None
    return value


def has_path(tree: Mapping[str, Any], path: str) -> bool:
    """Whether the tree holds `path`, whatever its value."""
    *parents, last = path.split(".")
    node: Any = tree
    for key in parents:
        node = node.get(key) if isinstance(node, Mapping) else None
    return isinstance(node, Mapping) and last in node


def set_path(tree: dict[str, Any], path: str, value: Any) -> None:
    """Write `value` at `path`, making each object on the way that is absent."""
    *parents, last = path.split(".")
    node = tree
    for key in parents:
        node = node.setdefault(key, {})
    node[last] = value


def entry(prop: Property, node: Node) -> Any:
    """`node` written as one entry of `prop`: its value under the property's value key, then each
    part the node has under the first key the definition gives that part's term, in the
    definition's order. A part whose own value is a list of objects is written as a list, any
    other as its first value. A property that holds a plain value is written as the node's
    value."""
    if prop.value is None and not prop.parts:
        return node.value
    written: dict[str, Any] = {}
    if prop.value is not None:
        written[prop.value] = node.value
    used: set[str] = set()
    for key, part in prop.parts.items():
        nodes = node.parts.get(part.term or "")
        if not nodes or part.term in used:
            continue
        used.add(str(part.term))
        if part.value is not None or part.parts:
            written[key] = [entry(part, given) for given in nodes]
        else:
            written[key] = nodes[0].value
    return written
