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
    """What a client cites: identified by `id`, with no integers."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    """`FAIRsharing.xxxxx` where the record has a DOI (its suffix), else the numeric id."""
    name: str
    url: str
    licence: str = LICENCE
    doi: str | None = None
    abbreviation: str | None = None
    homepage: str | None = None
    description: str | None = None
    status: str | None = None
    registry: str | None = None
    record_type: str | None = None
    subjects: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)

    def document(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def _labels(tags: Any) -> list[str]:
    """The labels in a list of tags, each either a string or an object with a `label`."""
    wanted = tags if isinstance(tags, list) else []
    return [
        str(label)
        for tag in wanted
        if (label := tag.get("label") if isinstance(tag, dict) else tag)
    ]


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
    ident = doi.removeprefix(DOI_PREFIX) if doi and doi.startswith(DOI_PREFIX) else numeric
    return Record(
        id=ident,
        url=PUBLIC_RECORD_URL.format(id=ident),
        name=str(meta.get("name") or top.get("name") or ""),
        doi=doi,
        abbreviation=_text(meta.get("abbreviation") or top.get("abbreviation")),
        homepage=_text(meta.get("homepage")),
        description=_text(meta.get("description")),
        status=_text(meta.get("status")),
        registry=_text(registry),
        record_type=_text(record_type),
        subjects=_labels(tags.get("subjects")),
        domains=_labels(tags.get("domains")),
    )


def from_public_json(data: dict[str, Any]) -> Record | None:
    """The public route's object as a record; None when it is an error shaped as JSON."""
    meta = data.get("metadata") or {}
    if not (data.get("name") or meta.get("name")):
        return None
    return _record(
        str(data.get("id") or meta.get("identifier") or ""),
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
