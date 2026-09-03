"""§6.2 — the recommendations document.

Two properties earn their place, and both are enforced structurally rather than by convention:

- `requires_human_review` is `Literal[True]`, so `False` is a validation error and the JSON
  Schema carries `"const": true`. C15's mandatory review is met by the output format, not by
  whoever builds the interface.
- `nothing_found` is a *sibling* of `recommendations`, never nested inside it, so anything
  displaying the output cannot show the recommendations while ignoring what the system declined
  to do.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field

from standards_advisor.models.common import (
    AgentRef,
    Frozen,
    PromptRef,
    RankingConfigRef,
    RecommendationKind,
    RegistrySnapshotRef,
    ScoreComponent,
)


class ResourceRef(Frozen):
    """The registry record a recommendation names.

    `registry_id` is what the §5.5 grounding check tests against the candidate set. A
    recommendation without one cannot pass, which is the entire mechanism preventing a
    fabricated standard from reaching a reader.
    """

    name: str
    registry_id: str
    doi: str | None = None
    url: str | None = None
    record_type: str | None = None
    record_subtype: str | None = None
    """FAIRsharing's own curator-applied subtype. §5.2 uses it — not a model's judgement — to
    tell an ontology from a controlled vocabulary. §1.2 makes this a stop condition: if the
    subtype is not reliably populated, the one distinction R3 explicitly requires has no
    dependable mechanical basis."""
    status: str | None = None
    """`ready`, `in_development`, `uncertain`, `deprecated`. Kept and shown, never filtered
    out (§5.2) — a deprecated standard a researcher is already using is useful information."""


class TargetKind(StrEnum):
    """What part of the dataset a recommendation applies to.

    `FIELD_VALUES` versus `STRUCTURE` is where §2.1 draws the vocabulary/ontology line: concept
    linkage targets a column's values, ontology alignment targets the dataset's shape.
    """

    FIELD_VALUES = "field_values"
    STRUCTURE = "structure"
    FILE = "file"
    DATASET = "dataset"


class Target(Frozen):
    kind: TargetKind
    field: str | None = None
    file: str | None = None
    detail: str | None = None


class Evidence(Frozen):
    """One factual statement, tied to the registry field that backs it.

    §5.5's evidence check is mechanical: it verifies that `record` and `field` are present and
    resolve, not that the prose is true. That is a deliberate limit — a check that tried to
    understand the sentence would be another thing needing review.
    """

    statement: str
    record: str
    field: str


class Recommendation(Frozen):
    kind: RecommendationKind
    resource: ResourceRef
    target: Target
    score: float
    score_features: dict[str, float] = Field(default_factory=dict)
    score_components: list[ScoreComponent] = Field(default_factory=list)
    """Attributed breakdown — see `ScoreComponent`. An addition to §6.2's sketch."""
    confidence: float
    reason: str
    evidence: list[Evidence] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list)
    """Which registry queries found this candidate (§5.2). Without it a ranking bug cannot be
    diagnosed."""


class NothingFoundReason(StrEnum):
    """Why a kind of recommendation produced nothing.

    Distinguishing these matters: "we searched and nothing qualified" and "we could not
    search" call for different responses from a reader, and collapsing them into one
    'no results' would hide the second.
    """

    NO_QUALIFYING_RESOURCE = "no_qualifying_resource"
    NO_CANDIDATES_RETRIEVED = "no_candidates_retrieved"
    REGISTRY_UNAVAILABLE = "registry_unavailable"
    NOT_APPLICABLE = "not_applicable"
    STAGE_NOT_IMPLEMENTED = "stage_not_implemented"
    """v0.1 only. Honest about a stub rather than implying a search happened."""


class SearchedSummary(Frozen):
    """What was looked for, so a reader can judge the abstention (§5.5 check 4)."""

    facets: dict[str, list[str]] = Field(default_factory=dict)
    queries: list[str] = Field(default_factory=list)
    registry_snapshot: RegistrySnapshotRef | None = None
    candidates_retrieved: int = 0
    candidates_surviving_checks: int = 0
    highest_score: float | None = None
    confidence_floor: float | None = None


class NothingFound(Frozen):
    """An abstention. An equal output to a recommendation, not an error (R3.6)."""

    kind: RecommendationKind
    reason: NothingFoundReason
    searched: SearchedSummary
    statement: str
    """Plain prose for the researcher: what we looked for and why nothing qualified."""
    referral: str
    """Who to talk to instead. §5.5: R3 declining is a decline *with a referral*."""


class RecommendationsDocument(Frozen):
    """§6.2. The only thing that leaves the system."""

    run_id: str
    profile_id: str

    requires_human_review: Literal[True] = True
    """Always present, cannot be set false, cannot be reassigned (the model is frozen). C15's
    mandatory human review is therefore a property of the output format."""

    generated_at: str
    registry_snapshot: RegistrySnapshotRef
    agent: AgentRef
    ranking_config: RankingConfigRef
    prompts: list[PromptRef] = Field(default_factory=list)
    """Which prompts, at which versions, influenced this document (§5.4)."""

    recommendations: list[Recommendation] = Field(default_factory=list)
    nothing_found: list[NothingFound] = Field(default_factory=list)
    """Sibling of `recommendations`, deliberately. See the module docstring."""

    provenance: str
    """Relative path to this run's PROV-O graph (§6.3)."""
