"""advisor.linking's relation table (relations.yaml) against DataCite's controlled lists."""

from __future__ import annotations

import pytest

from dd_agent_advisor_linking.relations import for_type, load_relations

# DataCite Metadata Schema 4.6, Appendix 1: relationType and resourceTypeGeneral.
RELATION_TYPES = frozenset(
    [
        "IsCitedBy",
        "Cites",
        "IsSupplementTo",
        "IsSupplementedBy",
        "IsContinuedBy",
        "Continues",
        "IsDescribedBy",
        "Describes",
        "HasMetadata",
        "IsMetadataFor",
        "HasVersion",
        "IsVersionOf",
        "IsNewVersionOf",
        "IsPreviousVersionOf",
        "IsPartOf",
        "HasPart",
        "IsPublishedIn",
        "IsReferencedBy",
        "References",
        "IsDocumentedBy",
        "Documents",
        "IsCompiledBy",
        "Compiles",
        "IsVariantFormOf",
        "IsOriginalFormOf",
        "IsIdenticalTo",
        "IsReviewedBy",
        "Reviews",
        "IsDerivedFrom",
        "IsSourceOf",
        "IsRequiredBy",
        "Requires",
        "IsObsoletedBy",
        "Obsoletes",
        "IsCollectedBy",
        "Collects",
        "HasTranslation",
        "IsTranslationOf",
    ]
)
RESOURCE_TYPES_GENERAL = frozenset(
    [
        "Audiovisual",
        "Award",
        "Book",
        "BookChapter",
        "Collection",
        "ComputationalNotebook",
        "ConferencePaper",
        "ConferenceProceeding",
        "DataPaper",
        "Dataset",
        "Dissertation",
        "Event",
        "Image",
        "Instrument",
        "InteractiveResource",
        "Journal",
        "JournalArticle",
        "Model",
        "OutputManagementPlan",
        "PeerReview",
        "PhysicalObject",
        "Preprint",
        "Project",
        "Report",
        "Service",
        "Software",
        "Sound",
        "Standard",
        "StudyRegistration",
        "Text",
        "Workflow",
        "Other",
    ]
)
# Crossref's work types (api.crossref.org/types).
CROSSREF_TYPES = frozenset(
    [
        "book-section",
        "monograph",
        "report-component",
        "report",
        "peer-review",
        "book-track",
        "journal-article",
        "book-part",
        "other",
        "book",
        "journal-volume",
        "book-set",
        "reference-entry",
        "proceedings-article",
        "journal",
        "component",
        "book-chapter",
        "proceedings-series",
        "report-series",
        "proceedings",
        "database",
        "standard",
        "reference-book",
        "posted-content",
        "journal-issue",
        "dissertation",
        "grant",
        "dataset",
        "book-series",
        "edited-book",
    ]
)

ROWS = load_relations()


def test_every_relation_is_a_datacite_relation_type() -> None:
    assert {r.relation for r in ROWS if r.relation is not None} <= RELATION_TYPES


def test_every_type_is_datacite_or_crossref_and_listed_once() -> None:
    types = [t for r in ROWS for t in r.types]
    assert set(types) <= RESOURCE_TYPES_GENERAL | CROSSREF_TYPES
    assert len(types) == len(set(types))


def test_every_row_says_what_to_check() -> None:
    assert all(r.advice for r in ROWS)


@pytest.mark.parametrize("record_type", [None, "", "Other", "other"])
def test_a_type_no_row_lists_has_no_suggestion(record_type: str | None) -> None:
    assert for_type(record_type) is None
