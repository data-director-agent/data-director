"""advisor.fairness with a model writer: rules decide `met`, the model writes only the
recommendations, and each unusable one falls back to the template (docs/specs/agents.md,
Model-backed personas). Every model is a `FakeModel`; no test needs a key."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from dd_agent_advisor_fairness.agent import FairAssessor
from dd_agent_advisor_fairness.classes import FairnessReport, PublishedRecord
from dd_agent_advisor_fairness.factory import SWITCH, build
from dd_agent_advisor_fairness.testing import writer_reply
from dd_agent_advisor_fairness.write import (
    MAX_RECOMMENDATION,
    SYSTEM_PROMPT,
    ModelWriter,
    TemplateWriter,
)
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.contract.models import Derivation, Envelope, GroundingMode, OutcomeStatus
from dd_sdk.credentials import ConfigError
from dd_sdk.model import ModelCallError, ModelRequest
from dd_sdk.testing import FakeModel

MODEL = "claude-test"
ORCID = "https://orcid.org/0000-0002-1825-0097"
RECORD = PublishedRecord(
    identifier="https://data.example.ac.uk/datasets/household-energy-2024",
    title="Household energy use in Sheffield, 2024",
    description="Half-hourly smart meter readings from 120 households.",
    licence="CC-BY-4.0",
    keywords=["energy demand"],
    creators=["Ada Byron", "Charles Babbage"],
    creator_identifiers=[ORCID],
    formats=["text/csv"],
    access_protocol="https",
)
# The rule table finds these three checks unmet for RECORD.
UNMET = ["identifier-is-doi", "related-identifiers-present", "creators-identified"]
TAILORED = "Ask the repository to mint a DOI for 'Household energy use in Sheffield, 2024'."


def invoke(runs_dir: Path, model: FakeModel) -> tuple[Envelope, FairnessReport]:
    conductor = make_conductor(runs_dir, FairAssessor(ModelWriter(model)))
    env = conductor.invoke(request("advisor.fairness", RECORD), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert conductor.grounding_reports[env.invocation_id].passed
    return env, env.payload_as(FairnessReport)


def template_run(runs_dir: Path) -> FairnessReport:
    conductor = make_conductor(runs_dir / "template", FairAssessor())
    env = conductor.invoke(request("advisor.fairness", RECORD), acting_for=TEST_PRINCIPAL)
    return env.payload_as(FairnessReport)


def derivations(payload: FairnessReport) -> dict[str, Derivation | None]:
    return {c.check: c.recommendation_derivation for c in payload.checks if not c.met}


def test_unmet_checks_get_the_models_recommendation_and_met_stays_by_rule(
    runs_dir: Path,
) -> None:
    replies = [(check, f"{TAILORED} ({check})") for check in UNMET]
    env, payload = invoke(runs_dir, FakeModel(writer_reply(replies), model_id=MODEL))

    assert env.grounding_mode == GroundingMode.INPUT_ONLY
    assert [(c.check, c.met) for c in payload.checks] == [
        (c.check, c.met) for c in template_run(runs_dir).checks
    ]
    assert derivations(payload) == dict.fromkeys(UNMET, Derivation.MODEL)
    assert {c.check: c.recommendation for c in payload.checks if not c.met} == dict(replies)
    assert all(
        c.recommendation is None and c.recommendation_derivation is None
        for c in payload.checks
        if c.met
    )
    assert env.telemetry.model_id == MODEL
    assert [c.model_id for c in env.telemetry.model_calls] == [MODEL]


def test_the_model_is_sent_the_record_and_only_the_unmet_checks(runs_dir: Path) -> None:
    model = FakeModel(writer_reply(), model_id=MODEL)
    invoke(runs_dir, model)
    [sent] = model.sent
    assert sent.system == SYSTEM_PROMPT
    (message,) = sent.messages
    assert isinstance(message, Mapping)
    body = json.loads(message["content"])
    assert body["record"]["title"] == RECORD.title
    assert body["record"]["description"] == RECORD.description
    assert [c["check"] for c in body["unmet_checks"]] == UNMET
    assert all(c["template"] for c in body["unmet_checks"])


def test_a_check_the_model_leaves_out_keeps_its_template(runs_dir: Path) -> None:
    model = FakeModel(writer_reply([("identifier-is-doi", TAILORED)]), model_id=MODEL)
    _, payload = invoke(runs_dir, model)
    assert derivations(payload) == {
        "identifier-is-doi": Derivation.MODEL,
        "related-identifiers-present": Derivation.TEMPLATE,
        "creators-identified": Derivation.TEMPLATE,
    }
    assert all(c.recommendation for c in payload.checks if not c.met)


@pytest.mark.parametrize(
    ("check", "text"),
    [
        ("title-present", "A check the record meets."),
        ("no-such-check", "A check that does not exist."),
        ("identifier-is-doi", "   "),
        ("identifier-is-doi", "x" * (MAX_RECOMMENDATION + 1)),
        ("identifier-is-doi", "Cite it as https://doi.org/10.5555/invented."),
        ("identifier-is-doi", "Cite it as 10.5555/invented."),
        ("creators-identified", "Add Charles Babbage's ORCID iD, 0000-0001-2345-6789."),
    ],
)
def test_an_unusable_recommendation_is_dropped_and_the_template_kept(
    runs_dir: Path, check: str, text: str
) -> None:
    env, payload = invoke(runs_dir, FakeModel(writer_reply([(check, text)]), model_id=MODEL))
    assert [(c.check, c.met) for c in payload.checks] == [
        (c.check, c.met) for c in template_run(runs_dir).checks
    ]
    assert derivations(payload) == dict.fromkeys(UNMET, Derivation.TEMPLATE)
    assert check in env.outcome.statement


def test_an_identifier_the_record_gives_may_be_named(runs_dir: Path) -> None:
    text = f"Charles Babbage has no identifier; only Ada Byron's ({ORCID}) is given."
    model = FakeModel(writer_reply([("creators-identified", text)]), model_id=MODEL)
    _, payload = invoke(runs_dir, model)
    assert derivations(payload)["creators-identified"] == Derivation.MODEL


def test_a_second_recommendation_for_one_check_is_dropped(runs_dir: Path) -> None:
    replies = [("identifier-is-doi", TAILORED), ("identifier-is-doi", "Another.")]
    _, payload = invoke(runs_dir, FakeModel(writer_reply(replies), model_id=MODEL))
    [doi] = [c for c in payload.checks if c.check == "identifier-is-doi"]
    assert (doi.recommendation, doi.recommendation_derivation) == (TAILORED, Derivation.MODEL)


def test_a_fenced_reply_that_matches_is_used(runs_dir: Path) -> None:
    fenced = f"```json\n{writer_reply([('identifier-is-doi', TAILORED)])}\n```"
    _, payload = invoke(runs_dir, FakeModel(fenced, model_id=MODEL))
    assert derivations(payload)["identifier-is-doi"] == Derivation.MODEL


def _unreachable(request: ModelRequest) -> str:
    raise ModelCallError("connection refused")


@pytest.mark.parametrize(
    "model",
    [
        FakeModel(refuse=True, model_id=MODEL),
        FakeModel("I cannot help with that.", model_id=MODEL),
        FakeModel(json.dumps({"recommendations": [{"check": "x"}]}), model_id=MODEL),
        FakeModel(_unreachable, model_id=MODEL),
    ],
)
def test_an_unusable_reply_leaves_every_recommendation_as_the_template(
    runs_dir: Path, model: FakeModel
) -> None:
    env, payload = invoke(runs_dir, model)
    template = template_run(runs_dir)
    assert [(c.check, c.met, c.recommendation) for c in payload.checks] == [
        (c.check, c.met, c.recommendation) for c in template.checks
    ]
    assert derivations(payload) == dict.fromkeys(UNMET, Derivation.TEMPLATE)
    assert env.telemetry.model_id == MODEL


def test_a_record_that_meets_every_check_calls_no_model(runs_dir: Path) -> None:
    record = RECORD.model_copy(
        update={
            "identifier": "https://doi.org/10.5555/household-energy",
            "related_identifiers": ["https://doi.org/10.5555/article"],
            "creators": ["Ada Byron"],
        }
    )
    model = FakeModel(writer_reply(), model_id=MODEL)
    conductor = make_conductor(runs_dir, FairAssessor(ModelWriter(model)))
    env = conductor.invoke(request("advisor.fairness", record), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert all(c.met for c in env.payload_as(FairnessReport).checks)
    assert model.sent == []


def test_the_template_build_needs_no_model_and_no_key() -> None:
    agent = build({"DD_FAIRNESS_WRITER": "template"})
    assert isinstance(agent.writer, TemplateWriter)
    assert agent.spec.models == ()


def test_the_model_is_on_by_default_and_says_how_to_turn_it_off() -> None:
    with pytest.raises(ConfigError, match="DD_FAIRNESS_WRITER=template"):
        build({})


def test_the_model_writer_is_declared_on_the_card() -> None:
    agent = build({SWITCH: "model", "DD_MODEL_ID": MODEL, "ANTHROPIC_API_KEY": "sk-test"})
    assert isinstance(agent.writer, ModelWriter)
    (use,) = agent.spec.models
    assert (use.provider, use.model) == ("anthropic", MODEL)


def test_an_unknown_writer_is_a_configuration_error() -> None:
    with pytest.raises(ConfigError):
        build({SWITCH: "gpt"})
