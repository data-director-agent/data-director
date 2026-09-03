"""The §5.5 checks — where C15 is met.

The grounding check is the load-bearing one. §5.6 lets the model direct retrieval and weigh in
on ranking, and the reason that is safe is entirely this check: it asks only whether an
identifier came back from a real query, which is a question about provenance rather than about
who ranked it highest. A fabricated standard cannot pass it however it got into the output.
"""

from __future__ import annotations

from standards_advisor.models.candidates import (
    Candidate,
    CandidateSet,
    Explanation,
    RegistryQuery,
)
from standards_advisor.models.common import RecommendationKind, RegistrySnapshotRef
from standards_advisor.models.recommendations import (
    Evidence,
    ResourceRef,
    Target,
    TargetKind,
)
from standards_advisor.nodes.check import (
    check_confidence_floor,
    check_evidence,
    check_grounding,
)

KIND = RecommendationKind.CONTROLLED_VOCABULARY_LINKAGE
SNAPSHOT = RegistrySnapshotRef(version="2026-09-01", source="fake", stale=False)


def _candidate_set(*, registry_id: str = "FAIRsharing.aaa") -> CandidateSet:
    query = RegistryQuery(kind=KIND, record_types=["terminology_artefact"])
    candidate = Candidate(
        kind=KIND,
        resource=ResourceRef(name="A Vocabulary", registry_id=registry_id, status="ready"),
        query=query,
        snapshot=SNAPSHOT,
        populated_fields=["recommended_by", "licence"],
        record={"recommended_by": "40 data policies", "licence": "CC-BY-4.0"},
    )
    return CandidateSet(queries=[query], candidates=[candidate], snapshot=SNAPSHOT)


def _explanation(
    registry_id: str,
    *,
    confidence: float = 0.9,
    evidence: list[Evidence] | None = None,
) -> Explanation:
    return Explanation(
        registry_id=registry_id,
        kind=KIND,
        target=Target(kind=TargetKind.FIELD_VALUES, field="soil_horizon"),
        reason="Because it covers these values.",
        evidence=evidence if evidence is not None else [],
        confidence=confidence,
    )


# -- check 1: grounding -----------------------------------------------------------------------


def test_a_grounded_recommendation_survives():
    kept, findings = check_grounding([_explanation("FAIRsharing.aaa")], _candidate_set())
    assert len(kept) == 1
    assert findings == []


def test_an_invented_standard_is_dropped_not_warned_about():
    """§5.5: dropped and logged as a bug, not shown with a warning. Target zero."""
    kept, findings = check_grounding([_explanation("FAIRsharing.invented")], _candidate_set())
    assert kept == []
    assert len(findings) == 1
    assert findings[0].check == "grounding"
    assert findings[0].outcome == "dropped"
    assert "not in the candidate set" in findings[0].detail


def test_grounding_fails_everything_when_there_is_no_candidate_set():
    kept, findings = check_grounding([_explanation("FAIRsharing.aaa")], None)
    assert kept == []
    assert len(findings) == 1


# -- check 2: evidence ------------------------------------------------------------------------


def test_evidence_naming_a_supplied_field_survives():
    explanation = _explanation(
        "FAIRsharing.aaa",
        evidence=[
            Evidence(
                statement="Recommended by 40 data policies",
                record="FAIRsharing.aaa",
                field="recommended_by",
            )
        ],
    )
    kept, findings = check_evidence([explanation], _candidate_set())
    assert len(kept[0].evidence) == 1
    assert findings == []


def test_evidence_citing_a_field_the_route_never_supplied_is_removed():
    """§7.2's `populated_fields` is what makes this decidable.

    Citing a field the route did not provide is precisely the unbacked claim this check exists
    to catch — and without recording what each route supplies, it would be indistinguishable
    from a field that happened to be empty.
    """
    explanation = _explanation(
        "FAIRsharing.aaa",
        evidence=[
            Evidence(
                statement="It has 900 adopters",
                record="FAIRsharing.aaa",
                field="adopter_count",
            )
        ],
    )
    kept, findings = check_evidence([explanation], _candidate_set())
    assert kept[0].evidence == []
    assert any("did not supply" in finding.detail for finding in findings)


def test_evidence_citing_a_record_outside_the_candidate_set_is_removed():
    explanation = _explanation(
        "FAIRsharing.aaa",
        evidence=[Evidence(statement="Related to X", record="FAIRsharing.zzz", field="name")],
    )
    kept, findings = check_evidence([explanation], _candidate_set())
    assert kept[0].evidence == []
    assert any("not in the candidate set" in finding.detail for finding in findings)


def test_losing_every_citation_is_flagged_but_the_reason_is_kept():
    """§5.5 removes unbacked *statements* and logs the removal.

    Whether a reason with no citations left should reach a reader is then the confidence floor's
    business, not this check's — so it is flagged here rather than dropped.
    """
    explanation = _explanation(
        "FAIRsharing.aaa",
        evidence=[Evidence(statement="Invented", record="FAIRsharing.zzz", field="name")],
    )
    kept, findings = check_evidence([explanation], _candidate_set())
    assert len(kept) == 1
    assert any(finding.outcome == "flagged" for finding in findings)


# -- check 3: confidence floor ----------------------------------------------------------------


def test_the_confidence_floor_excludes_a_weak_candidate():
    kept, findings = check_confidence_floor([_explanation("a", confidence=0.31)], 0.55)
    assert kept == []
    assert findings[0].check == "confidence_floor"
    assert "below the floor" in findings[0].detail


def test_a_candidate_exactly_at_the_floor_is_kept():
    kept, _ = check_confidence_floor([_explanation("a", confidence=0.55)], 0.55)
    assert len(kept) == 1
