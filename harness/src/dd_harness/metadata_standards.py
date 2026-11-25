"""The metadata standards this deployment can read a record in: the definitions and codecs
registered by entry point with `dd_metadata_records` (docs/specs/metadata-standards.md, invariant
11). A standard is available by being installed; the profile does not choose among them.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import cache
from typing import Any

from dd_metadata_records import Record, RecordError, Standards, discover


@cache
def registered() -> Standards:
    """The registered standards, found once per process."""
    return discover()


class UnreadRecordError(ValueError):
    """An approved metadata record that could not be read. The message says why, as the rest of a
    sentence that begins "The approved metadata record"."""


def read_record(record: Mapping[str, Any], standards: Standards | None = None) -> Record:
    """An approved metadata record, as `ProjectStore.metadata_record` gives it, read with the
    definition of the standard it names. Raises `UnreadRecordError` for a record in a pair of
    standard and serialisation no registered definition covers (invariant 1), or whose text is not
    a record in it."""
    found = standards or registered()
    conforms_to, media_type = record.get("conforms_to"), record.get("media_type")
    standard = found.covering(conforms_to, media_type)
    if standard is None:
        raise UnreadRecordError(
            f"is in {conforms_to or 'no named standard'} as {media_type or 'no media type'}, "
            "a pair no registered standard's definition covers"
        )
    try:
        return standard.read(record.get("document_text") or "", str(media_type))
    except RecordError as exc:
        name = standard.definition.name
        serialisation = standard.definition.serialisation(str(media_type))
        written = serialisation.name if serialisation else media_type
        raise UnreadRecordError(f"is not a {name} record in {written}: {exc}") from None


def readable(record: Mapping[str, Any] | None) -> Record | None:
    """The approved metadata record read, or None if there is none or it could not be read: the
    validation has said why, and a package is built only from a valid report."""
    try:
        return read_record(record) if record else None
    except UnreadRecordError:
        return None
