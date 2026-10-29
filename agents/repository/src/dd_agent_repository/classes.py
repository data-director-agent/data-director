"""The input and payload classes of repository.advisor, as Pydantic models (ADR-0019).

`schema/repository.yaml` is the source; `ClassSchema.of` compares each model with the schema
generated from it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field

from dd_sdk.contract.models import Derivation, Frozen, Grounded


class AccessNeed(StrEnum):
    OPEN = "open"
    EMBARGOED = "embargoed"
    RESTRICTED = "restricted"


class CandidateBasis(StrEnum):
    MANDATED = "mandated"
    RECOMMENDED = "recommended"


class Answer(StrEnum):
    YES = "yes"
    NO = "no"
    UNSTATED = "unstated"


class RepositoryRef(Frozen):
    name: str
    re3data_id: str | None = Field(default=None, pattern=r"^r3d\d+$")


class Affiliation(Frozen):
    name: str
    ror: str | None = None


class RepositoryNeeds(Frozen):
    schema_class: Literal["RepositoryNeeds"] = "RepositoryNeeds"
    themes: list[str] = Field(default_factory=list)
    data_kinds: list[str] = Field(default_factory=list)
    access: AccessNeed | None = None
    mandated: list[RepositoryRef] = Field(default_factory=list)
    affiliation: Affiliation | None = None


class RepositoryCandidate(Grounded):
    """Names its repository only in `grounded_on`; the facts are in evidence (ADR-0015)."""

    basis: CandidateBasis
    score: float | None = None
    assigns_pids: Answer
    commercial: Answer
    fee_required: Answer
    meets: list[str] = Field(default_factory=list)
    misses: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    rationale: str
    rationale_derivation: Derivation


class SearchedSummary(Frozen):
    queries: list[str] = Field(default_factory=list)
    snapshot_ref: str | None = None
    candidates_retrieved: int | None = None
    candidates_qualifying: int | None = None


class RepositoryOptions(Grounded):
    schema_class: Literal["RepositoryOptions"] = "RepositoryOptions"
    candidates: list[RepositoryCandidate] = Field(default_factory=list)
    not_found: list[str] = Field(default_factory=list)
    searched: SearchedSummary | None = None
