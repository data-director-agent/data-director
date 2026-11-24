"""Where each property of a standard is in an XML serialisation: the layout that turns the codec's
tree of elements into the standard's logical tree, and back (docs/specs/metadata-standards.md, A
standard's definition).

A codec knows no standard (invariant 4), so this mapping is the definition's, and is read from
its file. A property is a repeatable element directly under the root, its values the elements'
text; a property under nested elements is TODO(#1361).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from dd_metadata_records.codecs import Tree
from dd_metadata_records.xml import element

XSI = "http://www.w3.org/2001/XMLSchema-instance"


class LayoutError(ValueError):
    """A tree that does not fit the serialisation's layout."""


def clark(qname: str, namespaces: Mapping[str, str]) -> str:
    """A prefixed name, such as `dc:title`, in Clark notation, with the layout's namespaces."""
    prefix, sep, local = qname.partition(":")
    if not sep:
        return qname
    if prefix not in namespaces:
        raise LayoutError(f"{qname} names a prefix the layout does not declare")
    return f"{{{namespaces[prefix]}}}{local}"


@dataclass(frozen=True)
class XmlLayout:
    """The root element, the namespaces declared on it, the schema it names, and the element each
    property is written as, in the order they are written."""

    root: str
    namespaces: Mapping[str, str]
    elements: Mapping[str, str]
    schema_location: str | None = None

    @classmethod
    def of(cls, spec: Mapping[str, Any]) -> XmlLayout:
        namespaces = {str(k): str(v) for k, v in (spec.get("namespaces") or {}).items()}
        return cls(
            root=clark(str(spec["root"]), namespaces),
            namespaces=namespaces,
            elements={str(p): clark(str(q), namespaces) for p, q in spec["elements"].items()},
            schema_location=spec.get("schema_location"),
        )

    def to_logical(self, tree: Tree) -> dict[str, Any]:
        """The logical tree of a parsed document: each property's element texts, as a list. An
        element the layout does not name is kept under its local name, so that it is reported as
        unmapped and never dropped silently."""
        if not isinstance(tree, dict) or tree.get("name") != self.root:
            name = tree.get("name") if isinstance(tree, dict) else None
            raise LayoutError(f"its root element is {name}, not {self.root}")
        paths = {name: path for path, name in self.elements.items()}
        logical: dict[str, list[Any]] = {}
        for child in tree.get("children") or []:
            name = str(child["name"])
            path = paths.get(name, name.rpartition("}")[2])
            logical.setdefault(path, []).append(child.get("text"))
        return logical

    def to_document(self, tree: Mapping[str, Any]) -> dict[str, Any]:
        """The document of a logical tree: one element for each value of each property, in the
        layout's order. A property the layout has no element for cannot be written."""
        if unknown := [path for path in tree if path not in self.elements]:
            raise LayoutError(f"there is no element for {', '.join(unknown)}")
        children = []
        for path, name in self.elements.items():
            if path not in tree:
                continue
            value = tree[path]
            for given in value if isinstance(value, list) else [value]:
                children.append(element(name, text=None if given is None else str(given)))
        attributes = {}
        if self.schema_location:
            attributes[f"{{{XSI}}}schemaLocation"] = self.schema_location
        root = element(self.root, attributes=attributes, children=children)
        root["namespaces"] = dict(self.namespaces)
        return root
