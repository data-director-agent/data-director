"""dd_sdk.explain: template and model explainers, and the identifier check."""

from __future__ import annotations

import re

import pytest
from opentelemetry.sdk.trace import TracerProvider

from dd_sdk.agent import RunContext
from dd_sdk.contract.models import Derivation
from dd_sdk.explain import (
    ModelExplainer,
    Rationale,
    TemplateExplainer,
    add_usage,
    checked_rationale,
    missing_rationale,
    names_other_identifier,
    with_reason,
)
from dd_sdk.model import Usage
from dd_sdk.testing import FakeModel

PATTERN = re.compile(r"\bREC\.\d+", re.IGNORECASE)


def _ctx() -> RunContext:
    return RunContext(tracer=TracerProvider().get_tracer("test"), input_ref="r", input_hash="h")


class Template(TemplateExplainer[str, str]):
    def rationale(self, item: str) -> str:
        return f"template for {item}"


class Explainer(ModelExplainer[str, str]):
    system_prompt = "system"
    pattern = PATTERN

    def prompt(self, context: str, items: list[str]) -> str:
        return context + ": " + ", ".join(items)

    def template(self, item: str) -> str:
        return f"template for {item}"

    def allowed(self, items: list[str]) -> set[str]:
        return set(items)


def test_the_template_gives_one_rationale_per_item_in_order() -> None:
    out = Template().explain("ctx", ["REC.1", "REC.2"], _ctx())
    assert [r.text for r in out.rationales] == ["template for REC.1", "template for REC.2"]
    assert {r.derivation for r in out.rationales} == {Derivation.TEMPLATE}
    assert out.calls is None


def test_identifiers_outside_those_allowed_are_found() -> None:
    assert names_other_identifier("see rec.2", {"REC.1"}, PATTERN)
    assert not names_other_identifier("see rec.1", {"REC.1"}, PATTERN)
    assert not names_other_identifier("no identifier", set(), PATTERN)


def test_an_ungrounded_rationale_is_replaced_by_the_template() -> None:
    kept = checked_rationale("fits  REC.1\nwell", {"REC.1"}, PATTERN, "fallback")
    replaced = checked_rationale("like REC.9", {"REC.1"}, PATTERN, "fallback")
    assert kept == Rationale("fits REC.1 well", Derivation.MODEL)
    assert replaced.derivation == Derivation.TEMPLATE
    assert replaced.text.startswith("fallback")
    assert missing_rationale("fallback").derivation == Derivation.TEMPLATE


def test_with_reason_keeps_each_rationale_and_says_why() -> None:
    out = with_reason([Rationale("a", Derivation.TEMPLATE)], "model declined")
    assert out[0].text.startswith("a")
    assert "model declined" in out[0].text


def test_usage_adds_and_keeps_unreported_counts_unknown() -> None:
    assert add_usage(Usage(1, 2), Usage(3, None)) == Usage(4, 2)
    assert add_usage(Usage(), Usage()) == Usage()


def test_the_model_writes_each_numbered_rationale() -> None:
    model = FakeModel("1. REC.1 fits.\n2) REC.2 also fits.")
    out = Explainer(model).explain("needs", ["REC.1", "REC.2"], _ctx())
    assert [r.derivation for r in out.rationales] == [Derivation.MODEL, Derivation.MODEL]
    assert out.calls is not None
    assert model.sent[0].system == "system"


@pytest.mark.parametrize("reply", ["1. REC.1 is like REC.7.\n2. fine", "2. fine"])
def test_a_missing_or_ungrounded_line_falls_back_to_the_template(reply: str) -> None:
    out = Explainer(FakeModel(reply)).explain("needs", ["REC.1", "REC.2"], _ctx())
    assert [r.derivation for r in out.rationales] == [Derivation.TEMPLATE, Derivation.MODEL]
    assert out.rationales[0].text.startswith("template for REC.1")


def test_a_refusal_falls_back_to_the_template_for_every_item() -> None:
    out = Explainer(FakeModel(refuse=True)).explain("needs", ["REC.1", "REC.2"], _ctx())
    assert {r.derivation for r in out.rationales} == {Derivation.TEMPLATE}


def test_no_items_means_no_call() -> None:
    model = FakeModel("1. x")
    assert Explainer(model).explain("needs", [], _ctx()).rationales == []
    assert model.sent == []
