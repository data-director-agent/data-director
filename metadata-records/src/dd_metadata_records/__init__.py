"""Metadata records in any standard: codecs that parse and write a serialisation, standards'
definitions that say how a standard is written and what each property means, and the pivot a
record is read as (docs/specs/metadata-standards.md). It speaks no Data Director contract."""

from __future__ import annotations

from dd_metadata_records.codecs import JSON, MAX_RECORD_BYTES, Codec, CodecError, JsonCodec, Tree
from dd_metadata_records.definition import (
    TERM_NAMESPACES,
    Definition,
    DefinitionError,
    Property,
    Serialisation,
    expand,
    load,
)
from dd_metadata_records.record import Node, Pivot, Record
from dd_metadata_records.registry import RecordError, Standard, Standards, discover
from dd_metadata_records.tree import entry, get_path, has_path, set_path

__all__ = [
    "JSON",
    "MAX_RECORD_BYTES",
    "TERM_NAMESPACES",
    "Codec",
    "CodecError",
    "Definition",
    "DefinitionError",
    "JsonCodec",
    "Node",
    "Pivot",
    "Property",
    "Record",
    "RecordError",
    "Serialisation",
    "Standard",
    "Standards",
    "Tree",
    "discover",
    "entry",
    "expand",
    "get_path",
    "has_path",
    "load",
    "set_path",
]
