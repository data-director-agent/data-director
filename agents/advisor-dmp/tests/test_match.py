"""advisor.dmp with a matcher model (docs/specs/agents.md, Model-backed personas): the model reads
only what the rules leave over, may merge or reconcile a flag but never hides one, and any reply
that cannot be used leaves the rules' result. Every model here is a `FakeModel`; no key is
needed."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from dd_agent_advisor_dmp import factory
from dd_agent_advisor_dmp.agent import DmpChecker
from dd_agent_advisor_dmp.classes import DmpCommitments, DmpDiscrepancies, SharingCommitment
from dd_agent_advisor_dmp.match import (
    DEFAULT_MODEL,
    SYSTEM_PROMPT,
    MatchReply,
    ModelMatcher,
    TemplateMatcher,
)
from dd_agent_advisor_dmp.testing import match_reply
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.agent import describe
from dd_sdk.contract.models import Derivation, Envelope, GroundingMode, OutcomeStatus
from dd_sdk.credentials import ConfigError
from dd_sdk.model import ModelCallError, ModelRequest, declared
from dd_sdk.testing import FakeModel

MODEL = "fake-model"
RENAMED_WHY = "Anonymised transcripts of the same interviews."
LICENCE_WHY = "CC-BY with no version given is read as CC BY 4.0, the plan's licence."

COMMITMENTS = DmpCommitments(
    dmp_identifier="example-dmp-energy-001",
    committed_outputs=[
        SharingCommitment(
            output="Household survey", repository="UK Data Service", access="restricted"
        ),
        SharingCommitment(
            output="Interview transcripts", repository="UK Data Service", access="restricted"
        ),
        SharingCommitment(output="Smart-meter readings", repository="ORDA", licence="CC BY 4.0"),
    ],
    planned_outputs=[
        SharingCommitment(
            output="Household survey", repository="UK Data Service", access="restricted"
        ),
        SharingCommitment(
            output="Anonymised interview transcripts",
            repository="UK Data Service",
            access="open",
        ),
        SharingCommitment(output="Smart-meter readings", repository="ORDA", licence="CC-BY"),
    ],
)
GOOD = match_reply(
    pairings=[("Interview transcripts", "Anonymised interview transcripts", RENAMED_WHY)],
    equivalences=[("licence", "CC BY 4.0", "CC-BY", LICENCE_WHY)],
)


def checker(model: FakeModel) -> DmpChecker:
    """Built as the factory builds it with a model: the model declared on the card."""
    agent = DmpChecker(ModelMatcher(model))
    agent.spec = replace(agent.spec, models=(declared(model),))
    return agent


def run(runs_dir: Path, agent: DmpChecker, asked: DmpCommitments = COMMITMENTS) -> Envelope:
    conductor = make_conductor(runs_dir, agent)
    env = conductor.invoke(request("advisor.dmp", asked), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.grounding_mode == GroundingMode.INPUT_ONLY
    assert conductor.grounding_reports[env.invocation_id].passed
    return env


def flags(env: Envelope) -> list[tuple[str, str, str | None, str | None, Derivation]]:
    return [
        (d.output, d.aspect, d.committed, d.planned, d.discrepancy_derivation)
        for d in env.payload_as(DmpDiscrepancies).discrepancies
    ]


RULES = [
    ("Interview transcripts", "missing", None, None, Derivation.LEXICAL),
    ("Smart-meter readings", "licence", "CC BY 4.0", "CC-BY", Derivation.LEXICAL),
    ("Anonymised interview transcripts", "unplanned", None, None, Derivation.LEXICAL),
]


@pytest.mark.requirement("DD-GROUNDING-MODE", "DD-GROUNDED-PAYLOAD")
def test_a_renamed_output_is_one_flag_for_review_and_its_aspects_are_still_compared(
    runs_dir: Path,
) -> None:
    env = run(runs_dir, checker(FakeModel(GOOD)))

    assert flags(env) == [
        (
            "Interview transcripts",
            "renamed",
            "Interview transcripts",
            "Anonymised interview transcripts",
            Derivation.MODEL,
        ),
        # The paired outputs are compared as matched ones are: the access still differs.
        ("Interview transcripts", "access", "restricted", "open", Derivation.LEXICAL),
    ]
    payload = env.payload_as(DmpDiscrepancies)
    renamed = payload.discrepancies[0]
    assert renamed.reason == RENAMED_WHY
    assert "review" in renamed.message and RENAMED_WHY in renamed.message
    assert all(d.reason is None for d in payload.discrepancies[1:])
    assert f"A model ({MODEL})" in env.outcome.statement
    assert env.telemetry.model_id == MODEL


def test_equivalent_values_are_reconciled_with_their_reason_not_hidden(runs_dir: Path) -> None:
    env = run(runs_dir, checker(FakeModel(GOOD)))

    payload = env.payload_as(DmpDiscrepancies)
    assert all(d.aspect != "licence" for d in payload.discrepancies)
    assert [(r.output, r.aspect, r.committed, r.planned, r.reason) for r in payload.reconciled] == [
        ("Smart-meter readings", "licence", "CC BY 4.0", "CC-BY", LICENCE_WHY)
    ]
    assert "reconciled 1 difference" in env.outcome.statement


def test_only_what_the_rules_leave_over_reaches_the_model(runs_dir: Path) -> None:
    model = FakeModel(GOOD)
    run(runs_dir, checker(model))

    [sent] = model.sent
    assert isinstance(sent, ModelRequest)
    assert sent.system == SYSTEM_PROMPT
    assert sent.schema is MatchReply
    content = json.dumps([m if isinstance(m, dict) else str(m) for m in sent.messages])
    assert "Household survey" not in content  # matched exactly, by rule
    assert "example-dmp-energy-001" not in content
    for named in ("Interview transcripts", "Anonymised interview transcripts", "CC-BY"):
        assert named in content


@pytest.mark.parametrize(
    ("model", "why"),
    [
        (FakeModel(refuse=True), "the model declined"),
        (FakeModel("I think these are the same."), "did not match its schema"),
        (FakeModel(lambda _: (_ for _ in ()).throw(ModelCallError("timed out"))), "timed out"),
    ],
    ids=["refused", "not-json", "unreachable"],
)
def test_a_reply_that_cannot_be_used_leaves_the_rules_result(
    runs_dir: Path, model: FakeModel, why: str
) -> None:
    env = run(runs_dir, checker(model))

    assert flags(env) == RULES
    payload = env.payload_as(DmpDiscrepancies)
    assert payload.reconciled == []
    assert "They were found by rule, because" in env.outcome.statement
    assert why in env.outcome.statement


def test_a_fenced_reply_is_used(runs_dir: Path) -> None:
    env = run(runs_dir, checker(FakeModel(f"```json\n{GOOD}\n```")))
    assert flags(env)[0][1] == "renamed"


def test_proposals_outside_the_input_are_dropped_and_recorded(runs_dir: Path) -> None:
    reply = match_reply(
        pairings=[
            ("Interview transcripts", "Anonymised interview transcripts", RENAMED_WHY),
            # Matched exactly by rule, so not offered.
            ("Household survey", "Anonymised interview transcripts", "Both are about homes."),
            ("Lab notebooks", "Anonymised interview transcripts", "Invented."),
            ("Interview transcripts", "Anonymised interview transcripts", RENAMED_WHY),
        ],
        equivalences=[
            ("licence", "CC BY 4.0", "MIT", "Invented."),
            ("embargo", "none", "12 months", "Not an aspect."),
            ("licence", "CC BY 4.0", "CC-BY", None),
        ],
    )
    env = run(runs_dir, checker(FakeModel(reply)))

    payload = env.payload_as(DmpDiscrepancies)
    # The one good pairing is kept; every licence flag stays, since no equivalence was usable.
    assert [d.aspect for d in payload.discrepancies] == ["renamed", "access", "licence"]
    assert payload.reconciled == []
    assert payload.dropped == [
        "pairing 'Household survey' with 'Anonymised interview transcripts': names "
        "'Household survey', which is not a committed output left unmatched",
        "pairing 'Lab notebooks' with 'Anonymised interview transcripts': names "
        "'Lab notebooks', which is not a committed output left unmatched",
        "pairing 'Interview transcripts' with 'Anonymised interview transcripts': paired twice",
        "licence 'CC BY 4.0' as 'MIT': names 'MIT', which is not a planned licence in the input",
        "embargo 'none' as '12 months': 'embargo' is not an aspect it may reconcile",
        "licence 'CC BY 4.0' as 'CC-BY': gives no reason",
    ]
    assert "6 proposals it made were not used" in env.outcome.statement


def test_no_call_when_the_rules_leave_nothing_to_read(runs_dir: Path) -> None:
    model = FakeModel(GOOD)
    same = DmpCommitments(
        committed_outputs=[SharingCommitment(output="Survey", licence="CC BY 4.0")],
        planned_outputs=[SharingCommitment(output="survey ", licence="cc by 4.0")],
    )
    env = run(runs_dir, checker(model), same)

    assert model.sent == []
    assert flags(env) == []
    assert "left nothing for the matcher model" in env.outcome.statement
    assert env.telemetry.model_calls == []


def test_the_call_and_its_prompt_are_recorded(runs_dir: Path) -> None:
    env = run(runs_dir, checker(FakeModel(GOOD)))

    [made] = env.telemetry.model_calls
    assert made.model_id == MODEL
    assert env.telemetry.input_tokens == 100 and env.telemetry.output_tokens == 40


def test_the_factory_runs_the_template_when_set_to_it_and_declares_no_model() -> None:
    agent = factory.build({factory.SWITCH: "template"})
    assert isinstance(agent.matcher, TemplateMatcher)
    assert describe(agent.spec)["models"] == []


def test_the_model_matcher_is_on_by_default_and_says_how_to_run_without_it() -> None:
    with pytest.raises(ConfigError, match=f"{factory.SWITCH}=template"):
        factory.build({})


@pytest.mark.parametrize("setting", ["model", "anthropic"])
def test_the_factory_declares_the_model_it_sends_data_to(setting: str) -> None:
    pytest.importorskip("anthropic")
    agent = factory.build({factory.SWITCH: setting, "ANTHROPIC_API_KEY": "sk-test"})
    assert isinstance(agent.matcher, ModelMatcher)
    [use] = agent.spec.models
    assert (use.provider, use.model) == ("anthropic", DEFAULT_MODEL)


def test_an_unknown_matcher_stops_the_agent_at_start_up() -> None:
    with pytest.raises(ConfigError):
        factory.build({factory.SWITCH: "regex"})
