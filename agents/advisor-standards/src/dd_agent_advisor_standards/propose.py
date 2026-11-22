"""Each recommendation as a `standard` project fact for the researcher to choose
(docs/specs/projects.md, #1391).

A recommendation is advice; a standard becomes the project's only when a person confirms the
proposal, and a proposal they reject is not chosen. The proposal names the record's name and
identifier, from the record the recommendation cites, because a later agent is given the decided
fact and not this run's evidence. Its subject is the standard's name, followed by the field for a
field-level recommendation, so a standard chosen for the dataset and for one field are decided
apart, and a person who states the same standard for the dataset decides the same fact.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from dd_agent_advisor_standards.classes import Recommendation, RecommendationKind
from dd_agent_advisor_standards.fairsharing.records import Record
from dd_sdk.contract.facts import DATASET_TARGET, FactKind, ProjectFact, StandardKind

# The core's kind of standard for each kind of recommendation.
STANDARD_KINDS: Mapping[RecommendationKind, StandardKind] = {
    RecommendationKind.CONTROLLED_VOCABULARY: StandardKind.CONTROLLED_VOCABULARY,
    RecommendationKind.ONTOLOGY: StandardKind.ONTOLOGY,
    RecommendationKind.TERMINOLOGY_UNCLASSIFIED: StandardKind.TERMINOLOGY,
    RecommendationKind.DATA_FORMAT: StandardKind.DATA_FORMAT,
    RecommendationKind.FIELD_FORMAT: StandardKind.FIELD_FORMAT,
}

BECAUSE = (
    "The Standards Librarian recommended it from FAIRsharing ({snapshot}). Confirm it if you "
    "will use it for {what}, or reject it if you will not."
)


def subject(name: str, target: str) -> str:
    """The key a decision on the standard counts by."""
    return name if target == DATASET_TARGET else f"{name} ({target})"


def identifier(record: Record) -> str:
    """The record's DOI as a URL where it has one, else its FAIRsharing page."""
    if record.doi:
        return record.doi if record.doi.startswith("http") else f"https://doi.org/{record.doi}"
    return record.url


def proposals(
    items: Sequence[Recommendation], records: Mapping[str, Record], snapshot: str
) -> list[ProjectFact]:
    """One proposal for each recommendation, in its order, without repeats."""
    proposed: dict[str, ProjectFact] = {}
    for item in items:
        record = records[item.grounded_on[0].source_id]
        key = subject(record.name, item.target)
        what = "the dataset" if item.target == DATASET_TARGET else f"the {item.target}"
        proposed.setdefault(
            key,
            ProjectFact(
                fact_kind=FactKind.STANDARD,
                fact_subject=key,
                standard_name=record.name,
                standard_id=identifier(record),
                standard_kind=STANDARD_KINDS[item.kind],
                standard_target=item.target,
                proposed_because=BECAUSE.format(snapshot=snapshot, what=what),
            ),
        )
    return list(proposed.values())
