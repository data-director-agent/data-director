"""Stage 6 — assemble. The only place a `RecommendationsDocument` is constructed.

It is also where §5.5's coverage check lives, and the mechanism is worth stating plainly because
it is what makes R3.6 hold:

    for kind in RecommendationKind:
        if nothing survived for this kind:
            write a NothingFound

Nothing else in the codebase constructs a `NothingFound`. So a fifth kind of recommendation
cannot be added without its abstention path appearing automatically, and no kind can be quietly
omitted — the loop is over the enum, not over whatever happened to be produced.

§5.5's requirement for what an abstention must say is met by `_statement` and `_referral`: what
we looked for, what we searched, why nothing qualified, and what the researcher should do
instead. "R3 declining is a decline with a referral — it says why, and points to a person who
can help."
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from standards_advisor.ids import utc_now
from standards_advisor.models.candidates import (
    CandidateSet,
    CheckOutcome,
    Explanation,
    RankedCandidateSet,
)
from standards_advisor.models.common import RecommendationKind, StageName
from standards_advisor.models.recommendations import (
    NothingFound,
    NothingFoundReason,
    Recommendation,
    RecommendationsDocument,
    SearchedSummary,
)
from standards_advisor.nodes.support import merge, stage

if TYPE_CHECKING:
    from langgraph.runtime import Runtime

    from standards_advisor.context import RunContext
    from standards_advisor.state import PipelineState

#: Who to send a researcher to when we have nothing useful to say. Deliberately a person, not a
#: link: §5.5's referral is to someone who can help, and for this university that is the
#: subject specialist or the Library's research data management team.
REFERRALS: dict[RecommendationKind, str] = {
    RecommendationKind.CONTROLLED_VOCABULARY_LINKAGE: (
        "Talk to a data specialist in your field, or the Library RDM team, before choosing a "
        "vocabulary to code these values against. If none exists for your field, that is worth "
        "recording in your data management plan — and worth considering registering one."
    ),
    RecommendationKind.ONTOLOGY_ALIGNMENT: (
        "Talk to a data specialist in this field, or the Library RDM team, before choosing an "
        "ontology to match your dataset's structure to."
    ),
    RecommendationKind.OPEN_FORMAT: (
        "The Library RDM team can advise on open formats for long-term preservation of this "
        "kind of data."
    ),
    RecommendationKind.FIELD_LEVEL_STANDARD: (
        "For how to write dates, coordinates, units and codes, the Library RDM team can point "
        "you at the conventions used in your discipline."
    ),
}

KIND_DESCRIPTIONS: dict[RecommendationKind, str] = {
    RecommendationKind.CONTROLLED_VOCABULARY_LINKAGE: (
        "a controlled vocabulary to link this dataset's values to agreed concept identifiers"
    ),
    RecommendationKind.ONTOLOGY_ALIGNMENT: (
        "an ontology to align this dataset's variables and structure to"
    ),
    RecommendationKind.OPEN_FORMAT: "an open format for these files",
    RecommendationKind.FIELD_LEVEL_STANDARD: (
        "a standard for how individual values are written — dates, coordinates, units, codes"
    ),
}


def assemble_node(state: PipelineState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    ctx = runtime.context
    profile = state.get("profile")
    candidate_set = state.get("candidates")
    ranked_set = state.get("ranked")
    checked = state.get("checked")
    reports = state.get("stage_reports") or []

    with stage(ctx, StageName.ASSEMBLE) as run:
        passed = checked.passed if checked else []
        recommendations = [_to_recommendation(explanation, ranked_set) for explanation in passed]

        nothing_found = [
            _nothing_found(kind, candidate_set, checked, recommendations)
            for kind in RecommendationKind
            if not any(item.kind == kind for item in recommendations)
        ]

        prompts = [ref for report in reports for ref in report.prompts]

        document = RecommendationsDocument(
            run_id=state["run_id"],
            profile_id=profile.profile_id if profile else "unknown",
            generated_at=utc_now().isoformat(),
            registry_snapshot=(
                candidate_set.snapshot if candidate_set else ctx.registry.snapshot()
            ),
            agent=ctx.agent,
            ranking_config=ctx.ranking.ref(),
            prompts=prompts,
            recommendations=recommendations,
            nothing_found=nothing_found,
            provenance=ctx.run_dir.provenance_relpath(),
        )

        run.payload = document
        run.counts = {
            "recommendations": len(recommendations),
            "nothing_found": len(nothing_found),
        }
        ctx.run_dir.write_json("recommendations", document.model_dump(mode="json"))

    return merge(run, document=run.payload)


def _to_recommendation(
    explanation: Explanation, ranked_set: RankedCandidateSet | None
) -> Recommendation:
    """Pair a checked explanation with the ranking that produced it."""
    ranked = None
    if ranked_set is not None:
        ranked = next(
            (
                item
                for item in ranked_set.ranked
                if item.candidate.resource.registry_id == explanation.registry_id
            ),
            None,
        )
    if ranked is None:  # pragma: no cover — grounding would have dropped it first
        raise RuntimeError(
            f"{explanation.registry_id!r} passed the checks but is not in the ranked set; "
            "this is a pipeline defect, not a content outcome"
        )

    return Recommendation(
        kind=explanation.kind,
        resource=ranked.candidate.resource,
        target=explanation.target,
        score=ranked.score,
        score_features=ranked.features,
        score_components=list(ranked.components),
        confidence=explanation.confidence,
        reason=explanation.reason,
        evidence=list(explanation.evidence),
        caveats=list(explanation.caveats),
        queries=[ranked.candidate.query.describe()],
    )


def _nothing_found(
    kind: RecommendationKind,
    candidate_set: CandidateSet | None,
    checked: CheckOutcome | None,
    recommendations: list[Recommendation],
) -> NothingFound:
    """Say plainly that nothing qualified, and why (§5.5 check 4)."""
    queries = (
        [query for query in candidate_set.queries if query.kind == kind] if candidate_set else []
    )
    retrieved = len(candidate_set.for_kind(kind)) if candidate_set else 0
    unavailable = bool(candidate_set and kind in candidate_set.unavailable_kinds)
    highest = (checked.highest_score_by_kind.get(kind.value) if checked else None) or None

    if unavailable or candidate_set is None:
        reason = NothingFoundReason.REGISTRY_UNAVAILABLE
    elif not queries:
        reason = NothingFoundReason.STAGE_NOT_IMPLEMENTED
    elif retrieved == 0:
        reason = NothingFoundReason.NO_CANDIDATES_RETRIEVED
    else:
        reason = NothingFoundReason.NO_QUALIFYING_RESOURCE

    facets: dict[str, list[str]] = {}
    for query in queries:
        for facet, values in query.facets.items():
            if values:
                facets.setdefault(facet, [])
                facets[facet].extend(value for value in values if value not in facets[facet])

    return NothingFound(
        kind=kind,
        reason=reason,
        searched=SearchedSummary(
            facets=facets,
            queries=[query.describe() for query in queries],
            registry_snapshot=candidate_set.snapshot if candidate_set else None,
            candidates_retrieved=retrieved,
            candidates_surviving_checks=0,
            highest_score=highest,
            confidence_floor=checked.confidence_floor if checked else None,
        ),
        statement=_statement(kind, reason, retrieved),
        referral=REFERRALS[kind],
    )


def _statement(kind: RecommendationKind, reason: NothingFoundReason, retrieved: int) -> str:
    """Prose a researcher can act on. Not an error message."""
    looked_for = KIND_DESCRIPTIONS[kind]
    if reason is NothingFoundReason.REGISTRY_UNAVAILABLE:
        return (
            f"We looked for {looked_for}, but no standards registry was available to this run, "
            "so no search actually ran. This is a limitation of the tool as configured, not a "
            "finding about your dataset."
        )
    if reason is NothingFoundReason.STAGE_NOT_IMPLEMENTED:
        return (
            f"We did not search for {looked_for}: that part of the tool is not implemented yet. "
            "This says nothing about your dataset."
        )
    if reason is NothingFoundReason.NO_CANDIDATES_RETRIEVED:
        return (
            f"We searched the registry for {looked_for} and found no registered resource that "
            "covers this dataset's subject area. Anything we suggested here would be generic "
            "rather than suited to your field, so we are not suggesting anything."
        )
    return (
        f"We looked for {looked_for} and considered {retrieved} registered resource(s), but "
        "none covers this dataset well enough to recommend. A weak suggestion here would be "
        "worse than none."
    )
