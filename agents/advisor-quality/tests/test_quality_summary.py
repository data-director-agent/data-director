"""advisor.quality's summary: a model's by default, the rules' own with the template (factory.py,
docs/specs/agents.md, Model-backed personas). Every model is a `FakeModel`; no test needs a key."""

from __future__ import annotations

from pathlib import Path

import pytest

from dd_agent_advisor_quality.agent import QualityReviewer
from dd_agent_advisor_quality.classes import MetadataRecord, QualityReview
from dd_agent_advisor_quality.factory import SWITCH, build
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.contract.models import Derivation, OutcomeStatus
from dd_sdk.credentials import ConfigError
from dd_sdk.summary import ModelSummariser
from dd_sdk.testing import FakeModel


def sample() -> MetadataRecord:
    return MetadataRecord(
        title="Soil cores", description="Cores from two sites.", keywords=["soil"]
    )


def _summarised(runs_dir: Path, agent: QualityReviewer) -> tuple[QualityReview, str | None]:
    conductor = make_conductor(runs_dir, agent)
    env = conductor.invoke(request("advisor.quality", sample()), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert conductor.grounding_reports[env.invocation_id].passed
    return env.payload_as(QualityReview), env.telemetry.model_id


def test_the_template_gives_the_rules_own_summary_and_calls_no_model(runs_dir: Path) -> None:
    payload, model_id = _summarised(runs_dir, build({SWITCH: "template"}))
    assert payload.summary
    assert payload.summary_derivation is Derivation.TEMPLATE
    assert model_id is None


def test_the_model_writes_the_summary_beside_findings_it_cannot_change(runs_dir: Path) -> None:
    template, _ = _summarised(runs_dir / "template", QualityReviewer())
    model = FakeModel("1. Add a licence and the creators first.", model_id="m-test")
    payload, model_id = _summarised(
        runs_dir / "model", QualityReviewer(summariser=ModelSummariser(model, "s"))
    )
    assert payload.summary == "Add a licence and the creators first."
    assert payload.summary_derivation is Derivation.MODEL
    assert model_id == "m-test"
    assert [x.model_dump(exclude={"grounded_on"}) for x in payload.findings] == [
        x.model_dump(exclude={"grounded_on"}) for x in template.findings
    ]
    (sent,) = model.sent
    assert "Soil cores" in str(sent.messages)


def test_a_summary_naming_an_address_not_given_is_replaced_by_the_template(runs_dir: Path) -> None:
    model = FakeModel("1. See https://example.org/advice for help.")
    payload, _ = _summarised(runs_dir, QualityReviewer(summariser=ModelSummariser(model, "s")))
    assert payload.summary_derivation is Derivation.TEMPLATE
    assert payload.summary and "example.org" not in payload.summary


def test_the_model_is_on_by_default_and_says_how_to_turn_it_off() -> None:
    with pytest.raises(ConfigError, match=f"{SWITCH}=template"):
        build({})


def test_the_card_declares_the_model_only_when_one_is_configured() -> None:
    assert build({SWITCH: "template"}).spec.models == ()
    agent = build({"ANTHROPIC_API_KEY": "unused", "DD_MODEL_ID": "m-test"})
    assert [(m.provider, m.model) for m in agent.spec.models] == [("anthropic", "m-test")]
