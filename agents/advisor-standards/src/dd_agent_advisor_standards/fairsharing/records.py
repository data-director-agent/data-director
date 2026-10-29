"""A FAIRsharing record as the workbench sees it, and the projections from the two routes.

Two routes return different shapes:

- the **public record route** (`GET https://fairsharing.org/<id>` with `Accept: application/json`,
  no account) returns a flat object with `id`, `name`, `abbreviation`, `registry`, `type`,
  `metadata{doi,status,description,homepage,…}`, `tags{subjects,domains,…}` and a licence line;
- the **authenticated API** (`api.fairsharing.org`) returns JSON:API with the same information
  under `data[].attributes` and `record_type` / `fairsharing_registry` keys.

Both are projected to `Record`, so evidence hashes agree across routes.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from dd_sdk.evidence import content_hash

PUBLIC_RECORD_URL = "https://fairsharing.org/{id}"
LICENCE_NOTE = (
    "FAIRsharing content is CC BY-SA 4.0; attribution: https://fairsharing.org and "
    "https://api.fairsharing.org/img/fairsharing-attribution.svg"
)

# FAIRsharing's own record_type slugs for standards. Read from the registry where possible
# (R3.5); these constants are used only to build queries, never to enumerate standards.
TERMINOLOGY = "terminology_artefact"
MODEL_AND_FORMAT = "model_and_format"
IDENTIFIER_SCHEMA = "identifier_schema"
REPORTING_GUIDELINE = "reporting_guideline"


class Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    fairsharing_id: str
    """The `FAIRsharing.xxxxx` identifier taken from the DOI suffix where present, else the
    numeric id. This is what recommendations cite and the linter matches on."""
    numeric_id: str | None = None
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
    subject_iris: list[str] = Field(default_factory=list)
    source_uri: str | None = None

    @property
    def url(self) -> str:
        return f"https://fairsharing.org/{self.fairsharing_id}"

    def hash_projection(self) -> dict[str, Any]:
        return {
            "fairsharing_id": self.fairsharing_id,
            "doi": self.doi,
            "name": self.name,
            "abbreviation": self.abbreviation,
            "record_type": self.record_type,
            "status": self.status,
            "description": self.description,
            "subjects": self.subjects,
            "domains": self.domains,
        }

    def content_hash(self) -> str:
        return content_hash(self.hash_projection())

    def search_text(self) -> str:
        parts = [
            self.name,
            self.abbreviation or "",
            self.description or "",
            *self.subjects,
            *self.domains,
        ]
        return " ".join(p for p in parts if p)


def _id_from_doi(doi: str | None, fallback: str) -> str:
    if doi and doi.startswith("10.25504/"):
        return doi.removeprefix("10.25504/")
    return fallback


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


def _iris(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return [str(i["iri"]) for i in items if isinstance(i, dict) and i.get("iri")]


def from_public_json(data: dict[str, Any], source_uri: str | None = None) -> Record:
    meta = data.get("metadata") or {}
    tags = data.get("tags") or {}
    numeric = str(data.get("id") or meta.get("identifier") or "")
    doi = meta.get("doi")
    return Record(
        fairsharing_id=_id_from_doi(doi, numeric),
        numeric_id=numeric or None,
        doi=doi,
        name=str(meta.get("name") or data.get("name") or ""),
        abbreviation=meta.get("abbreviation") or data.get("abbreviation"),
        registry=data.get("registry"),
        record_type=data.get("type"),
        status=meta.get("status"),
        description=meta.get("description"),
        homepage=meta.get("homepage"),
        subjects=_labels(tags.get("subjects")),
        domains=_labels(tags.get("domains")),
        subject_iris=_iris(tags.get("subjects")),
        source_uri=source_uri,
    )


def from_api_json(item: dict[str, Any], source_uri: str | None = None) -> Record:
    """JSON:API `data[]` item from api.fairsharing.org."""
    attrs = item.get("attributes") or {}
    meta = attrs.get("metadata") or {}
    numeric = str(item.get("id") or "")
    doi = meta.get("doi")
    return Record(
        fairsharing_id=_id_from_doi(doi, numeric),
        numeric_id=numeric or None,
        doi=doi,
        name=str(meta.get("name") or attrs.get("name") or ""),
        abbreviation=meta.get("abbreviation") or attrs.get("abbreviation"),
        registry=attrs.get("fairsharing_registry"),
        record_type=attrs.get("record_type"),
        status=meta.get("status"),
        description=meta.get("description"),
        homepage=meta.get("homepage"),
        subjects=_labels(attrs.get("subjects")),
        domains=_labels(attrs.get("domains")),
        source_uri=source_uri,
    )
