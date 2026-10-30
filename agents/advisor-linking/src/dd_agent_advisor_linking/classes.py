"""The input and payload classes of advisor.linking, as Pydantic models (ADR-0019).

`schema/linking.yaml` is the source; `ClassSchema.of` compares each model with the schema generated
from it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from dd_sdk.contract.models import Frozen, Grounded


class LinkCandidates(Frozen):
    schema_class: Literal["LinkCandidates"] = "LinkCandidates"
    identifiers: list[str] = Field(default_factory=list)


class RelatedLink(Frozen):
    given: str
    scheme: str
    normalised: str | None = None
    relation: str | None = None
    valid: bool
    message: str


class RelatedIdentifiers(Grounded):
    schema_class: Literal["RelatedIdentifiers"] = "RelatedIdentifiers"
    links: list[RelatedLink] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
