"""A payload as JSON-LD, so that it can be checked against its class's SHACL shapes
(docs/specs/contract.md).

A payload names its class in `schema_class` and nothing else: it carries no `@context` and no
`@type`. `payload_jsonld` adds the class's generated context and an `@type` on the payload and on
every object nested in it whose class the class schema names, found by following the schema's
`$ref`s into its `$defs`. The shapes target classes, so an object without its `@type` would be
checked against nothing, or reported as not of the class its slot requires. A number the schema
types `integer` is written as one, whichever way the transport sent it.

This is pure: it builds a dictionary and imports no RDF library. The harness parses the result
(dd_harness.shacl).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dd_sdk.contract.classes import DESIGNATOR, ClassSchema

_DEFS = "#/$defs/"


def payload_jsonld(payload: Mapping[str, Any], schema: ClassSchema) -> dict[str, Any]:
    """`payload` as a JSON-LD document read through `schema`'s context. Raises `ValueError` if the
    class has no shapes."""
    if schema.shapes is None:
        raise ValueError(f"class {schema.name!r} has no shapes")
    context = schema.shapes.context.get("@context", {})
    defs = schema.json_schema.get("$defs", {})
    document = _typed(payload, schema.name, schema.json_schema, defs, context)
    return {"@context": context, **document}


def _typed(
    value: Any,
    class_name: str | None,
    node: Mapping[str, Any],
    defs: Mapping[str, Any],
    context: Mapping[str, Any],
) -> Any:
    if isinstance(value, list):
        items = node.get("items", {})
        return [_typed(v, *_class_of(v, items, defs), defs, context) for v in value]
    if not isinstance(value, Mapping):
        return _scalar(value, node)
    out: dict[str, Any] = {}
    if class_name is not None and class_name in context:
        out["@type"] = class_name
    properties = node.get("properties", {})
    for key, child in value.items():
        child_node = properties.get(key, {})
        if isinstance(child, list):
            out[key] = _typed(child, None, child_node, defs, context)
        else:
            out[key] = _typed(child, *_class_of(child, child_node, defs), defs, context)
    return out


def _scalar(value: Any, node: Mapping[str, Any]) -> Any:
    """A JSON number the schema types `integer` as an integer. JSON does not tell 14 from 14.0,
    and a transport that carries numbers as doubles, as A2A does, sends the second; JSON Schema
    admits both, and so must the RDF they are read as, where they are different literals."""
    types = node.get("type")
    integer = types == "integer" or (isinstance(types, list) and "integer" in types)
    if integer and isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _class_of(
    value: Any, node: Mapping[str, Any], defs: Mapping[str, Any]
) -> tuple[str | None, Mapping[str, Any]]:
    """The class a value's schema node admits it as, and that class's definition. A value that
    names its class in `schema_class` is taken at its word where the node admits that class."""
    names = [r.removeprefix(_DEFS) for r in _refs(node) if r.removeprefix(_DEFS) in defs]
    if isinstance(value, Mapping) and value.get(DESIGNATOR) in names:
        names = [value[DESIGNATOR]]
    if len(names) == 1:
        return names[0], defs[names[0]]
    return None, node


def _refs(node: Mapping[str, Any]) -> list[str]:
    ref = node.get("$ref")
    if isinstance(ref, str) and ref.startswith(_DEFS):
        return [ref]
    found: list[str] = []
    for key in ("anyOf", "oneOf"):
        for option in node.get(key, ()):
            if isinstance(option, Mapping):
                found.extend(_refs(option))
    return found
