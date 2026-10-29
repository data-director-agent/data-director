"""orchestrator.stub through the conductor: routing, delegation to real agents over the in-memory
wire, and the delegation-mode linter on a real orchestrator's reply."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dd_agent_advisor_quality.agent import QualityReviewer
from dd_agent_advisor_standards.factory import build as build_standards
from dd_agent_example_hello.agent import HelloWorld
from dd_agent_orchestrator_stub.agent import (
    DirectorStub,
    entry_named,
    load_entries,
    load_rules,
    route,
)
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.contract.models import (
    ConversationTurn,
    Derivation,
    GroundingMode,
    Message,
    OutcomeStatus,
    ReasonCode,
    Reply,
    TurnRole,
)
from dd_sdk.evidence import input_hash
from dd_sdk.tracing import CHAT, DELEGATE, RETRIEVAL, records_from_jsonl


def conductor(runs_dir: Path):
    return make_conductor(
        runs_dir, DirectorStub(), HelloWorld(), build_standards({}), QualityReviewer()
    )


def ask(runs_dir: Path, text: str, history: list[ConversationTurn] | None = None):
    c = conductor(runs_dir)
    env = c.invoke(
        request("orchestrator.stub", Message(message_text=text, history=history or [])),
        acting_for=TEST_PRINCIPAL,
    )
    return c, env


@pytest.mark.requirement("DD-DELEGATION", "DD-CONVERSATION")
def test_a_greeting_is_routed_to_example_hello_and_relayed(runs_dir: Path) -> None:
    c = conductor(runs_dir)
    env = c.invoke(
        request("orchestrator.stub", Message(message_text="hello Joe")), acting_for=TEST_PRINCIPAL
    )
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.grounding_mode == GroundingMode.DELEGATION
    payload = env.payload_as(Reply)
    assert payload.reply_derivation == Derivation.TEMPLATE
    assert "example.hello@0.1.0" in payload.reply_text
    assert "Hello, Joe!" in payload.reply_text
    [delegation] = env.delegations
    assert delegation.delegated_agent_id == "example.hello"
    assert c.grounding_reports[env.invocation_id].passed

    spans = (runs_dir / env.invocation_id / "spans.jsonl").read_text()
    names = {r.name for r in records_from_jsonl([json.loads(line) for line in spans.splitlines()])}
    assert DELEGATE in names
    assert RETRIEVAL not in names and CHAT not in names
    assert env.telemetry.model_id is None


@pytest.mark.requirement("DD-DELEGATION")
def test_a_request_for_standards_is_routed_to_the_advisor_standards(runs_dir: Path) -> None:
    env = conductor(runs_dir).invoke(
        request("orchestrator.stub", Message(message_text="standards for soil chemistry")),
        acting_for=TEST_PRINCIPAL,
    )
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.delegations[0].delegated_agent_id == "advisor.standards"
    assert "It succeeded" in env.payload_as(Reply).reply_text


def test_a_mention_picks_the_agent_and_no_match_abstains() -> None:
    rules = load_rules()
    found = route("@example.hello Grace Hopper", rules)
    assert not isinstance(found, str)
    assert found.rule.agent_id == "example.hello"
    assert found.input_document["greeted_name"] == "Grace Hopper"
    found = route("@advisor.standards recommend standards for soil chemistry", rules)
    assert not isinstance(found, str) and found.input_document["keywords"] == ["soil chemistry"]
    found = route("@advisor.standards soil chemistry", rules)
    assert not isinstance(found, str) and found.input_document["title"] == "soil chemistry"
    assert isinstance(route("@nobody hi", rules), str)
    assert isinstance(route("what is the weather", rules), str)


@pytest.mark.requirement("DD-OUTCOME")
def test_an_unroutable_message_abstains_naming_what_it_can_route(runs_dir: Path) -> None:
    _, env = ask(
        runs_dir,
        "what is the weather",
        [ConversationTurn(role=TurnRole.USER, turn_text="hi")],
    )
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.OUTSIDE_AGENT_SCOPE
    assert "example.hello" in env.outcome.statement and env.delegations == []


def test_without_a_callback_it_abstains_rather_than_calling_agents_directly(
    runs_dir: Path,
) -> None:
    c = conductor(runs_dir)
    c.harness_url = None
    env = c.invoke(
        request("orchestrator.stub", Message(message_text="hello Joe")), acting_for=TEST_PRINCIPAL
    )
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.CAPABILITY_NOT_IMPLEMENTED


def test_an_unregistered_target_fails_with_an_agent_error(runs_dir: Path) -> None:
    c = make_conductor(runs_dir, DirectorStub(), HelloWorld())  # no advisor.standards
    env = c.invoke(
        request("orchestrator.stub", Message(message_text="standards for soil chemistry")),
        acting_for=TEST_PRINCIPAL,
    )
    assert env.outcome.status == OutcomeStatus.FAILED
    assert env.problem is not None and env.problem.type.endswith("/agent-error")


@pytest.mark.requirement("DD-CONVERSATION")
def test_history_is_part_of_the_input_hash(runs_dir: Path) -> None:
    bare = Message(message_text="hello Joe")
    with_history = Message(
        message_text="hello Joe", history=[ConversationTurn(role=TurnRole.USER, turn_text="hi")]
    )
    assert input_hash(bare.model_dump(mode="json")) != input_hash(
        with_history.model_dump(mode="json")
    )


@pytest.mark.requirement("DD-DELEGATION")
def test_a_request_for_a_metadata_review_is_routed_to_the_advisor_quality(
    runs_dir: Path,
) -> None:
    _, env = ask(runs_dir, "review metadata for Soil cores 2024")
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.delegations[0].delegated_agent_id == "advisor.quality"


@pytest.mark.requirement("DD-ENTRY-POINTS")
def test_a_first_turn_that_names_nothing_asks_which_entry_point_applies(runs_dir: Path) -> None:
    c, env = ask(runs_dir, "hi")
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    text = env.payload_as(Reply).reply_text
    assert "before data collection begins" in text
    assert "prepared for sharing" in text
    assert "Ready to deposit" in text
    assert env.delegations == []
    assert c.grounding_reports[env.invocation_id].passed


@pytest.mark.requirement("DD-ENTRY-POINTS")
def test_entry_two_lists_phases_two_to_six_with_the_agents_and_the_gaps(runs_dir: Path) -> None:
    c, env = ask(runs_dir, "2", [ConversationTurn(role=TurnRole.AGENT, turn_text="Where are you?")])
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    payload = env.payload_as(Reply)
    assert payload.reply_derivation == Derivation.TEMPLATE
    text = payload.reply_text
    assert "Phase 1," not in text
    assert all(f"Phase {n}," in text for n in range(2, 7))
    assert "Validate metadata quality (R4): advisor.quality" in text
    assert "Recommend open formats (R3): advisor.standards" in text
    assert "no agent yet (R8)" in text
    assert "no agent yet (R1)" in text
    assert env.delegations == []
    assert c.grounding_reports[env.invocation_id].passed


@pytest.mark.requirement("DD-ENTRY-POINTS")
def test_entry_one_starts_before_collection_and_names_the_documentation_gap(
    runs_dir: Path,
) -> None:
    _, env = ask(runs_dir, "We are starting a new project and have not collected data yet")
    text = env.payload_as(Reply).reply_text
    assert text.startswith("Entry point 1")
    assert "Draft the data documentation: no agent yet (R5)." in text
    assert "advisor.standards, for example 'standards for soil chemistry'" in text


@pytest.mark.requirement("DD-ENTRY-POINTS")
def test_a_well_formed_request_on_a_first_turn_is_routed_not_questioned(runs_dir: Path) -> None:
    _, env = ask(runs_dir, "hello Joe")
    assert env.delegations[0].delegated_agent_id == "example.hello"


@pytest.mark.parametrize(
    ("text", "number"),
    [
        ("1", 1),
        ("Entry 3", 3),
        ("We haven't collected anything yet", 1),
        ("our data has been collected", 2),
        ("I'm preparing the files for sharing", 2),
        ("ready to deposit", 3),
        ("what is the weather", None),
    ],
)
def test_entry_points_are_recognised_from_the_message(text: str, number: int | None) -> None:
    found = entry_named(text, load_entries())
    assert (found.number if found else None) == number
