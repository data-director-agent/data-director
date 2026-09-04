"""Stage 5 — check (§5.5). This is where C15 is met.

§3 marks C15 as one of two controls that cannot be added later — "this is the architecture, not
a setting" — so the mechanical checks are implemented at v0.1 rather than stubbed, even though
nothing yet reaches them on a real run. They are also the cheapest part of the pipeline to write
and the most expensive to retrofit, because retrofitting them means auditing every path that
already produced output.

Four checks, in order. The first two are mechanical and non-negotiable:

1. **Grounding (must pass).** Every recommendation must carry a registry identifier that was in
   the candidate set the retriever actually returned. Anything failing is *dropped and logged as
   a bug*, not shown with a warning. Target zero; anything above zero is a defect report against
   the pipeline, and `counts["grounding_failed"]` in the run record is where it shows up.

   This is the whole reason §5.6 can let the model direct retrieval and weigh in on ranking
   without risking a fabricated standard reaching a reader: the check asks only "is this
   identifier in the set a real query returned?", which is a question about provenance, not
   about who ranked it highest.

2. **Evidence (must pass).** Every factual statement in a reason must be backed by an evidence
   entry naming a registry record and field, and those references must resolve. A mechanical
   check on the references — deliberately not an attempt to understand the prose, because a
   check that tried would itself need review.

3. **Confidence floor (configurable).** From the versioned weights file, so a change to it is
   recorded with the run.

4. **Coverage.** Handled in `assemble`, which iterates `RecommendationKind` and writes a
   `NothingFound` for every kind with no survivor. It lives there because it needs the whole
   picture, and because putting it anywhere else would let a kind be quietly omitted.

`checks_enabled` is not a setting. §4.3 says this stage "must not be switched off in
configuration", and the absence of a flag is how that is enforced.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from standards_advisor.models.candidates import (
    CandidateSet,
    CheckFinding,
    CheckOutcome,
    Explanation,
    RankedCandidateSet,
)
from standards_advisor.models.common import StageName, StageStatus
from standards_advisor.nodes.support import merge, stage

if TYPE_CHECKING:
    from langgraph.runtime import Runtime

    from standards_advisor.context import RunContext
    from standards_advisor.state import PipelineState


def check_node(state: PipelineState, runtime: Runtime[RunContext]) -> dict[str, Any]:
    ctx = runtime.context
    explanations = state.get("explanations") or []
    candidate_set = state.get("candidates")
    ranked_set = state.get("ranked")
    floor = ctx.ranking.confidence_floor

    with stage(ctx, StageName.CHECK) as run:
        findings: list[CheckFinding] = []

        grounded, grounding_findings = check_grounding(explanations, candidate_set)
        findings.extend(grounding_findings)

        evidenced, evidence_findings = check_evidence(grounded, candidate_set)
        findings.extend(evidence_findings)

        passed, floor_findings = check_confidence_floor(evidenced, floor)
        findings.extend(floor_findings)

        for finding in grounding_findings:
            # A grounding failure is a defect in the pipeline, not a property of the dataset,
            # so it is recorded as a failure as well as a finding.
            run.fail("grounding_failed", finding.detail)
            ctx.events.note("grounding_failed", finding.detail, registry_id=finding.registry_id)

        outcome = CheckOutcome(
            passed=passed,
            findings=findings,
            confidence_floor=floor,
            highest_score_by_kind=_highest_scores(ranked_set),
        )
        run.payload = outcome
        run.counts = {
            "explanations_in": len(explanations),
            "grounding_failed": len(grounding_findings),
            "evidence_removed": len(evidence_findings),
            "below_floor": len(floor_findings),
            "passed": len(passed),
        }
        if not passed:
            run.status = StageStatus.EMPTY

    return merge(run, checked=run.payload)


def check_grounding(
    explanations: list[Explanation], candidate_set: CandidateSet | None
) -> tuple[list[Explanation], list[CheckFinding]]:
    """Check 1. Drop anything whose identifier was not in the candidate set."""
    grounding_set = candidate_set.registry_ids() if candidate_set else frozenset()
    kept: list[Explanation] = []
    findings: list[CheckFinding] = []
    for explanation in explanations:
        if explanation.registry_id in grounding_set:
            kept.append(explanation)
            continue
        findings.append(
            CheckFinding(
                check="grounding",
                outcome="dropped",
                registry_id=explanation.registry_id,
                detail=(
                    f"{explanation.registry_id!r} is not in the candidate set returned by any "
                    "registry query; dropped as a defect, not shown with a warning"
                ),
            )
        )
    return kept, findings


def check_evidence(
    explanations: list[Explanation], candidate_set: CandidateSet | None
) -> tuple[list[Explanation], list[CheckFinding]]:
    """Check 2. Remove evidence entries whose references do not resolve.

    "Resolve" means: the named record is in the candidate set, and the named field was actually
    supplied by the route that fetched it. The second half matters — citing a field the route
    never provided is exactly the kind of unbacked claim this check exists to catch, and §7.2's
    `populated_fields` is what makes it decidable.

    An explanation left with no evidence at all is kept but flagged, not dropped. §5.5 says
    unbacked *statements* are removed and the removal logged; whether a reason with no citations
    survives the confidence floor is then the floor's business, not this check's.
    """
    if candidate_set is None:
        return explanations, [
            CheckFinding(
                check="evidence",
                outcome="skipped",
                detail="no candidate set, so no evidence reference could be resolved",
            )
        ]

    fields_by_record = {
        candidate.resource.registry_id: set(candidate.populated_fields) | set(candidate.record)
        for candidate in candidate_set.candidates
    }

    kept: list[Explanation] = []
    findings: list[CheckFinding] = []
    for explanation in explanations:
        surviving = []
        for entry in explanation.evidence:
            available = fields_by_record.get(entry.record)
            if available is None:
                findings.append(
                    CheckFinding(
                        check="evidence",
                        outcome="removed",
                        registry_id=explanation.registry_id,
                        detail=(
                            f"evidence cites record {entry.record!r}, which is not in the "
                            "candidate set"
                        ),
                    )
                )
                continue
            if entry.field not in available:
                findings.append(
                    CheckFinding(
                        check="evidence",
                        outcome="removed",
                        registry_id=explanation.registry_id,
                        detail=(
                            f"evidence cites field {entry.field!r} of {entry.record!r}, which "
                            "this registry route did not supply"
                        ),
                    )
                )
                continue
            surviving.append(entry)

        if not surviving and explanation.evidence:
            findings.append(
                CheckFinding(
                    check="evidence",
                    outcome="flagged",
                    registry_id=explanation.registry_id,
                    detail="every evidence reference was removed; the reason is now unbacked",
                )
            )
        kept.append(explanation.model_copy(update={"evidence": surviving}))

    return kept, findings


def check_confidence_floor(
    explanations: list[Explanation], floor: float
) -> tuple[list[Explanation], list[CheckFinding]]:
    """Check 3. Keep only candidates at or above the configured floor."""
    kept: list[Explanation] = []
    findings: list[CheckFinding] = []
    for explanation in explanations:
        if explanation.confidence >= floor:
            kept.append(explanation)
            continue
        findings.append(
            CheckFinding(
                check="confidence_floor",
                outcome="excluded",
                registry_id=explanation.registry_id,
                detail=f"confidence {explanation.confidence:.2f} is below the floor {floor:.2f}",
            )
        )
    return kept, findings


def _highest_scores(ranked_set: RankedCandidateSet | None) -> dict[str, float]:
    """The best score per kind, for a `NothingFound` to report how close it came."""
    if ranked_set is None:
        return {}
    best: dict[str, float] = {}
    for item in ranked_set.ranked:
        kind = item.candidate.kind.value
        best[kind] = max(best.get(kind, 0.0), item.score)
    return best
