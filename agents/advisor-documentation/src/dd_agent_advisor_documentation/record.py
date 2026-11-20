"""The approved metadata record as the Documentation Editor reads it (docs/specs/drafting.md,
invariant 2): DataCite's properties in the JSON form of its REST API's attributes, as
advisor.metadata drafts it, and the README text drafted from them. A value is placed as the record
gives it; a placeholder the metadata mock left (null, or blank) is not a value."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from dd_agent_advisor_documentation.sections import RECORD_GENERAL
from dd_sdk.contract.models import ApprovedMetadataRecord

# The metadata record's schema the editor reads: DataCite's, in the JSON form of its REST API's
# attributes, as advisor.metadata drafts it.
DATACITE = "http://datacite.org/schema/kernel-4"


def _record(given: ApprovedMetadataRecord | None) -> tuple[dict[str, Any] | None, str | None]:
    """The approved metadata record's properties, or None and, if there was a record, why it was
    not read."""
    if given is None:
        return None, None
    unread = "The approved metadata record was not used: "
    if given.conforms_to != DATACITE:
        return None, unread + f"the editor reads only DataCite records ({DATACITE})."
    try:
        properties = json.loads(given.document_text)
    except json.JSONDecodeError:
        return None, unread + "its text is not JSON."
    if not isinstance(properties, dict):
        return None, unread + "its text is not a JSON object of DataCite properties."
    return properties, None


def _values(record: Mapping[str, Any], prop: str, key: str) -> list[str]:
    """Each non-empty `key` of the entries of a DataCite property whose value is a list of
    objects. A placeholder the metadata mock left (null, or blank) is not a value."""
    entries = record.get(prop)
    if not isinstance(entries, list):
        return []
    return [
        value.strip()
        for entry in entries
        if isinstance(entry, dict) and isinstance(value := entry.get(key), str) and value.strip()
    ]


def _title(record: Mapping[str, Any]) -> str | None:
    """The record's main title: its first title with no `titleType`, else its first title."""
    entries = record.get("titles")
    if not isinstance(entries, list):
        return None
    main = [e for e in entries if isinstance(e, dict) and not e.get("titleType")]
    titles = _values({"titles": main}, "titles", "title") or _values(record, "titles", "title")
    return titles[0] if titles else None


def _creators(record: Mapping[str, Any]) -> list[str]:
    """Each creator's name, or else their family and given names, as the record writes them."""
    entries = record.get("creators")
    if not isinstance(entries, list):
        return []
    names = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
            continue
        parts = [entry.get("familyName"), entry.get("givenName")]
        given = [p.strip() for p in parts if isinstance(p, str) and p.strip()]
        if given:
            names.append(", ".join(given))
    return names


def _record_general(record: Mapping[str, Any] | None) -> dict[str, str]:
    """The record's general values by key (RECORD_GENERAL), each "" when the record lacks it."""
    if record is None:
        return dict.fromkeys(RECORD_GENERAL, "")
    return {
        "title": _title(record) or "",
        "creators": "; ".join(_creators(record)),
        "collected": "; ".join(_collected(record)),
        "location": "; ".join(_values(record, "geoLocations", "geoLocationPlace")),
        "funding": "; ".join(_values(record, "fundingReferences", "funderName")),
    }


def _collected(record: Mapping[str, Any]) -> list[str]:
    """The record's dates of data collection: its `dates` of type `Collected`, as it writes them."""
    entries = record.get("dates")
    collected = [
        e
        for e in (entries if isinstance(entries, list) else [])
        if isinstance(e, dict) and e.get("dateType") == "Collected"
    ]
    return _values({"dates": collected}, "dates", "date")


def _from_record(source: str, record: Mapping[str, Any]) -> str | None:
    """A section's text from the approved metadata record, its values placed as given."""
    title = _title(record)
    creators = _creators(record)
    if source == "record_general":
        given = _record_general(record)
        lines = [(label, given[key]) for key, label in RECORD_GENERAL.items() if given[key]]
        return "\n".join(f"- **{label}:** {value}" for label, value in lines) or None
    if source == "record_abstract":
        entries = record.get("descriptions")
        abstracts = [
            e
            for e in entries or []
            if isinstance(e, dict) and e.get("descriptionType") == "Abstract"
        ]
        found = _values({"descriptions": abstracts}, "descriptions", "description")
        return found[0] if found else None
    if source == "record_rights":
        entries = record.get("rightsList")
        rights = []
        for entry in entries if isinstance(entries, list) else []:
            if not isinstance(entry, dict):
                continue
            name, uri = entry.get("rights"), entry.get("rightsUri") or entry.get("rightsURI")
            name = name.strip() if isinstance(name, str) else ""
            uri = uri.strip() if isinstance(uri, str) else ""
            if name or uri:
                rights.append(f"{name} (<{uri}>)" if name and uri else name or f"<{uri}>")
        return ("Licence: " + "; ".join(rights) + ".") if rights else None
    if source == "record_citation":
        if not (creators and title):
            return None
        year = record.get("publicationYear")
        when = f" ({year})" if isinstance(year, int | str) and str(year).strip() else ""
        return f"{_closed('; '.join(creators) + when)} {_closed(title)}"
    return None


def _closed(text: str) -> str:
    """`text` ending with a full stop, unless it already ends a sentence."""
    return text if text.endswith((".", "?", "!")) else text + "."
