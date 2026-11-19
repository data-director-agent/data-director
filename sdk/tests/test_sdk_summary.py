"""dd_sdk.summary: the template and model summarisers, and their fallbacks."""

from __future__ import annotations

from opentelemetry.sdk.trace import TracerProvider

from dd_sdk.agent import AgentResult, RunContext
from dd_sdk.contract.models import Derivation, Outcome, OutcomeStatus
from dd_sdk.model import ModelCallError, ModelRequest, ModelResponse
from dd_sdk.summary import (
    UNREACHABLE,
    Findings,
    ModelSummariser,
    TemplateSummariser,
    summarise,
    with_calls,
)
from dd_sdk.testing import FakeModel

FINDINGS = Findings(
    {"identifiers": ["https://doi.org/10.5281/zenodo.1"], "valid": 1},
    "One identifier was recognised.",
)


def _ctx() -> RunContext:
    return RunContext(tracer=TracerProvider().get_tracer("test"), input_ref="r", input_hash="h")


def test_the_template_gives_the_rules_own_summary_and_calls_no_model() -> None:
    summary, explanation = summarise(TemplateSummariser(), FINDINGS, _ctx())
    assert summary.text == "One identifier was recognised."
    assert summary.derivation is Derivation.TEMPLATE
    assert explanation.calls is None


def test_the_model_writes_the_summary_from_the_findings() -> None:
    model = FakeModel("1. The DOI 10.5281/zenodo.1 is well formed.")
    summary, explanation = summarise(ModelSummariser(model, "system"), FINDINGS, _ctx())
    assert summary.text == "The DOI 10.5281/zenodo.1 is well formed."
    assert summary.derivation is Derivation.MODEL
    assert explanation.calls is not None and explanation.calls.calls
    (sent,) = model.sent
    assert sent.system == "system"
    assert "zenodo.1" in str(sent.messages)


def test_a_summary_naming_an_identifier_the_findings_do_not_give_is_replaced() -> None:
    model = FakeModel("1. See https://example.org/elsewhere for more.")
    summary, _ = summarise(ModelSummariser(model, "system"), FINDINGS, _ctx())
    assert summary.text.startswith("One identifier was recognised.")
    assert summary.derivation is Derivation.TEMPLATE


def test_a_refusal_or_a_missing_line_falls_back_on_the_template() -> None:
    for model in (FakeModel(refuse=True), FakeModel("no numbered line")):
        summary, _ = summarise(ModelSummariser(model, "system"), FINDINGS, _ctx())
        assert summary.text.startswith("One identifier was recognised.")
        assert summary.derivation is Derivation.TEMPLATE


class Unreachable(FakeModel):
    def send(self, request: ModelRequest) -> ModelResponse:
        raise ModelCallError("down")


def test_a_model_that_cannot_be_reached_falls_back_on_the_template_and_says_so() -> None:
    summary, explanation = summarise(ModelSummariser(Unreachable(), "system"), FINDINGS, _ctx())
    assert summary.text == "One identifier was recognised." + UNREACHABLE
    assert summary.derivation is Derivation.TEMPLATE
    assert explanation.calls is None


def test_the_calls_made_are_put_on_the_result() -> None:
    model = FakeModel("1. Fine.")
    _, explanation = summarise(ModelSummariser(model, "system"), FINDINGS, _ctx())
    result = AgentResult(outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement="Done."))
    made = with_calls(result, model.model_id, explanation)
    assert made.model_id == "fake-model"
    assert made.model_calls and made.input_tokens == explanation.usage.input_tokens
