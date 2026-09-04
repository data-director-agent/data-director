"""Stage 3 — rank (§5.3). The scoring loop is real; every rule body is a stub.

§5.3's default is explicit scoring with readable rules rather than an unexamined judgement by
the model, because readable rules are what let a test harness sweep weight combinations against
fixtures and attribute a bad ranking to a specific rule. The loop that makes each rule's
contribution a *recorded, attributed* part of the score is implemented here; the rules
themselves are not, because they read registry fields no v0.1 route supplies
(`ranking/rules.py`).

The one behaviour worth having correct from the start is the difference between a rule that
scored zero and a rule that was **skipped**. §7.2 requires the latter where a route did not
supply the rule's inputs; a zero is a statement about the candidate, a skip is a statement about
the data, and conflating them makes rankings vary by route for no visible reason.

§5.6 permits the model to contribute a signal here — flagging a candidate as off-topic despite a
subject match, or proposing a weight adjustment. When that arrives it becomes another
`ScoreComponent` with `source="model"`, recorded and attributed like any other, not folded
invisibly into a rule's output. `ScoreComponent.source` already reserves the space.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from standards_advisor.models.candidates import (
    Candidate,
    RankedCandidate,
    RankedCandidateSet,
)
from standards_advisor.models.common import ScoreComponent, StageName, StageStatus
from standards_advisor.models.profile import DatasetProfile
from standards_advisor.nodes.support import merge, stage
from standards_advisor.ranking import KIND_SPECIFIC_RULES, RULES
from standards_advisor.ranking.weights import RankingConfig
from standards_advisor.registry.base import RegistryRecord

if TYPE_CHECKING:
    from langgraph.runtime import Runtime

    from standards_advisor.context import RunContext
    from standards_advisor.state import PipelineState


def rank_node(state: PipelineState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    ctx = runtime.context
    profile = state.get("profile")
    candidate_set = state.get("candidates")

    with stage(ctx, StageName.RANK) as run:
        ranked: list[RankedCandidate] = []
        if profile is not None and candidate_set is not None:
            for candidate in candidate_set.candidates:
                ranked.append(score_candidate(profile, candidate, ctx.ranking))
            ranked.sort(key=lambda item: item.score, reverse=True)

        run.payload = RankedCandidateSet(ranked=ranked)
        run.counts = {"ranked": len(ranked)}
        if not ranked:
            run.status = StageStatus.EMPTY
        if all(not item.components for item in ranked) and ranked:
            # Every rule skipped for every candidate: a real condition worth flagging rather
            # than a silent list of zero-scored candidates.
            run.status = StageStatus.NOT_IMPLEMENTED
            run.note("no ranking rule produced a score; every rule was skipped (§5.3 stubs)")

    return merge(run, ranked=run.payload)


def score_candidate(
    profile: DatasetProfile, candidate: Candidate, config: RankingConfig
) -> RankedCandidate:
    """Score one candidate, recording each rule's contribution or its absence."""
    record = _record_from_candidate(candidate)
    components: list[ScoreComponent] = []
    skipped: list[str] = []
    total = 0.0

    for name, rule in RULES.items():
        applies_to = KIND_SPECIFIC_RULES.get(name)
        if applies_to is not None and candidate.kind.value not in applies_to:
            skipped.append(name)
            continue

        raw = rule(profile, record)
        if raw is None:
            # Skipped, not zero. See the module docstring and §7.2.
            skipped.append(name)
            continue

        weight = config.weight(name)
        contribution = raw * weight
        total += contribution
        components.append(
            ScoreComponent(
                name=name,
                source="rule",
                raw=raw,
                weight=weight,
                contribution=contribution,
            )
        )

    # Normalise the weighted rule contributions to 0..1 first, then apply penalties. Penalising
    # before normalising would scale the penalty by however many rules happened to run, which
    # would make the same deprecated record cost a different amount on different routes.
    divisor = sum(component.weight for component in components)
    score = (total / divisor) if divisor > 0 else 0.0

    penalty = _deprecation_penalty(candidate, config)
    if penalty is not None:
        score += penalty.contribution  # negative by construction
        components.append(penalty)

    return RankedCandidate(
        candidate=candidate,
        score=max(0.0, min(1.0, score)),
        components=components,
        skipped_rules=skipped,
    )


def _deprecation_penalty(candidate: Candidate, config: RankingConfig) -> ScoreComponent | None:
    """A heavy penalty and a flag saying why (§5.3).

    Applied as its own attributed component rather than folded into `maturity`, so that the
    reason survives into the output document. §5.2 is explicit that a deprecated standard is
    retrieved and shown rather than hidden, precisely so this warning can be given.
    """
    if candidate.resource.status != "deprecated":
        return None
    magnitude = config.penalties.get("deprecated", 0.0)
    return ScoreComponent(
        name="deprecated_penalty",
        source="rule",
        raw=1.0,
        weight=0.0,
        contribution=-magnitude,
        note="the registry marks this resource deprecated; shown as a warning, not a suggestion",
    )


def _record_from_candidate(candidate: Candidate) -> RegistryRecord:
    """Rebuild the record view a rule expects from what the candidate carried forward."""
    return RegistryRecord(
        registry_id=candidate.resource.registry_id,
        name=candidate.resource.name,
        doi=candidate.resource.doi,
        url=candidate.resource.url,
        record_type=candidate.resource.record_type,
        record_subtype=candidate.resource.record_subtype,
        status=candidate.resource.status,
        fields=dict(candidate.record),
        populated_fields=frozenset(candidate.populated_fields),
    )
