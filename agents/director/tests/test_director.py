"""director.stub through the conductor: routing, delegation to real agents over the in-memory
wire, and the delegation-mode linter on a real orchestrator's reply."""

from __future__ import annotations

from pathlib import Path

import pytest

from dd_agent_director.agent import DirectorStub, load_rules, route
from dd_agent_factcheck.agent import FactChecker
from dd_agent_hello.agent import HelloWorld
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
from dd_sdk.tracing import CHAT, RETRIEVAL
from workbench.testing import make_conductor, request


def conductor(runs_dir: Path):
    return make_conductor(runs_dir, DirectorStub(), HelloWorld(), FactChecker())


@pytest.mark.requirement("DD-DELEGATION", "DD-CONVERSATION")
def test_a_greeting_is_routed_to_hello_world_and_relayed(runs_dir: Path) -> None:
    c = conductor(runs_dir)
    env = c.invoke(request("director.stub", Message(message_text="hello Joe")))
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.grounding_mode == GroundingMode.DELEGATION
    assert isinstance(env.payload, Reply)
    assert env.payload.reply_derivation == Derivation.TEMPLATE
    assert "hello.world@0.1.0" in env.payload.reply_text
    assert "Hello, Joe!" in env.payload.reply_text
    [delegation] = env.delegations
    assert delegation.delegated_agent_id == "hello.world"
    assert c.grounding_reports[env.invocation_id].passed

    names = {r.name for r in c.tracing.finished_records(env.telemetry.trace_id)}
    assert RETRIEVAL not in names and CHAT not in names
    assert env.telemetry.model_id is None


@pytest.mark.requirement("DD-DELEGATION")
def test_a_claim_is_routed_to_the_fact_checker(runs_dir: Path) -> None:
    env = conductor(runs_dir).invoke(
        request(
            "director.stub",
            Message(message_text="check A DOI does not change when the object moves."),
        )
    )
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.delegations[0].delegated_agent_id == "fact.checker"


def test_a_mention_picks_the_agent_and_no_match_abstains() -> None:
    rules = load_rules()
    found = route("@hello.world Grace Hopper", rules)
    assert not isinstance(found, str)
    assert found.rule.agent_id == "hello.world"
    assert found.input_document["greeted_name"] == "Grace Hopper"
    found = route("@fact.checker is it true that DOIs persist?", rules)
    assert not isinstance(found, str) and found.input_document["text"] == "DOIs persist"
    assert isinstance(route("@nobody hi", rules), str)
    assert isinstance(route("what is the weather", rules), str)


@pytest.mark.requirement("DD-OUTCOME")
def test_an_unroutable_message_abstains_naming_what_it_can_route(runs_dir: Path) -> None:
    env = conductor(runs_dir).invoke(
        request("director.stub", Message(message_text="what is the weather"))
    )
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.OUTSIDE_AGENT_SCOPE
    assert "hello.world" in env.outcome.statement and env.delegations == []


def test_without_a_callback_it_abstains_rather_than_calling_agents_directly(
    runs_dir: Path,
) -> None:
    c = conductor(runs_dir)
    c.workbench_url = None
    env = c.invoke(request("director.stub", Message(message_text="hello Joe")))
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.CAPABILITY_NOT_IMPLEMENTED


def test_an_unregistered_target_fails_with_an_agent_error(runs_dir: Path) -> None:
    c = make_conductor(runs_dir, DirectorStub(), HelloWorld())  # no fact.checker
    env = c.invoke(request("director.stub", Message(message_text="check DOIs persist")))
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
