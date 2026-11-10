"""orchestrator.stub through the conductor: routing, delegation to real agents over the in-memory
wire, and the delegation-mode linter on a real orchestrator's reply."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

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
    QuestionAnswer,
    ReasonCode,
    Reply,
    ReplyAnswers,
    TurnRole,
)
from dd_sdk.evidence import input_hash
from dd_sdk.process_flow import ENTRIES, PlannedStep, entry, plan
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


def listed(
    text: str, start: int, manifest: Iterable[Mapping[str, Any]]
) -> list[tuple[PlannedStep, str]]:
    """Each step planned from entry point `start`, with the line of `text` that lists it, after
    checking that the line says what serves the step: its agents, "no agent yet" or "out of
    scope", and its requirements."""
    lines = text.splitlines()
    found = []
    for planned in plan(entry(start), manifest):
        step = planned.step
        [line] = [line for line in lines if line.startswith(f"- {step.text}")]
        if step.out_of_scope:
            assert "out of scope" in line, line
        else:
            assert all(r in line for r in step.requirements), line
            if planned.agent_ids:
                assert all(a in line for a in planned.agent_ids), line
            else:
                assert "no agent yet" in line, line
        found.append((planned, line))
    return found


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
    assert "example.hello@" in payload.reply_text
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
    reply = env.payload_as(Reply)
    (question,) = reply.reply_questions or []
    assert not question.question_multiple and question.question_options is not None
    assert [o.option_value for o in question.question_options] == [str(e.number) for e in ENTRIES]
    assert all(o.option_label for o in question.question_options)
    assert env.delegations == []
    assert c.grounding_reports[env.invocation_id].passed


@pytest.mark.requirement("DD-ENTRY-POINTS")
def test_a_chosen_entry_point_is_read_from_the_answer_not_the_text(runs_dir: Path) -> None:
    c = conductor(runs_dir)
    asked = c.invoke(
        request("orchestrator.stub", Message(message_text="hi")), acting_for=TEST_PRINCIPAL
    )
    (question,) = asked.payload_as(Reply).reply_questions or []
    answer = ReplyAnswers(
        answer_to=asked.invocation_id,
        given_answers=[QuestionAnswer(answered_key=question.question_key, answer_values=["3"])],
    )
    message = Message(
        message_text="Ready to deposit data into a repository",
        history=[ConversationTurn(role=TurnRole.AGENT, turn_text="Where are you?")],
        reply_answers=answer,
    )
    env = c.invoke(request("orchestrator.stub", message), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    text = env.payload_as(Reply).reply_text
    assert "Phase 3," in text and "Phase 2," not in text


@pytest.mark.requirement("DD-ENTRY-POINTS")
def test_entry_two_lists_phases_two_to_six_with_the_agents_and_the_gaps(runs_dir: Path) -> None:
    c, env = ask(runs_dir, "2", [ConversationTurn(role=TurnRole.AGENT, turn_text="Where are you?")])
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    payload = env.payload_as(Reply)
    assert payload.reply_derivation == Derivation.TEMPLATE
    text = payload.reply_text
    assert "Phase 1," not in text
    assert all(f"Phase {n}," in text for n in range(2, 7))
    steps = listed(text, 2, c.registry.manifest())
    served = {a for planned, _ in steps for a in planned.agent_ids}
    assert {"advisor.quality", "advisor.standards"} <= served
    assert any(not p.agent_ids and not p.step.out_of_scope for p, _ in steps)  # the gaps
    assert env.delegations == []
    assert c.grounding_reports[env.invocation_id].passed


@pytest.mark.requirement("DD-ENTRY-POINTS")
def test_data_management_plan_steps_are_named_and_said_to_be_out_of_scope(
    runs_dir: Path,
) -> None:
    c, env = ask(runs_dir, "We are starting a new project and have not collected data yet")
    steps = listed(env.payload_as(Reply).reply_text, 1, c.registry.manifest())
    plan_steps = [p.step for p, _ in steps if "Data Management Plan" in p.step.text]
    assert any(step.out_of_scope for step in plan_steps)
    # Checking a deposit against an existing plan (R8) is in scope: a gap, not out of scope.
    assert any("R8" in step.requirements and not step.out_of_scope for step in plan_steps)
    assert env.delegations == []


@pytest.mark.requirement("DD-ENTRY-POINTS")
def test_entry_one_starts_before_collection_and_names_the_documentation_gap(
    runs_dir: Path,
) -> None:
    c, env = ask(runs_dir, "We are starting a new project and have not collected data yet")
    text = env.payload_as(Reply).reply_text
    assert text.startswith("Entry point 1")
    lines = {p.step.id: (p, line) for p, line in listed(text, 1, c.registry.manifest())}
    documentation, line = lines["setup.documentation"]
    assert not documentation.agent_ids and "R5" in line
    # An agent that serves a step is named with an example of what to ask it.
    [standards] = [r for r in load_rules() if r.agent_id == "advisor.standards"]
    assert any(
        "advisor.standards" in line and standards.example in line for _, line in lines.values()
    )


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
