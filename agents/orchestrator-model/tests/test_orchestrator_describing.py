"""A project's data description: the model may propose one from what the researcher said, with
`propose_data_description`, which the conductor records as a proposal for a person to confirm;
once confirmed, the next conversation in the project is given it (describing.py, #160)."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_orchestrator import ScriptedModel, call, say
from test_orchestrator_naming import in_project, tool_names, turn

from dd_agent_orchestrator_model.agent import DESCRIBE_TOOL, ModelOrchestrator
from dd_harness.projects.facts import FactVerdict
from dd_harness.testing import TEST_PRINCIPAL
from dd_sdk.agent import Derived
from dd_sdk.contract.facts import PLAN_SUBJECT, FactKind
from dd_sdk.contract.models import Derivation, OutcomeStatus, Reply

pytestmark = pytest.mark.requirement("DD-CONVERSATION")

SAID = "We record 40 interviews as audio, about 20 GB, and transcribe them to text."
DESCRIBED = {
    "data_collected": "Interview recordings and their transcripts.",
    "data_collection_method": "Recorded interviews, transcribed.",
    "data_volume": "About 20 GB.",
    "quote": SAID,
}


def test_a_description_is_proposed_for_a_person_and_given_to_later_runs(tmp_path: Path) -> None:
    model = ScriptedModel(
        [call((DESCRIBE_TOOL, DESCRIBED)), say("Noted. Confirm it on the project page."), say("Hi")]
    )
    conductor, project, conversation_id = in_project(tmp_path, model)
    env = turn(conductor, conversation_id, SAID)

    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert DESCRIBE_TOOL in tool_names(model.sent[0])
    [result] = model.sent[1]["messages"][-1]["results"]
    assert result["is_error"] is False
    [proposed] = env.payload_as(Reply).proposed_facts or []
    assert (proposed.fact_kind, proposed.fact_subject) == (FactKind.DATA_DESCRIPTION, PLAN_SUBJECT)
    assert proposed.proposed_because == SAID
    assert ModelOrchestrator.spec.derivations["proposed_facts"] == Derived(Derivation.MODEL)

    # A proposal is not a fact: no agent is given it until a person decides it.
    store = conductor.projects
    assert store is not None
    [open_proposal] = store.proposals(project)
    assert store.decisions(project) is None
    store.decide_fact(
        project,
        FactVerdict.CONFIRMED,
        proposal=open_proposal["proposal"],
        acted_for=TEST_PRINCIPAL,
        caused_by="test",
    )
    later = store.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="test")
    turn(conductor, later)
    assert proposed.data_collected in model.sent[2]["messages"][-1]["content"]


@pytest.mark.parametrize(
    "given", [{"quote": SAID}, {"data_collected": "  ", "quote": SAID}], ids=["none", "blank"]
)
def test_a_description_that_says_no_data_is_refused(tmp_path: Path, given: dict[str, str]) -> None:
    model = ScriptedModel([call((DESCRIBE_TOOL, given)), say("Hello.")])
    conductor, project, conversation_id = in_project(tmp_path, model)
    env = turn(conductor, conversation_id)
    [result] = model.sent[1]["messages"][-1]["results"]
    assert result["is_error"] is True
    assert env.payload_as(Reply).proposed_facts is None
    assert conductor.projects is not None and conductor.projects.proposals(project) == []


def test_outside_a_project_there_is_nothing_to_describe(tmp_path: Path) -> None:
    model = ScriptedModel([say("Hello.")])
    conductor, _, _ = in_project(tmp_path, model)
    turn(conductor, None)
    assert DESCRIBE_TOOL not in tool_names(model.sent[0])
