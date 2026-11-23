"""The input and payload classes of advisor.linking, as Pydantic models (docs/specs/contract.md).

`schema/linking.yaml` is the source; `ClassSchema.of` compares each model with the schema generated
from it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from dd_sdk.contract.models import Derivation, Frozen, Grounded


class LinkCandidates(Frozen):
    schema_class: Literal["LinkCandidates"] = "LinkCandidates"
    identifiers: list[str] = Field(default_factory=list)


class GrantCandidate(Frozen):
    id: str
    award: str | None = None
    title: str | None = None
    funder: str | None = None
    funder_identifier: str | None = None
    funding_stream: str | None = None
    source: str


class RelatedLink(Frozen):
    given: str
    scheme: str
    normalised: str | None = None
    relation: str | None = None
    valid: bool
    resolved: bool | None = None
    title: str | None = None
    resource_type: str | None = None
    candidates: list[GrantCandidate] = Field(default_factory=list)
    message: str


class RelatedIdentifiers(Grounded):
    schema_class: Literal["RelatedIdentifiers"] = "RelatedIdentifiers"
    links: list[RelatedLink] = Field(default_factory=list)
    summary: str | None = None
    summary_derivation: Derivation | None = None
    limitations: list[str] = Field(default_factory=list)
