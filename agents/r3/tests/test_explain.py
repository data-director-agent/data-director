"""Explainers: the template is deterministic; the model explainer cannot smuggle identities."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from dd_agent_r3 import testing as fakes
from dd_agent_r3.explain import (
    SYSTEM_PROMPT,
    AnthropicExplainer,
    TemplateExplainer,
    template_rationale,
)
from dd_sdk.agent import RunContext
from dd_sdk.contract.models import DatasetProfile, Derivation, RecommendationKind
from dd_sdk.tracing import make_tracing


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
    assert [r.derivation for r in out.rationales] == [Derivation.TEMPLATE, Derivation.TEMPLATE]


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


class _CountingClient:
    """A stub Anthropic client whose every call reports a different token count."""

    def __init__(self) -> None:
        self.calls = 0
        self.messages = self

    def create(self, **_: object) -> SimpleNamespace:
        self.calls += 1
        return SimpleNamespace(
            usage=SimpleNamespace(input_tokens=self.calls * 10, output_tokens=self.calls),
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text="1. First.\n2. Second.")],
        )


def test_each_call_returns_its_own_usage() -> None:
    """Usage travels with the call, so concurrent runs on one explainer cannot swap counts."""
    pytest.importorskip("anthropic")
    ex = AnthropicExplainer(client=_CountingClient(), model_id="claude-opus-5")  # type: ignore[arg-type]
    tracing = make_tracing()
    ctx = RunContext(tracer=tracing.tracer, input_ref="", input_hash="")
    first = ex.explain(DatasetProfile(), _items(), ctx)
    second = ex.explain(DatasetProfile(), _items(), ctx)
    assert (first.usage.input_tokens, first.usage.output_tokens) == (10, 1)
    assert (second.usage.input_tokens, second.usage.output_tokens) == (20, 2)
    assert not hasattr(ex, "usage")
