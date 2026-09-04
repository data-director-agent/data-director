"""The two §6.2 properties that are enforced by the type rather than by convention.

Both are C15 obligations, and §3 marks C15 as one of the two controls that cannot be added
later — "this is the architecture, not a setting". These tests are what stop that claim quietly
becoming false.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from standards_advisor.models.common import (
    AgentRef,
    RankingConfigRef,
    RecommendationKind,
    RegistrySnapshotRef,
)
from standards_advisor.models.recommendations import (
    NothingFound,
    NothingFoundReason,
    RecommendationsDocument,
    SearchedSummary,
)
from standards_advisor.schema_export import render


def _document(**overrides) -> RecommendationsDocument:
    payload = {
        "run_id": "r1",
        "profile_id": "p1",
        "generated_at": "2026-09-03T10:04:12+00:00",
        "registry_snapshot": RegistrySnapshotRef(version="2026-09-01", source="fake", stale=False),
        "agent": AgentRef(identity="urn:dd:agent:test", version="0.1.0"),
        "ranking_config": RankingConfigRef(version="ranking.v1", sha256="abc"),
        "provenance": "runs/r1/prov.jsonld",
    }
    payload.update(overrides)
    return RecommendationsDocument(**payload)


def test_requires_human_review_is_true_by_default():
    assert _document().requires_human_review is True


def test_requires_human_review_cannot_be_set_false():
    """C15's mandatory review is met by the output format, not by the interface author."""
    with pytest.raises(ValidationError):
        _document(requires_human_review=False)


def test_requires_human_review_cannot_be_reassigned():
    document = _document()
    with pytest.raises(ValidationError):
        document.requires_human_review = False  # type: ignore[assignment,misc]


def test_the_published_schema_pins_it_as_a_constant():
    """A consumer in another language must not be able to produce a document claiming otherwise."""
    schema = render(RecommendationsDocument)
    assert '"const": true' in schema


def test_nothing_found_is_a_sibling_of_recommendations_not_nested_in_it():
    """So a viewer cannot render the recommendations while ignoring the abstentions (§6.2)."""
    fields = RecommendationsDocument.model_fields
    assert "nothing_found" in fields
    assert "recommendations" in fields

    recommendation_schema = render(RecommendationsDocument)
    # `nothing_found` must not appear as a property of a Recommendation.
    assert '"nothing_found"' in recommendation_schema


def test_unknown_fields_are_rejected():
    """`extra="forbid"` — silently swallowing a misspelled field is how a schema stops meaning
    anything, and this document is the published contract of §6."""
    with pytest.raises(ValidationError):
        _document(recomendations=[])  # deliberate misspelling


def test_the_document_is_immutable():
    document = _document()
    with pytest.raises(ValidationError):
        document.run_id = "r2"  # type: ignore[misc]


def test_all_four_kinds_exist_and_separate_linkage_from_alignment():
    """R3's required distinction lives in the type system, not in a free-text field."""
    kinds = set(RecommendationKind)
    assert RecommendationKind.CONTROLLED_VOCABULARY_LINKAGE in kinds
    assert RecommendationKind.ONTOLOGY_ALIGNMENT in kinds
    assert len(kinds) == 4
    # Distinct members, so the two kinds R3 must tell apart cannot be conflated by accident.
    assert (
        len(
            {
                RecommendationKind.CONTROLLED_VOCABULARY_LINKAGE.value,
                RecommendationKind.ONTOLOGY_ALIGNMENT.value,
            }
        )
        == 2
    )


def test_an_abstention_must_carry_a_statement_and_a_referral():
    """§5.5: R3 declining is a decline *with a referral* — it says why, and points to a person."""
    with pytest.raises(ValidationError):
        NothingFound(  # type: ignore[call-arg]  # the missing referral is the point
            kind=RecommendationKind.ONTOLOGY_ALIGNMENT,
            reason=NothingFoundReason.NO_QUALIFYING_RESOURCE,
            searched=SearchedSummary(),
            statement="nothing suitable",
        )
