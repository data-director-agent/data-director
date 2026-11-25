"""The Zenodo transport's item: the approved metadata record, read as its pivot, rendered as the
`metadata` of a Zenodo deposition (docs/specs/deposit.md, Depositing through an API; TODO(#648)
for the rest).

The mapping is the platform item's packager. It reads the pivot terms the record's standard's
definition gives its properties (docs/specs/metadata-standards.md), so a record in any registered
standard renders, and writes the members of Zenodo's deposition metadata
(https://developers.zenodo.org/#representation):

| Pivot term | Zenodo |
|---|---|
| `schema:name` (the first) | `title` |
| `schema:creator`, with its ORCID identifier and affiliation | `creators` |
| `schema:description` (the one of `dcterms:type` Abstract, else the first) | `description` |
| `schema:additionalType` | `upload_type`: `dataset`, `software`, else `other` |
| `schema:keywords`, then `schema:about` | `keywords` |
| `schema:license` (the first identifier) | `license`, lower case, as Zenodo names licences |
| `schema:citation`, with its `dcterms:type` | `related_identifiers`: `identifier`, `relation` |
| the connector's `target` | `communities` |

Every other value the record has, under a term or under none, is reported as unplaced, by its
property's path in the record's standard, on the deposit's outcome, never dropped silently.
Funding is among them: Zenodo takes a grant only by its funder's and award's identifiers in its
own grants database, and a grant it does not know fails the whole draft. The upload types and
the relation vocabulary Zenodo takes are DataCite's, so a record in another standard places
them only where its values are DataCite's.

The item is a draft's metadata. It never asks Zenodo to reserve or register a DOI, and nothing the
harness sends publishes it (invariant 14).
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from typing import Any, Final

from dd_metadata_records import Node, Pivot
from dd_sdk.transports import RenderedItem, Transport

SCHEMA: Final = "http://schema.org/"
DCTERMS: Final = "http://purl.org/dc/terms/"
_NAME, _CREATOR, _DESCRIPTION = SCHEMA + "name", SCHEMA + "creator", SCHEMA + "description"
_TYPE, _KEYWORDS, _ABOUT = SCHEMA + "additionalType", SCHEMA + "keywords", SCHEMA + "about"
_LICENSE, _CITATION = SCHEMA + "license", SCHEMA + "citation"
_IDENTIFIER, _PROPERTY_ID = SCHEMA + "identifier", SCHEMA + "propertyID"
_AFFILIATION, _KIND = SCHEMA + "affiliation", DCTERMS + "type"
# The terms the mapping places, and those Zenodo fills itself or that every deposit has: a value
# under any other term is reported as unplaced.
_PLACED: Final = frozenset(
    {_NAME, _CREATOR, _DESCRIPTION, _TYPE, _KEYWORDS, _ABOUT, _LICENSE, _CITATION}
)
_ZENODO_FILLS: Final = frozenset(
    {
        "http://schema.org/identifier",
        "http://schema.org/publisher",
        "http://schema.org/datePublished",
        "http://schema.org/schemaVersion",
        "http://schema.org/url",
        "http://schema.org/inLanguage",
    }
)
_UPLOAD_TYPES = {"Dataset": "dataset", "Software": "software"}
_ORCID = "https://orcid.org/"


def render(pivot: Mapping[str, Any], target: str | None) -> RenderedItem:
    """The deposition's metadata, as `{"metadata": ...}` in compact, key-sorted JSON so that the
    same record always renders to the same bytes, and the properties left unplaced."""
    unplaced: list[str] = []
    metadata: dict[str, Any] = {
        "upload_type": _upload_type(pivot, unplaced),
        "access_right": "open",
    }
    titles = list(_values(pivot.get(_NAME)))
    if titles:
        metadata["title"] = titles[0]
        if len(titles) > 1:
            unplaced.append(f"{_paths(pivot, _NAME)[0]} (all but the first)")
    if creators := [c for c in map(_creator, pivot.get(_CREATOR, ())) if c]:
        metadata["creators"] = creators
    description = _description(pivot.get(_DESCRIPTION, ()))
    if description:
        metadata["description"] = description
    if keywords := [*_values(pivot.get(_KEYWORDS)), *_values(pivot.get(_ABOUT))]:
        metadata["keywords"] = keywords
    licence = _licence(pivot.get(_LICENSE, ()))
    if licence:
        metadata["license"] = licence
    elif pivot.get(_LICENSE):
        unplaced += _paths(pivot, _LICENSE)
    if related := _related(pivot.get(_CITATION, ())):
        metadata["related_identifiers"] = related
    if target:
        metadata["communities"] = [{"identifier": target}]
    left = {
        node.path
        for term, nodes in pivot.items()
        if term not in _PLACED | _ZENODO_FILLS
        for node in nodes
    }
    unmapped = pivot.unmapped if isinstance(pivot, Pivot) else ()
    unplaced += sorted(left | set(unmapped))
    content = json.dumps(
        {"metadata": metadata}, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return RenderedItem(content, tuple(unplaced))


def _paths(pivot: Mapping[str, Any], term: str) -> list[str]:
    return list(dict.fromkeys(node.path for node in pivot.get(term, ())))


def _values(nodes: Any) -> Iterator[str]:
    for node in nodes or ():
        if node.value is not None:
            yield node.value


def _upload_type(pivot: Mapping[str, Any], unplaced: list[str]) -> str:
    general = next(_values(pivot.get(_TYPE)), None)
    if general in _UPLOAD_TYPES:
        return _UPLOAD_TYPES[general]
    if general:
        unplaced += _paths(pivot, _TYPE)
    return "other" if general else "dataset"


def _creator(node: Node) -> dict[str, str] | None:
    if node.value is None:
        return None
    creator = {"name": node.value}
    for identifier in node.parts.get(_IDENTIFIER, ()):
        if identifier.value is not None and identifier.part(_PROPERTY_ID)[:1] == ["ORCID"]:
            creator["orcid"] = identifier.value.removeprefix(_ORCID).strip("/")
            break
    if affiliations := node.part(_AFFILIATION):
        creator["affiliation"] = affiliations[0]
    return creator


def _description(nodes: tuple[Node, ...]) -> str | None:
    abstract = [n for n in nodes if n.part(_KIND)[:1] == ["Abstract"]] or list(nodes)
    return next(_values(abstract), None)


def _licence(nodes: tuple[Node, ...]) -> str | None:
    for node in nodes:
        if identifiers := node.part(_IDENTIFIER):
            return identifiers[0].lower()
    return None


def _related(nodes: tuple[Node, ...]) -> list[dict[str, str]]:
    found = []
    for node in nodes:
        relation = node.part(_KIND)
        if node.value is not None and relation:
            found.append(
                {"identifier": node.value, "relation": relation[0][0].lower() + relation[0][1:]}
            )
    return found


TRANSPORT = Transport(
    name="zenodo", format="zenodo-deposit", media_type="application/json", render=render
)
