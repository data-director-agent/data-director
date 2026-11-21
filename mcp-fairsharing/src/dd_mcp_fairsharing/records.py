"""A FAIRsharing record as this server answers it, projected from FAIRsharing's two routes.

- The public record route (`GET https://fairsharing.org/<id>`, `Accept: application/json`, no
  account) returns a flat object: `id`, `name`, `registry`, `type`, `metadata{...}`, `tags{...}`.
- The authenticated API (`api.fairsharing.org`) returns JSON:API: the same under
  `data[].attributes`, with `record_type` and `fairsharing_registry`.

Both give the same `Record`, so a record's content does not depend on the route that found it.
FAIRsharing content is CC BY-SA 4.0 and each record says so.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

PUBLIC_RECORD_URL = "https://fairsharing.org/{id}"
DOI_PREFIX = "10.25504/"
LICENCE = "FAIRsharing content is CC BY-SA 4.0; attribution: https://fairsharing.org"


class Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    """`FAIRsharing.xxxxx` (from the DOI suffix) where the record has a DOI, else the numeric id.
    This is the field a client identifies the record by."""
    doi: str | None = None
    name: str
    abbreviation: str | None = None
    registry: str | None = None
    record_type: str | None = None
    status: str | None = None
    description: str | None = None
    homepage: str | None = None
    subjects: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    url: str
    licence: str = LICENCE

    def document(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def _id(doi: str | None, numeric: str) -> str:
    return doi.removeprefix(DOI_PREFIX) if doi and doi.startswith(DOI_PREFIX) else numeric


def _labels(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    out: list[str] = []
    for item in items:
        if isinstance(item, dict) and item.get("label"):
            out.append(str(item["label"]))
        elif isinstance(item, str):
            out.append(item)
    return out


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _record(
    numeric: str,
    meta: dict[str, Any],
    top: dict[str, Any],
    tags: dict[str, Any],
    *,
    registry: Any,
    record_type: Any,
) -> Record:
    doi = _text(meta.get("doi"))
    ident = _id(doi, numeric)
    return Record(
        id=ident,
        doi=doi,
        name=str(meta.get("name") or top.get("name") or ""),
        abbreviation=_text(meta.get("abbreviation") or top.get("abbreviation")),
        registry=_text(registry),
        record_type=_text(record_type),
        status=_text(meta.get("status")),
        description=_text(meta.get("description")),
        homepage=_text(meta.get("homepage")),
        subjects=_labels(tags.get("subjects")),
        domains=_labels(tags.get("domains")),
        url=PUBLIC_RECORD_URL.format(id=ident),
    )


def from_public_json(data: dict[str, Any]) -> Record | None:
    """The public route's object as a record; None when it is an error shaped as JSON."""
    meta = data.get("metadata") or {}
    if not (data.get("name") or meta.get("name")):
        return None
    numeric = str(data.get("id") or meta.get("identifier") or "")
    return _record(
        numeric,
        meta,
        data,
        data.get("tags") or {},
        registry=data.get("registry"),
        record_type=data.get("type"),
    )


def from_api_json(item: dict[str, Any]) -> Record:
    """A JSON:API `data[]` item from api.fairsharing.org."""
    attrs = item.get("attributes") or {}
    return _record(
        str(item.get("id") or ""),
        attrs.get("metadata") or {},
        attrs,
        attrs,
        registry=attrs.get("fairsharing_registry"),
        record_type=attrs.get("record_type"),
    )
