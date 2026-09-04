"""The §5.3 scoring rules — REGISTRY REAL, BODIES NOT IMPLEMENTED AT v0.1.

Every rule §5.3 names is present, weighted, and wired into the ranker. None has a body yet, and
that is deliberate rather than unfinished: every rule reads fields off a registry record, and no
v0.1 route fetches one. Written now they could only be tested against records we invented, which
proves the fixture rather than the rule.

What *is* implemented is the contract that is easy to get wrong and expensive to fix later.

**A rule returns `None` to mean "skipped", never `0.0`.** §7.2 is explicit: the routes carry
different fields, so a rule whose inputs are missing must be skipped rather than scored zero.
Treating "this route does not supply that field" as "the field is empty" produces rankings that
vary by route for no visible reason — and a zero is a *statement about the candidate*, while a
skip is a statement about the data. §5.3 makes the same point for entity scope specifically:
"Skipped, not scored zero, where the profile yields no entity terms."
"""

from __future__ import annotations

from collections.abc import Callable

from standards_advisor.models.profile import DatasetProfile
from standards_advisor.registry.base import RegistryRecord

# A rule scores one candidate against one profile, in 0..1, or returns None to be skipped.
Rule = Callable[[DatasetProfile, RegistryRecord], float | None]

_TODO = "not implemented at v0.1 — needs a registry route (§5.3)"


def subject_overlap(profile: DatasetProfile, record: RegistryRecord) -> float | None:
    """The profile's subjects against the record's. The main signal.

    TODO(§5.3): implement once a route supplies `subjects`. Skipped while the profile has no
    subjects — filling them needs the registry's own subject list (§5.1 tier 2, R3.5).
    """
    if not profile.subjects or not record.supplies("subjects"):
        return None
    return None  # TODO(§5.3)


def field_of_research_overlap(profile: DatasetProfile, record: RegistryRecord) -> float | None:
    """Finer-grained terms. Separates records within the same broad subject.

    TODO(§5.3).
    """
    if not profile.fields_of_research or not record.supplies("domains"):
        return None
    return None  # TODO(§5.3)


def entity_scope_overlap(profile: DatasetProfile, record: RegistryRecord) -> float | None:
    """The kinds of thing the profile's values name against the kinds the record covers.

    Separates records within the same field of research — a soil chemistry dataset and a plant
    physiology dataset can share a subject term and still need different vocabularies (§5.2).

    TODO(§5.3). Skipped, never zero, where the profile yields no entity terms.
    """
    if not profile.entity_scope:
        return None
    return None  # TODO(§5.3)


def community_uptake(profile: DatasetProfile, record: RegistryRecord) -> float | None:
    """Named in data policies; adopter count; membership of a registry collection.

    Supports the community-specific versus general distinction. TODO(§5.3).
    """
    if not record.supplies("recommended_by"):
        return None
    return None  # TODO(§5.3)


def repository_fit(profile: DatasetProfile, record: RegistryRecord) -> float | None:
    """Recommended or already in use by the target repository, where the profile names one.

    TODO(§5.3).
    """
    if profile.target_repository is None:
        return None
    return None  # TODO(§5.3)


def maturity(profile: DatasetProfile, record: RegistryRecord) -> float | None:
    """The record's status and how recently it was updated.

    Deprecation is handled as a penalty rather than here (§5.3: "deprecated gets a heavy
    penalty and a flag saying why"), so that the reason survives into the output.

    TODO(§5.3).
    """
    if record.status is None:
        return None
    return None  # TODO(§5.3)


def specificity(profile: DatasetProfile, record: RegistryRecord) -> float | None:
    """Prefer domain-specific where the subject match is strong, general where it is thin.

    Aimed squarely at the failure the Blueprint predicts for fields with no history of FAIR
    practice: that the output will be generic. TODO(§5.3).
    """
    return None  # TODO(§5.3)


def openness(profile: DatasetProfile, record: RegistryRecord) -> float | None:
    """The licence and access conditions of the resource itself. TODO(§5.3)."""
    if not record.supplies("licence"):
        return None
    return None  # TODO(§5.3)


def type_match(profile: DatasetProfile, record: RegistryRecord) -> float | None:
    """R3.4 only: the inferred column type against what the standard applies to.

    Almost entirely mechanical, and the first rule worth writing — tier-1 profiling already
    supplies its input, so it is blocked only on the registry side.

    TODO(§5.3).
    """
    if not profile.columns:
        return None
    return None  # TODO(§5.3)


#: Every rule §5.3 names, keyed by the name used in `config/ranking.v1.toml` and in the
#: `score_components` of the output. The two must agree, and `test_versioning` checks it.
RULES: dict[str, Rule] = {
    "subject_overlap": subject_overlap,
    "field_of_research_overlap": field_of_research_overlap,
    "entity_scope_overlap": entity_scope_overlap,
    "community_uptake": community_uptake,
    "repository_fit": repository_fit,
    "maturity": maturity,
    "specificity": specificity,
    "openness": openness,
    "type_match": type_match,
}

#: Rules that only apply to one kind of recommendation.
KIND_SPECIFIC_RULES: dict[str, frozenset[str]] = {
    "type_match": frozenset({"field_level_standard"}),
}
