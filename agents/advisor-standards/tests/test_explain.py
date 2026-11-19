"""The template explainer is deterministic; the model advisor's checks are in
test_standards_advise.py."""

from __future__ import annotations

import pytest

from dd_agent_advisor_standards import testing as fakes
from dd_agent_advisor_standards.classes import DatasetProfile, RecommendationKind
from dd_agent_advisor_standards.explain import (
    TemplateExplainer,
    names_other_identifier,
    template_rationale,
)
from dd_sdk.contract.models import Derivation


def _items() -> list[tuple]:  # type: ignore[type-arg]
    return [
        (fakes.AGROVOC, RecommendationKind.CONTROLLED_VOCABULARY, "dataset", ("lexical=1.00",)),
        (
            fakes.ISO8601,
            RecommendationKind.FIELD_FORMAT,
            "field:collection_date",
            ("lexical=0.90",),
        ),
    ]


@pytest.mark.requirement("C14.1")
def test_template_rationale_names_resource_kind_and_target() -> None:
    text = template_rationale(*_items()[1])
    assert "ISO 8601" in text and "'collection_date'" in text and "field-level" in text
    assert "not by a model" in text
    out = TemplateExplainer().explain(DatasetProfile(), _items(), None)  # type: ignore[arg-type]
    assert [r.derivation for r in out.rationales] == [Derivation.TEMPLATE, Derivation.TEMPLATE]


def test_an_identifier_other_than_the_allowed_is_noticed() -> None:
    assert names_other_identifier("See FAIRsharing.made-up.", {"FAIRsharing.test-agrovoc"})
    assert not names_other_identifier(
        "AGROVOC (fairsharing.test-agrovoc) fits.", {"FAIRsharing.test-agrovoc"}
    )
    assert not names_other_identifier("No identifier here.", set())
