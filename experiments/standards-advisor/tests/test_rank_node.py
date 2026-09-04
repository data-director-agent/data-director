"""The ranking loop (§5.3). The rule bodies are stubs; the scoring contract is not.

The behaviour worth pinning down now is the difference between a rule that scored zero and a
rule that was **skipped**. §7.2 requires the latter wherever a route did not supply the rule's
inputs, and the reason is concrete: a zero is a statement about the candidate, a skip is a
statement about the data, and conflating them makes the same record rank differently depending
on which route fetched it, for no visible reason.

Also covered: deprecation is a penalty carrying its own reason, because §5.2 retrieves
deprecated records deliberately so they can be shown as a warning rather than hidden.
"""

from __future__ import annotations

import pytest

from standards_advisor.models.candidates import Candidate, RegistryQuery
from standards_advisor.models.common import RecommendationKind, RegistrySnapshotRef
from standards_advisor.models.profile import DatasetProfile
from standards_advisor.models.recommendations import ResourceRef
from standards_advisor.nodes.rank import score_candidate
from standards_advisor.ranking import RULES
from standards_advisor.ranking.weights import RankingConfig

SNAPSHOT = RegistrySnapshotRef(version="2026-09-01", source="fake", stale=False)
CONFIG = RankingConfig(
    version="ranking.test",
    confidence_floor=0.55,
    weights=dict.fromkeys(RULES, 1.0),
    penalties={"deprecated": 0.6},
    sha256="0" * 64,
)


def _profile() -> DatasetProfile:
    from standards_advisor.models.profile import ContentFingerprint, SourceRef

    return DatasetProfile(
        profile_id="p1",
        fingerprint=ContentFingerprint(digest="a", total_bytes=1, files_hashed=1),
        source=SourceRef(kind="local_files"),
        profiled_at="2026-09-03T00:00:00+00:00",
        profiler_version="0.1.0",
    )


def _candidate(*, status: str = "ready", kind: RecommendationKind | None = None) -> Candidate:
    resolved = kind or RecommendationKind.CONTROLLED_VOCABULARY_LINKAGE
    return Candidate(
        kind=resolved,
        resource=ResourceRef(name="A Vocabulary", registry_id="FAIRsharing.aaa", status=status),
        query=RegistryQuery(kind=resolved),
        snapshot=SNAPSHOT,
        populated_fields=[],
        record={},
    )


def test_a_rule_with_no_inputs_is_skipped_not_scored_zero():
    """The §7.2 contract. Every rule is a stub returning None, so all of them skip."""
    ranked = score_candidate(_profile(), _candidate(), CONFIG)

    assert ranked.components == []
    assert set(ranked.skipped_rules) == set(RULES)
    # No rule contributed, so there is no evidence either way about this candidate.
    assert ranked.score == pytest.approx(0.0)


def test_a_skipped_rule_contributes_no_component():
    """A skip must be invisible in the score and visible in the record.

    If a skip left a zero-valued component behind, a reader of the run could not tell it from a
    rule that genuinely found no overlap.
    """
    ranked = score_candidate(_profile(), _candidate(), CONFIG)
    names = {component.name for component in ranked.components}
    assert "subject_overlap" not in names
    assert "subject_overlap" in ranked.skipped_rules


def test_a_kind_specific_rule_is_skipped_for_other_kinds():
    """`type_match` is R3.4 only (§5.3), so it must not weigh on a vocabulary candidate."""
    vocabulary = score_candidate(
        _profile(),
        _candidate(kind=RecommendationKind.CONTROLLED_VOCABULARY_LINKAGE),
        CONFIG,
    )
    assert "type_match" in vocabulary.skipped_rules


def test_deprecation_is_a_penalty_that_carries_its_reason():
    """§5.3 wants a heavy penalty *and* a flag saying why.

    Recording it as its own attributed component rather than folding it into `maturity` is what
    lets the reason survive into the output document — which matters, because §5.2 retrieves a
    deprecated record on purpose so it can be shown as a warning.
    """
    ranked = score_candidate(_profile(), _candidate(status="deprecated"), CONFIG)

    penalties = [c for c in ranked.components if c.name == "deprecated_penalty"]
    assert len(penalties) == 1
    assert penalties[0].contribution < 0
    assert "deprecated" in (penalties[0].note or "")


def test_a_ready_record_gets_no_penalty():
    ranked = score_candidate(_profile(), _candidate(status="ready"), CONFIG)
    assert not any(c.name == "deprecated_penalty" for c in ranked.components)


def test_every_component_records_its_source():
    """§5.3 requires a model contribution be attributed as its own named component.

    Nothing produces a `source="model"` component yet, but the field is populated from the
    start so that a later model signal cannot be folded invisibly into a rule's output.
    """
    ranked = score_candidate(_profile(), _candidate(status="deprecated"), CONFIG)
    assert ranked.components
    for component in ranked.components:
        assert component.source in {"rule", "model"}


def test_the_score_stays_within_bounds():
    ranked = score_candidate(_profile(), _candidate(status="deprecated"), CONFIG)
    assert 0.0 <= ranked.score <= 1.0


def test_a_weight_missing_from_an_older_config_contributes_nothing():
    """A rule in code but absent from the weights file should not break that run.

    Different from a skip: the rule ran, it just carries no weight in this configuration.
    """
    sparse = RankingConfig(
        version="ranking.sparse",
        confidence_floor=0.5,
        weights={},
        penalties={},
        sha256="0" * 64,
    )
    ranked = score_candidate(_profile(), _candidate(), sparse)
    assert ranked.score == pytest.approx(0.0)
