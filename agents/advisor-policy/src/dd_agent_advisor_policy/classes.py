"""The input and payload classes of advisor.policy, as Pydantic models (docs/specs/contract.md).

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


class ReadingStatus(StrEnum):
    READ = "read"
    NOT_READ = "not_read"
    UNREADABLE = "unreadable"


class PolicyRegistry(StrEnum):
    FAIRSHARING = "fairsharing"
    OPEN_POLICY_FINDER = "open_policy_finder"


class PolicyScope(StrEnum):
    DATA = "data"
    PUBLICATION = "publication"


class Strength(StrEnum):
    REQUIRED = "required"
    RECOMMENDED = "recommended"
    UNSTATED = "unstated"


class Actor(Frozen):
    role: ActorRole
    name: str
    fairsharing_id: str | None = Field(default=None, pattern=r"^FAIRsharing\.\S+$")
    ror_id: str | None = Field(default=None, pattern=r"^(https?://ror\.org/)?0[a-z0-9]{6}[0-9]{2}$")
    issn: str | None = Field(default=None, pattern=r"^\d{4}-?\d{3}[\dXx]$")
    policy_url: str | None = Field(default=None, pattern=r"^https?://\S+$")


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
    scope: PolicyScope | None = None
    value: str | None = None
    quote: str | None = None
    derivation: Derivation | None = None


class MatchedPolicy(Grounded):
    """Names its policy only in `grounded_on`; the record is in evidence
    (docs/specs/grounding.md)."""

    actor: str
    role: ActorRole
    registry: PolicyRegistry
    match_derivation: Derivation
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


class ResolvedFunder(Grounded):
    """A funder identified in ROR. Names its ROR record only in `grounded_on`."""

    actor: str
    crossref_funder_id: str | None = None


class StatedObligation(Frozen):
    kind: ObligationKind
    strength: Strength
    value: str
    quote: str


class PolicyReading(Grounded):
    """What a model read in one policy's own text. Grounded on the text, and on the policy
    record it was reached from, if any."""

    actor: str
    role: ActorRole
    status: ReadingStatus
    stated: list[StatedObligation] = Field(default_factory=list)
    dropped: list[str] = Field(default_factory=list)
    reason: str | None = None


class ResolvedJournal(Grounded):
    """A journal identified in Crossref or Open Policy Finder, with its publisher. Names its
    record only in `grounded_on`."""

    actor: str
    publisher: str | None = None
    issn: str | None = Field(default=None, pattern=r"^\d{4}-?\d{3}[\dXx]$")


class AmbiguousActor(Grounded):
    """A funder or journal whose name could mean more than one. Grounded on each candidate,
    likeliest first."""

    actor: str
    role: ActorRole


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
    readings: list[PolicyReading] = Field(default_factory=list)
    funders: list[ResolvedFunder] = Field(default_factory=list)
    journals: list[ResolvedJournal] = Field(default_factory=list)
    ambiguous: list[AmbiguousActor] = Field(default_factory=list)
    searched: SearchedSummary | None = None
    limitations: list[str] = Field(default_factory=list)
