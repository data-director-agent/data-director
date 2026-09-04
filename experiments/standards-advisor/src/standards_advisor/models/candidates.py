"""Internal stage payloads.

These are not published: they are not exported to `schemas/` and no consumer outside the
pipeline reads them. They still get the same immutability and strictness as the §6 documents,
because they cross node boundaries and end up in checkpoints.
"""

from __future__ import annotations

from pydantic import Field

from standards_advisor.models.common import (
    Frozen,
    RecommendationKind,
    RegistrySnapshotRef,
    ScoreComponent,
)
from standards_advisor.models.recommendations import Evidence, ResourceRef, Target


class RegistryQuery(Frozen):
    """One registry search. §5.2 runs four of these, one per kind of recommendation.

    A query is a first-class recorded object rather than a string built inline, for two
    reasons: `NothingFound.searched.facets` is populated from it, so an abstention can state
    what was actually looked for; and §5.2 requires every candidate to remember which query
    found it.
    """

    kind: RecommendationKind
    record_types: list[str] = Field(default_factory=list)
    exclude_subtypes: list[str] = Field(default_factory=list)
    """How R3.1 excludes ontologies from a vocabulary search, and R3.2 keeps only them."""
    include_subtypes: list[str] = Field(default_factory=list)
    facets: dict[str, list[str]] = Field(default_factory=dict)
    free_text: str | None = None
    targets: list[Target] = Field(default_factory=list)
    """Which columns or parts of the structure this query is on behalf of."""
    origin: str = "fixed"
    """`fixed` for one of §5.2's four, `model_proposed` once §5.6's model-directed retrieval
    exists. Recorded so the two can be told apart in a run record."""

    def describe(self) -> str:
        """A short human-readable form, for `SearchedSummary.queries`."""
        parts = [f"kind={self.kind}"]
        if self.record_types:
            parts.append(f"record_types={','.join(self.record_types)}")
        if self.include_subtypes:
            parts.append(f"include_subtypes={','.join(self.include_subtypes)}")
        if self.exclude_subtypes:
            parts.append(f"exclude_subtypes={','.join(self.exclude_subtypes)}")
        for facet, values in sorted(self.facets.items()):
            if values:
                parts.append(f"{facet}={','.join(values)}")
        if self.free_text:
            parts.append(f"text={self.free_text!r}")
        parts.append(f"origin={self.origin}")
        return " ".join(parts)


class Candidate(Frozen):
    """A registry record that an actual query returned.

    The grounding check (§5.5) asks exactly one question of a recommendation: is its
    `registry_id` in the candidate set? That is a question about provenance, not about who
    ranked it — which is why the model is free to direct retrieval and weigh in on ranking
    (§5.6) without being able to make a fabricated standard pass.
    """

    kind: RecommendationKind
    resource: ResourceRef
    query: RegistryQuery
    snapshot: RegistrySnapshotRef
    populated_fields: list[str] = Field(default_factory=list)
    """Which record fields this route actually supplied (§7.2). A rule whose inputs are absent
    is *skipped*, not scored zero — treating "this route does not supply that field" as "the
    field is empty" produces rankings that vary by route for no visible reason."""
    record: dict[str, str] = Field(default_factory=dict)
    """The record's scalar fields, flattened. The evidence check resolves against this."""
    targets: list[Target] = Field(default_factory=list)


class CandidateSet(Frozen):
    queries: list[RegistryQuery] = Field(default_factory=list)
    candidates: list[Candidate] = Field(default_factory=list)
    snapshot: RegistrySnapshotRef
    unavailable_kinds: list[RecommendationKind] = Field(default_factory=list)
    """Kinds whose search could not run at all, as opposed to running and finding nothing.
    Drives the distinction between `REGISTRY_UNAVAILABLE` and `NO_CANDIDATES_RETRIEVED`."""

    def for_kind(self, kind: RecommendationKind) -> list[Candidate]:
        return [c for c in self.candidates if c.kind == kind]

    def registry_ids(self) -> frozenset[str]:
        """The grounding set."""
        return frozenset(c.resource.registry_id for c in self.candidates)


class RankedCandidate(Frozen):
    candidate: Candidate
    score: float
    components: list[ScoreComponent] = Field(default_factory=list)
    skipped_rules: list[str] = Field(default_factory=list)
    """Rules whose inputs were missing. Recorded, because a skipped rule and a rule that
    scored zero mean different things and only one of them is a signal about the candidate."""

    @property
    def features(self) -> dict[str, float]:
        return {component.name: component.raw for component in self.components}


class RankedCandidateSet(Frozen):
    ranked: list[RankedCandidate] = Field(default_factory=list)

    def for_kind(self, kind: RecommendationKind) -> list[RankedCandidate]:
        return [r for r in self.ranked if r.candidate.kind == kind]


class Explanation(Frozen):
    """What the explain stage produced for one candidate, before any check has run."""

    registry_id: str
    kind: RecommendationKind
    target: Target
    reason: str
    caveats: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: float


class CheckFinding(Frozen):
    """One thing a check did, and to what.

    Every drop and every removal is recorded. §5.5 requires a grounding failure be "logged as a
    bug, not shown with a warning" — the logging is this, and a non-zero count of
    `grounding_failed` in a run is a defect report against the pipeline.
    """

    check: str
    outcome: str
    registry_id: str | None = None
    detail: str


class CheckOutcome(Frozen):
    passed: list[Explanation] = Field(default_factory=list)
    findings: list[CheckFinding] = Field(default_factory=list)
    confidence_floor: float
    highest_score_by_kind: dict[str, float] = Field(default_factory=dict)
