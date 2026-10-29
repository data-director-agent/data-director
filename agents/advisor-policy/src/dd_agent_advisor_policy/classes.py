"""The input and payload classes of advisor.policy, as Pydantic models (ADR-0019).

`schema/policy.yaml` is the source; `ClassSchema.of` compares each model with the schema
generated from it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field

from dd_sdk.contract.models import Derivation, Frozen, Grounded


class ActorRole(StrEnum):
    FUNDER = "funder"
    JOURNAL = "journal"
    INSTITUTION = "institution"


class ObligationKind(StrEnum):
    DEPOSIT = "deposit"
    DATA_AVAILABILITY_STATEMENT = "data_availability_statement"
    REPOSITORY = "repository"
    STANDARD = "standard"
    EMBARGO = "embargo"
    LICENCE = "licence"
    TIMING = "timing"


class Strength(StrEnum):
    REQUIRED = "required"
    RECOMMENDED = "recommended"
    UNSTATED = "unstated"


class Actor(Frozen):
    role: ActorRole
    name: str
    fairsharing_id: str | None = Field(default=None, pattern=r"^FAIRsharing\.\S+$")


class PolicyContext(Frozen):
    schema_class: Literal["PolicyContext"] = "PolicyContext"
    actors: list[Actor] = Field(default_factory=list)
    disciplines: list[str] = Field(default_factory=list)
    data_kinds: list[str] = Field(default_factory=list)
    publication_date: str | None = Field(default=None, pattern=r"^\d{4}(-\d{2}(-\d{2})?)?$")


class Obligation(Frozen):
    kind: ObligationKind
    strength: Strength
    recorded_as: str | None = None


class MatchedPolicy(Grounded):
    """Names its policy only in `grounded_on`; the record is in evidence (ADR-0015)."""

    actor: str
    role: ActorRole
    obligations: list[Obligation] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    rationale: str
    rationale_derivation: Derivation


class PolicyConflict(Grounded):
    """Policies that state an obligation differently. Grounded on every policy involved."""

    kind: ObligationKind
    description: str


class RepositoryRef(Frozen):
    name: str
    re3data_id: str | None = Field(default=None, pattern=r"^r3d\d+$")


class SearchedSummary(Frozen):
    queries: list[str] = Field(default_factory=list)
    snapshot_ref: str | None = None
    policies_retrieved: int | None = None


class PolicyChecks(Grounded):
    schema_class: Literal["PolicyChecks"] = "PolicyChecks"
    policies: list[MatchedPolicy] = Field(default_factory=list)
    conflicts: list[PolicyConflict] = Field(default_factory=list)
    mandated_repositories: list[RepositoryRef] = Field(default_factory=list)
    no_record: list[str] = Field(default_factory=list)
    searched: SearchedSummary | None = None
