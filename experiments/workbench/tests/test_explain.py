"""Explainers: the template is deterministic; the model explainer cannot smuggle identities."""

from __future__ import annotations

import pytest

from tests import r3_fakes as fakes
from workbench.agents.r3.explain import (
    SYSTEM_PROMPT,
    AnthropicExplainer,
    TemplateExplainer,
    template_rationale,
)
from workbench.contract.models import DatasetProfile, Derivation, RecommendationKind

# R3 is not yet ported to the generalised agent interface (AgentSpec, polymorphic input and
# payload, declared grounding mode); see src/workbench/agents/r3/factory.py. TODO: port and
# remove this marker. Tests that still pass are reported xpassed, not passed, so they do not
# substantiate a requirement in CONFORMANCE.md.
pytestmark = pytest.mark.xfail(
    reason="R3 not yet ported to the generalised agent interface (TODO)", strict=False
)


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


@pytest.mark.requirement("C14")
def test_template_rationale_names_resource_kind_and_target() -> None:
    text = template_rationale(*_items()[1])
    assert "ISO 8601" in text and "'collection_date'" in text and "field-level" in text
    assert "not by a model" in text
    out = TemplateExplainer().explain(DatasetProfile(), _items(), None)  # type: ignore[arg-type]
    assert [r.derivation for r in out] == [Derivation.TEMPLATE, Derivation.TEMPLATE]


class _NoClient:
    pass


def _explainer() -> AnthropicExplainer:
    pytest.importorskip("anthropic")
    return AnthropicExplainer(client=_NoClient(), model_id="claude-opus-5")  # type: ignore[arg-type]


@pytest.mark.requirement("DD-GROUNDING", "C14")
def test_model_output_with_ungrounded_identifier_falls_back_to_template() -> None:
    ex = _explainer()
    text = "1. AGROVOC fits the soil keywords.\n2. Use FAIRsharing.made-up for dates."
    out = ex._parse(text, _items())
    assert out[0].derivation == Derivation.MODEL and out[0].text.startswith("AGROVOC fits")
    assert out[1].derivation == Derivation.TEMPLATE and "replaced" in out[1].text


def test_missing_or_reordered_lines_fall_back_per_item() -> None:
    ex = _explainer()
    out = ex._parse("2. Only the second item was explained (FAIRsharing.test-iso8601).", _items())
    assert out[0].derivation == Derivation.TEMPLATE
    assert out[1].derivation == Derivation.MODEL


def test_prompt_carries_metadata_only() -> None:
    """Only profile metadata and registry descriptions reach the model; never data values."""
    ex = _explainer()
    profile = DatasetProfile(title="Soil", keywords=["soil"], fields=[])
    prompt = ex._prompt(profile, _items())
    assert "Soil" in prompt and "AGROVOC" in prompt and "ISO 8601" in prompt
    assert "ALREADY been selected" in SYSTEM_PROMPT and "Do not recommend anything" in SYSTEM_PROMPT
