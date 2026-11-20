"""The Zenodo transport's item: the approved DataCite record rendered as the `metadata` of a
Zenodo deposition (docs/specs/deposit.md, Depositing through an API; TODO(#648) for the rest).

The mapping is the platform item's packager. It reads the same DataCite properties validation reads
(`dd_harness.deposit.VALUE_KEYS`) and writes the members of Zenodo's deposition metadata
(https://developers.zenodo.org/#representation):

| DataCite | Zenodo |
|---|---|
| `titles` (the first) | `title` |
| `creators` | `creators`: `name`, `orcid` from an ORCID name identifier, `affiliation` |
| `descriptions` (the Abstract, else the first) | `description` |
| `types.resourceTypeGeneral` | `upload_type`: `dataset`, `software`, else `other` |
| `subjects` | `keywords` |
| `rightsList` (the first SPDX identifier) | `license`, lower case, as Zenodo names licences |
| `relatedIdentifiers` | `related_identifiers`: `identifier`, `relation` |
| the connector's `target` | `communities` |

Every other property the record has is reported as unplaced on the deposit's outcome, never
dropped silently. Funding is among them: Zenodo takes a grant only by its funder's and award's
identifiers in its own grants database, and a grant it does not know fails the whole draft.

The item is a draft's metadata. It never asks Zenodo to reserve or register a DOI, and nothing the
harness sends publishes it (invariant 14).
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from typing import Any

from dd_sdk.transports import RenderedItem, Transport

# The properties the mapping places, and those it reads but Zenodo fills itself or that every
# deposit has: what is left of a record is reported as unplaced.
_PLACED = frozenset(
    {
        "titles",
        "creators",
        "descriptions",
        "types",
        "subjects",
        "rightsList",
        "relatedIdentifiers",
    }
)
_ZENODO_FILLS = frozenset(
    {"identifiers", "doi", "publisher", "publicationYear", "schemaVersion", "url", "language"}
)
_UPLOAD_TYPES = {"Dataset": "dataset", "Software": "software"}
_ORCID = "https://orcid.org/"


def render(attributes: Mapping[str, Any], target: str | None) -> RenderedItem:
    """The deposition's metadata, as `{"metadata": ...}` in compact, key-sorted JSON so that the
    same record always renders to the same bytes, and the properties left unplaced."""
    unplaced: list[str] = []
    metadata: dict[str, Any] = {
        "upload_type": _upload_type(attributes, unplaced),
        "access_right": "open",
    }
    titles = list(_values(attributes.get("titles"), "title"))
    if titles:
        metadata["title"] = titles[0]
        if len(titles) > 1:
            unplaced.append("titles (all but the first)")
    creators = [_creator(c) for c in attributes.get("creators") or [] if isinstance(c, dict)]
    if creators := [c for c in creators if c]:
        metadata["creators"] = creators
    description = _description(attributes.get("descriptions"))
    if description:
        metadata["description"] = description
    if keywords := list(_values(attributes.get("subjects"), "subject")):
        metadata["keywords"] = keywords
    licence = _licence(attributes.get("rightsList"))
    if licence:
        metadata["license"] = licence
    elif attributes.get("rightsList"):
        unplaced.append("rightsList")
    if related := _related(attributes.get("relatedIdentifiers")):
        metadata["related_identifiers"] = related
    if target:
        metadata["communities"] = [{"identifier": target}]
    unplaced += sorted(
        key for key, value in attributes.items() if value and key not in _PLACED | _ZENODO_FILLS
    )
    content = json.dumps(
        {"metadata": metadata}, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return RenderedItem(content, tuple(unplaced))


def _values(entries: Any, key: str) -> Iterator[str]:
    for entry in entries if isinstance(entries, list) else []:
        value = entry.get(key) if isinstance(entry, dict) else entry
        if isinstance(value, str) and value.strip():
            yield value.strip()


def _upload_type(attributes: Mapping[str, Any], unplaced: list[str]) -> str:
    types = attributes.get("types")
    general = types.get("resourceTypeGeneral") if isinstance(types, dict) else None
    if isinstance(general, str) and general in _UPLOAD_TYPES:
        return _UPLOAD_TYPES[general]
    if general:
        unplaced.append("types.resourceTypeGeneral")
    return "other" if general else "dataset"


def _creator(entry: Mapping[str, Any]) -> dict[str, str] | None:
    name = entry.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    creator = {"name": name.strip()}
    for identifier in entry.get("nameIdentifiers") or []:
        if not isinstance(identifier, dict):
            continue
        value = identifier.get("nameIdentifier")
        if identifier.get("nameIdentifierScheme") == "ORCID" and isinstance(value, str):
            creator["orcid"] = value.removeprefix(_ORCID).strip("/")
            break
    affiliations = list(_values(entry.get("affiliation"), "name"))
    if affiliations:
        creator["affiliation"] = affiliations[0]
    return creator


def _description(entries: Any) -> str | None:
    found = [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []
    abstract = [e for e in found if e.get("descriptionType") == "Abstract"] or found
    texts = list(_values(abstract, "description"))
    return texts[0] if texts else None


def _licence(entries: Any) -> str | None:
    for entry in entries if isinstance(entries, list) else []:
        identifier = entry.get("rightsIdentifier") if isinstance(entry, dict) else None
        if isinstance(identifier, str) and identifier.strip():
            return identifier.strip().lower()
    return None


def _related(entries: Any) -> list[dict[str, str]]:
    found = []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        identifier, relation = entry.get("relatedIdentifier"), entry.get("relationType")
        if isinstance(identifier, str) and isinstance(relation, str) and relation:
            found.append({"identifier": identifier, "relation": relation[0].lower() + relation[1:]})
    return found


TRANSPORT = Transport(
    name="zenodo", format="zenodo-deposit", media_type="application/json", render=render
)
