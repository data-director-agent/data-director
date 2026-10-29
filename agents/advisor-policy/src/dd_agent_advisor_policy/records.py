"""A FAIRsharing policy record, and how it is read from FAIRsharing's two routes.

- The **public record route** (`GET https://fairsharing.org/<id>` with `Accept: application/json`,
  no account) returns the record with `metadata`, `tags` and `type`, but no relations.
- The **authenticated API** (`api.fairsharing.org`) returns JSON:API: the same `metadata` under
  `data.attributes`, flat `subjects` and `countries`, `record_type`, and the record's relations
  to other records in `linked_records`.

Both are projected to `PolicyRecord`. A record is stored in the snapshot exactly as it is
hashed: the whole document, under `dd-json-document-v1` (ADR-0009). Lists are sorted when the
record is made, so the hash does not depend on the order a route lists things in. Evidence
`content` is the same document, so what the reader is shown is what the hash covers (ADR-0015).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from dd_sdk.evidence import DOCUMENT_CANONICALISATION, content_hash

PUBLIC_RECORD_URL = "https://fairsharing.org/{id}"
DOI_PREFIX = "10.25504/"

# The structured fields of a FAIRsharing policy record that this agent keeps, each a small
# object of curated values and free-text `notes`. Contacts, citations and support links are not
# kept: they are personal data or not about the policy's obligations.
CLAUSES = (
    "sharing_data",
    "data_availability_statement",
    "licences_for_outputs",
    "dmp_development",
    "data_preservation",
    "data_citation",
    "sharing_metadata",
    "sharing_research_software",
    "data_protection",
    "supported_costs",
    "compliance",
)


class Clause(BaseModel):
    """One structured field of a policy record, as FAIRsharing's curators recorded it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # The curated values, such as {"mandated_data_sharing": "required"}, as strings.
    values: dict[str, str] = Field(default_factory=dict)
    notes: str | None = None


class Relation(BaseModel):
    """A link from the policy to another FAIRsharing record, such as a database it recommends."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    relation: str
    registry: str | None = None
    record_type: str | None = None
    name: str
    numeric_id: str | None = None


def _sorted(values: list[str]) -> list[str]:
    return sorted(set(values))


class PolicyRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    fairsharing_id: str
    """The `FAIRsharing.xxxxx` identifier from the DOI suffix: what the payload cites."""
    numeric_id: str | None = None
    doi: str | None = None
    name: str
    abbreviation: str | None = None
    # FAIRsharing's policy type: funder, journal, journal_publisher, institution, society, project.
    policy_type: str | None = None
    status: str | None = None
    homepage: str | None = None
    description: str | None = None
    subjects: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    # A string, not an integer: the A2A transport carries evidence content as a protobuf Struct,
    # whose numbers are doubles, so 2000 would arrive as 2000.0 and no longer hash alike.
    year_creation: str | None = None
    clauses: dict[str, Clause] = Field(default_factory=dict)
    relations: list[Relation] = Field(default_factory=list)

    @field_validator("subjects", "countries")
    @classmethod
    def _sort(cls, values: list[str]) -> list[str]:
        return _sorted(values)

    @field_validator("relations")
    @classmethod
    def _sort_relations(cls, values: list[Relation]) -> list[Relation]:
        unique = {(r.relation, r.registry, r.name, r.numeric_id): r for r in values}
        return [unique[k] for k in sorted(unique, key=lambda k: tuple(x or "" for x in k))]

    @property
    def source_uri(self) -> str:
        return PUBLIC_RECORD_URL.format(id=self.fairsharing_id)

    def document(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def content_hash(self) -> str:
        return content_hash(self.document(), DOCUMENT_CANONICALISATION)

    def clause(self, name: str) -> Clause:
        return self.clauses.get(name) or Clause()

    def search_text(self) -> str:
        return " ".join(
            p for p in (self.name, self.abbreviation or "", self.description or "") if p
        )

    def names(self) -> list[str]:
        """The name and abbreviation, case-folded, for matching an actor's name."""
        return [n.casefold() for n in (self.name, self.abbreviation) if n]


def _scalar(value: Any) -> str | None:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, str | int | float):
        text = str(value).strip()
        return text or None
    return None


def _clauses(meta: dict[str, Any]) -> dict[str, Clause]:
    out: dict[str, Clause] = {}
    for name in CLAUSES:
        raw = meta.get(name)
        if not isinstance(raw, dict):
            continue
        values = {
            k: v for k, v in ((k, _scalar(raw[k])) for k in raw if k != "notes") if v is not None
        }
        notes = _scalar(raw.get("notes"))
        if values or notes:
            out[name] = Clause(values=values, notes=notes)
    return out


def _labels(items: Any, key: str) -> list[str]:
    if not isinstance(items, list):
        return []
    out: list[str] = []
    for item in items:
        if isinstance(item, dict) and item.get(key):
            out.append(str(item[key]))
        elif isinstance(item, str) and item:
            out.append(item)
    return out


def _year(value: Any) -> str | None:
    try:
        return str(int(value))
    except TypeError, ValueError:
        return None


def _relations(items: Any) -> list[Relation]:
    if not isinstance(items, list):
        return []
    return [
        Relation(
            relation=str(item["relation"]),
            registry=item.get("linked_record_registry"),
            record_type=item.get("linked_record_type"),
            name=str(item["linked_record_name"]),
            numeric_id=_scalar(item.get("linked_record_id")),
        )
        for item in items
        if isinstance(item, dict) and item.get("relation") and item.get("linked_record_name")
    ]


def _record(
    meta: dict[str, Any],
    numeric: str | None,
    policy_type: Any,
    abbreviation: Any,
    subjects: list[str],
    countries: list[str],
    relations: list[Relation],
) -> PolicyRecord | None:
    doi = meta.get("doi")
    name = meta.get("name")
    if not name or not doi or not str(doi).startswith(DOI_PREFIX):
        return None
    return PolicyRecord(
        fairsharing_id=str(doi).removeprefix(DOI_PREFIX),
        numeric_id=numeric,
        doi=str(doi),
        name=str(name),
        abbreviation=meta.get("abbreviation") or abbreviation or None,
        policy_type=policy_type or None,
        status=meta.get("status"),
        homepage=meta.get("homepage"),
        description=meta.get("description"),
        subjects=subjects,
        countries=countries,
        year_creation=_year(meta.get("year_creation")),
        clauses=_clauses(meta),
        relations=relations,
    )


def from_public_json(data: dict[str, Any]) -> PolicyRecord | None:
    """A policy record from the public route. None if it is not a policy record."""
    if str(data.get("registry", "")).casefold() != "policy":
        return None
    tags = data.get("tags") or {}
    return _record(
        data.get("metadata") or {},
        _scalar(data.get("id")),
        data.get("type"),
        data.get("abbreviation"),
        _labels(tags.get("subjects"), "label"),
        _labels(tags.get("countries"), "name"),
        [],
    )


def from_api_json(item: dict[str, Any]) -> PolicyRecord | None:
    """A JSON:API `data` item from api.fairsharing.org. None if it is not a policy record."""
    attrs = item.get("attributes") or {}
    if str(attrs.get("fairsharing_registry", "")).casefold() != "policy":
        return None
    return _record(
        attrs.get("metadata") or {},
        _scalar(item.get("id")),
        attrs.get("record_type"),
        attrs.get("abbreviation"),
        _labels(attrs.get("subjects"), "label"),
        _labels(attrs.get("countries"), "name"),
        _relations(attrs.get("linked_records")),
    )
