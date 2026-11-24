"""The XML codec: an XML document as a generic tree of elements, and back
(docs/specs/metadata-standards.md, invariants 4 and 13).

An element is `{"name": "{uri}local", "attributes": {...}, "text": str | None, "children": [...]}`,
with names in Clark notation so that nothing depends on the prefixes a document happens to use.
The root also holds `"namespaces"`, its prefixes by name, which the writer declares on the root.

The parser reads only the record: it refuses a document type declaration or an entity
declaration, so it resolves no external entity and fetches nothing, and it refuses text over the
size limit. The writer is this module's own, not `ElementTree.tostring`, so that the prefixes are
the tree's and no process-wide namespace registry is touched: the same tree always writes the same
text.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Final, cast
from xml.etree.ElementTree import Element, ParseError, XMLPullParser
from xml.sax.saxutils import escape, quoteattr

from dd_metadata_records.codecs import CodecError, Tree, check_size

_DECLARATIONS: Final = re.compile(r"<!(DOCTYPE|ENTITY)", re.IGNORECASE)
_CLARK: Final = re.compile(r"^\{([^}]*)\}(.+)$")
_INDENT: Final = "  "


def element(
    name: str,
    *,
    text: str | None = None,
    attributes: dict[str, str] | None = None,
    children: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """An element of the generic tree."""
    return {"name": name, "attributes": attributes or {}, "text": text, "children": children or []}


@dataclass(frozen=True)
class XmlCodec:
    """XML in UTF-8, with a declaration, the root's namespaces declared on it in order of prefix,
    two spaces of indentation, an element with no text and no children written empty, and a
    final newline."""

    codec_id: str = "xml-indent-2"
    media_type: str = "application/xml"

    def parse(self, text: str) -> Tree:
        check_size(text)
        if _DECLARATIONS.search(text):
            raise CodecError("it declares a document type or an entity, which a record never needs")
        parser: XMLPullParser[Any] = XMLPullParser(events=("start-ns", "start", "end"))
        namespaces: dict[str, str] = {}
        stack: list[dict[str, Any]] = []
        root: dict[str, Any] | None = None
        try:
            parser.feed(text)
            parser.close()
            events = cast(Iterator[tuple[str, Any]], parser.read_events())
            for event, item in events:
                if event == "start-ns" and isinstance(item, tuple):
                    namespaces.setdefault(str(item[0]), str(item[1]))
                elif event == "start" and isinstance(item, Element):
                    node = element(str(item.tag), attributes=dict(item.attrib))
                    if stack:
                        stack[-1]["children"].append(node)
                    else:
                        root = node
                    stack.append(node)
                elif event == "end" and isinstance(item, Element):
                    given = (item.text or "").strip()
                    stack.pop()["text"] = given or None
        except ParseError as exc:
            raise CodecError(f"it is not well-formed XML ({exc})") from None
        if root is None:
            raise CodecError("it has no root element")
        root["namespaces"] = namespaces
        return root

    def emit(self, tree: Tree) -> str:
        if not isinstance(tree, dict) or "name" not in tree:
            raise CodecError("an XML tree is an element")
        namespaces: dict[str, str] = dict(tree.get("namespaces") or {})
        prefixes = {uri: prefix for prefix, uri in namespaces.items()}
        declared = "".join(
            f" xmlns{':' + prefix if prefix else ''}={quoteattr(uri)}"
            for prefix, uri in sorted(namespaces.items())
        )
        lines = ['<?xml version="1.0" encoding="UTF-8"?>']
        _write(tree, prefixes, 0, lines, declared)
        return "\n".join(lines) + "\n"


def _qname(name: str, prefixes: dict[str, str]) -> str:
    match = _CLARK.match(name)
    if match is None:
        return name
    uri, local = match.groups()
    if uri == "http://www.w3.org/XML/1998/namespace":
        return f"xml:{local}"
    if uri not in prefixes:
        raise CodecError(f"no prefix is declared for the namespace {uri}")
    prefix = prefixes[uri]
    return f"{prefix}:{local}" if prefix else local


def _write(
    node: dict[str, Any],
    prefixes: dict[str, str],
    depth: int,
    lines: list[str],
    declared: str = "",
) -> None:
    name = _qname(node["name"], prefixes)
    attributes = "".join(
        f" {_qname(key, prefixes)}={quoteattr(str(value))}"
        for key, value in (node.get("attributes") or {}).items()
    )
    opening = f"{_INDENT * depth}<{name}{declared}{attributes}"
    children = node.get("children") or []
    text = node.get("text")
    if children:
        lines.append(opening + ">")
        for child in children:
            _write(child, prefixes, depth + 1, lines)
        lines.append(f"{_INDENT * depth}</{name}>")
    elif text is not None:
        lines.append(f"{opening}>{escape(str(text))}</{name}>")
    else:
        lines.append(opening + "/>")


XML: Final = XmlCodec()
