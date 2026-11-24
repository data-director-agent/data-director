"""The approved metadata record as the Documentation Editor reads it (docs/specs/drafting.md,
invariant 2): a record in any standard a registered definition covers, read as the pivot of its
standard's definition (docs/specs/metadata-standards.md), and the README text drafted from it. A
value is placed as the record gives it; a gap the metadata drafter left is not a value.

The record is read once, into its general values by name (`_record`), so that no module here
names a property of any standard."""

from __future__ import annotations

from collections.abc import Mapping
from functools import cache
from typing import Any, Final

from dd_agent_advisor_documentation.sections import RECORD_GENERAL
from dd_metadata_records import Node, Pivot, RecordError, Standards, discover
from dd_sdk.contract.models import ApprovedMetadataRecord

SCHEMA: Final = "http://schema.org/"
_TYPE: Final = "http://purl.org/dc/terms/type"
_FAMILY_NAME: Final = "http://schema.org/familyName"
_GIVEN_NAME: Final = "http://schema.org/givenName"


@cache
def _standards() -> Standards:
    return discover()


def _record(given: ApprovedMetadataRecord | None) -> tuple[dict[str, Any] | None, str | None]:
    """The approved metadata record's values by name, or None and, if there was a record, why it
    was not read."""
    if given is None:
        return None, None
    unread = "The approved metadata record was not used: "
    standard = _standards().covering(given.conforms_to, given.media_type)
    if standard is None:
        named = given.conforms_to or "no standard"
        return None, unread + (
            f"the editor reads only records in a standard it has a definition for, and this one "
            f"is in {named} as {given.media_type}."
        )
    try:
        read = standard.read(given.document_text, given.media_type)
    except RecordError as exc:
        return None, unread + f"{exc}."
    return _values(read.pivot()), None


def _values(pivot: Pivot) -> dict[str, Any]:
    """What the editor reads of a record: its title, creators, dates of collection, places,
    funders, abstract, rights and year of publication, each from its pivot term."""
    titles = pivot.get(SCHEMA + "name", ())
    main = [n for n in titles if not n.part(_TYPE)]
    abstracts = [n for n in pivot.get(SCHEMA + "description", ()) if n.part(_TYPE) == ["Abstract"]]
    year = pivot.values_of(SCHEMA + "datePublished")
    return {
        "title": _first(main) or _first(titles),
        "creators": [name for node in pivot.get(SCHEMA + "creator", ()) if (name := _name(node))],
        "collected": pivot.values_of(SCHEMA + "temporalCoverage"),
        "location": pivot.values_of(SCHEMA + "spatialCoverage"),
        "funding": pivot.values_of(SCHEMA + "funding"),
        "abstract": _first(abstracts),
        "rights": [_rights(node) for node in pivot.get(SCHEMA + "license", ()) if _rights(node)],
        "year": year[0] if year else None,
    }


def _first(nodes: Any) -> str | None:
    return next((node.value for node in nodes if node.value is not None), None)


def _name(node: Node) -> str | None:
    """A person's name, or else their family and given names, as the record writes them."""
    if node.value is not None:
        return node.value
    parts = [*node.part(_FAMILY_NAME)[:1], *node.part(_GIVEN_NAME)[:1]]
    return ", ".join(parts) or None


def _rights(node: Node) -> str:
    name, uris = node.value or "", node.part(SCHEMA + "url")
    uri = uris[0] if uris else ""
    return f"{name} (<{uri}>)" if name and uri else name or (f"<{uri}>" if uri else "")


def _title(record: Mapping[str, Any]) -> str | None:
    """The record's main title: its first title of no type, else its first title."""
    title: str | None = record.get("title")
    return title


def _creators(record: Mapping[str, Any]) -> list[str]:
    """Each creator's name, or else their family and given names, as the record writes them."""
    return list(record.get("creators") or [])


def _collected(record: Mapping[str, Any]) -> list[str]:
    """The record's dates of data collection, as it writes them."""
    return list(record.get("collected") or [])


def _record_general(record: Mapping[str, Any] | None) -> dict[str, str]:
    """The record's general values by key (RECORD_GENERAL), each "" when the record lacks it."""
    if record is None:
        return dict.fromkeys(RECORD_GENERAL, "")
    return {
        "title": _title(record) or "",
        "creators": "; ".join(_creators(record)),
        "collected": "; ".join(_collected(record)),
        "location": "; ".join(record.get("location") or []),
        "funding": "; ".join(record.get("funding") or []),
    }


def _from_record(source: str, record: Mapping[str, Any]) -> str | None:
    """A section's text from the approved metadata record, its values placed as given."""
    title = _title(record)
    creators = _creators(record)
    if source == "record_general":
        given = _record_general(record)
        lines = [(label, given[key]) for key, label in RECORD_GENERAL.items() if given[key]]
        return "\n".join(f"- **{label}:** {value}" for label, value in lines) or None
    if source == "record_abstract":
        abstract: str | None = record.get("abstract")
        return abstract
    if source == "record_rights":
        rights = record.get("rights") or []
        return ("Licence: " + "; ".join(rights) + ".") if rights else None
    if source == "record_citation":
        if not (creators and title):
            return None
        year = record.get("year")
        when = f" ({year})" if year else ""
        return f"{_closed('; '.join(creators) + when)} {_closed(title)}"
    return None


def _closed(text: str) -> str:
    """`text` ending with a full stop, unless it already ends a sentence."""
    return text if text.endswith((".", "?", "!")) else text + "."
