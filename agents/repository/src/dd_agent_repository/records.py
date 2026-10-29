"""The two kinds of registry record this agent cites, and how each is read from its source.

- **re3data** answers `GET https://www.re3data.org/api/v1/repository/<id>` with an XML record
  (schema 2.2). `from_re3data_xml` keeps the fields Phase 3 asks about and drops contacts.
- **FAIRsharing** answers `GET https://fairsharing.org/<id>` with `Accept: application/json`, no
  account needed. `from_fairsharing_json` keeps the database fields re3data does not have.

Each record is stored in the snapshot exactly as it is hashed: the whole JSON document, under
`dd-json-document-v1` (ADR-0009). Lists are sorted when the record is made, so the hash does not
depend on the order a source happens to list things in. Evidence `content` is the same document,
so what the reader is shown is what the hash covers (ADR-0015).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from dd_sdk.evidence import DOCUMENT_CANONICALISATION, content_hash

RE3DATA_RECORD_URL = "https://www.re3data.org/api/v1/repository/{id}"
FAIRSHARING_RECORD_URL = "https://fairsharing.org/{id}"
FAIRSHARING_DOI_PREFIX = "10.25504/"

_NS = {"r3d": "http://www.re3data.org/schema/2-2"}


class Institution(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    country: str | None = None
    # re3data's institutionType: commercial or non-profit, when the record says.
    type: str | None = None
    # re3data's responsibilityType: general, funding, technical, sponsoring.
    responsibilities: list[str] = Field(default_factory=list)
    # The bare ROR identifier (05krs5044), from re3data's institutionIdentifier.
    ror: str | None = None

    @field_validator("responsibilities")
    @classmethod
    def _sort(cls, values: list[str]) -> list[str]:
        return _sorted(values)


def _sorted(values: list[str]) -> list[str]:
    return sorted(set(values))


class Re3dataRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    re3data_id: str
    doi: str | None = None
    name: str
    additional_names: list[str] = Field(default_factory=list)
    url: str | None = None
    description: str | None = None
    types: list[str] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    content_types: list[str] = Field(default_factory=list)
    institutions: list[Institution] = Field(default_factory=list)
    data_access_types: list[str] = Field(default_factory=list)
    data_access_restrictions: list[str] = Field(default_factory=list)
    data_upload_types: list[str] = Field(default_factory=list)
    data_upload_restrictions: list[str] = Field(default_factory=list)
    data_licences: list[str] = Field(default_factory=list)
    pid_systems: list[str] = Field(default_factory=list)
    certificates: list[str] = Field(default_factory=list)
    quality_management: str | None = None
    metadata_standards: list[str] = Field(default_factory=list)
    fairsharing_id: str | None = None
    last_update: str | None = None

    @field_validator(
        "additional_names",
        "types",
        "subjects",
        "keywords",
        "content_types",
        "data_access_types",
        "data_access_restrictions",
        "data_upload_types",
        "data_upload_restrictions",
        "data_licences",
        "pid_systems",
        "certificates",
        "metadata_standards",
    )
    @classmethod
    def _sort(cls, values: list[str]) -> list[str]:
        return _sorted(values)

    @field_validator("institutions")
    @classmethod
    def _sort_institutions(cls, values: list[Institution]) -> list[Institution]:
        return sorted(values, key=lambda i: (i.name, i.country or "", i.type or "", i.ror or ""))

    @property
    def source_uri(self) -> str:
        return RE3DATA_RECORD_URL.format(id=self.re3data_id)

    def document(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def content_hash(self) -> str:
        return content_hash(self.document(), DOCUMENT_CANONICALISATION)

    def search_text(self) -> str:
        parts = [
            self.name,
            *self.additional_names,
            self.description or "",
            *self.subjects,
            *self.keywords,
            *self.content_types,
        ]
        return " ".join(p for p in parts if p)

    def names(self) -> set[str]:
        return {n.casefold().strip() for n in (self.name, *self.additional_names)}


class DatabaseRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    fairsharing_id: str
    doi: str | None = None
    name: str
    abbreviation: str | None = None
    status: str | None = None
    homepage: str | None = None
    subjects: list[str] = Field(default_factory=list)
    access_condition: str | None = None
    access_notes: str | None = None
    deposition_condition: str | None = None
    deposition_notes: str | None = None
    curation: str | None = None
    pre_publication_review: str | None = None
    re3data_ids: list[str] = Field(default_factory=list)

    @field_validator("subjects", "re3data_ids")
    @classmethod
    def _sort(cls, values: list[str]) -> list[str]:
        return _sorted(values)

    @property
    def source_uri(self) -> str:
        return FAIRSHARING_RECORD_URL.format(id=self.fairsharing_id)

    def document(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def content_hash(self) -> str:
        return content_hash(self.document(), DOCUMENT_CANONICALISATION)


# --- re3data XML ------------------------------------------------------------------------------


def _texts(parent: ET.Element, path: str) -> list[str]:
    return [e.text.strip() for e in parent.findall(path, _NS) if e.text and e.text.strip()]


def _text(parent: ET.Element, path: str) -> str | None:
    found = _texts(parent, path)
    return found[0] if found else None


def _ror(identifiers: list[str]) -> str | None:
    for identifier in identifiers:
        if identifier.upper().startswith("ROR:"):
            return bare_ror(identifier[4:])
    return None


def bare_ror(value: str) -> str:
    """`05krs5044` from `https://ror.org/05krs5044`, `ror.org/05krs5044` or itself."""
    return value.strip().rstrip("/").rsplit("/", 1)[-1].lower()


def from_re3data_xml(body: str | bytes) -> Re3dataRecord | None:
    """One re3data record. None when the body holds no repository (an unknown identifier).

    The standard library's parser does not fetch external entities, and the expat it ships with
    limits entity expansion, so a hostile record cannot reach the network or exhaust memory.
    """
    root = ET.fromstring(body)
    repo = root.find("r3d:repository", _NS)
    if repo is None:
        return None
    re3data_id = _text(repo, "r3d:re3data.orgIdentifier")
    name = _text(repo, "r3d:repositoryName")
    if not re3data_id or not name:
        return None
    identifiers = _texts(repo, "r3d:repositoryIdentifier")
    fairsharing = next(
        (i.removeprefix(FAIRSHARING_DOI_PREFIX) for i in identifiers if "FAIRsharing." in i), None
    )
    institutions = [
        Institution(
            name=_text(i, "r3d:institutionName") or "",
            country=_text(i, "r3d:institutionCountry"),
            type=_text(i, "r3d:institutionType"),
            responsibilities=_texts(i, "r3d:responsibilityType"),
            ror=_ror(_texts(i, "r3d:institutionIdentifier")),
        )
        for i in repo.findall("r3d:institution", _NS)
        if _text(i, "r3d:institutionName")
    ]
    return Re3dataRecord(
        re3data_id=re3data_id,
        doi=_text(repo, "r3d:doi") or None,
        name=name,
        additional_names=_texts(repo, "r3d:additionalName"),
        url=_text(repo, "r3d:repositoryURL"),
        description=_text(repo, "r3d:description"),
        types=_texts(repo, "r3d:type"),
        subjects=_texts(repo, "r3d:subject"),
        keywords=_texts(repo, "r3d:keyword"),
        content_types=_texts(repo, "r3d:contentType"),
        institutions=institutions,
        data_access_types=_texts(repo, "r3d:dataAccess/r3d:dataAccessType"),
        data_access_restrictions=_texts(repo, "r3d:dataAccess/r3d:dataAccessRestriction"),
        data_upload_types=_texts(repo, "r3d:dataUpload/r3d:dataUploadType"),
        data_upload_restrictions=_texts(repo, "r3d:dataUpload/r3d:dataUploadRestriction"),
        data_licences=_texts(repo, "r3d:dataLicense/r3d:dataLicenseName"),
        pid_systems=_texts(repo, "r3d:pidSystem"),
        certificates=_texts(repo, "r3d:certificate"),
        quality_management=_text(repo, "r3d:qualityManagement"),
        metadata_standards=_texts(repo, "r3d:metadataStandard/r3d:metadataStandardName"),
        fairsharing_id=fairsharing,
        last_update=_text(repo, "r3d:lastUpdate"),
    )


def ids_from_re3data_list(body: str | bytes) -> list[str]:
    """The identifiers in a re3data search or list response, in the order given."""
    root = ET.fromstring(body)
    return [e.text.strip() for e in root.iter("id") if e.text and e.text.strip()]


# --- FAIRsharing JSON -------------------------------------------------------------------------


def _labels(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return [str(i["label"]) for i in items if isinstance(i, dict) and i.get("label")]


def _condition(value: Any) -> tuple[str | None, str | None]:
    if not isinstance(value, dict):
        return None, None
    return value.get("type") or None, value.get("notes") or None


def from_fairsharing_json(data: dict[str, Any]) -> DatabaseRecord | None:
    """A FAIRsharing database record from the public route. None if it is not one."""
    meta = data.get("metadata") or {}
    doi = meta.get("doi")
    name = meta.get("name") or data.get("name")
    if not name or not doi or not str(doi).startswith(FAIRSHARING_DOI_PREFIX):
        return None
    access, access_notes = _condition(meta.get("data_access_condition"))
    deposition, deposition_notes = _condition(meta.get("data_deposition_condition"))
    curation = meta.get("data_curation")
    review = meta.get("data_access_for_pre_publication_review")
    re3data_ids = [
        str(x.get("name", "")).removeprefix("re3data:")
        for x in meta.get("cross_references") or []
        if isinstance(x, dict) and x.get("portal") == "re3data"
    ]
    return DatabaseRecord(
        fairsharing_id=str(doi).removeprefix(FAIRSHARING_DOI_PREFIX),
        doi=str(doi),
        name=str(name),
        abbreviation=meta.get("abbreviation") or data.get("abbreviation"),
        status=meta.get("status"),
        homepage=meta.get("homepage"),
        subjects=_labels((data.get("tags") or {}).get("subjects")),
        access_condition=access,
        access_notes=access_notes,
        deposition_condition=deposition,
        deposition_notes=deposition_notes,
        curation=curation.get("type") if isinstance(curation, dict) else None,
        pre_publication_review=review if isinstance(review, str) else None,
        re3data_ids=[i for i in re3data_ids if i],
    )
