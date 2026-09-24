"""Conversations read back from the invocation store (ADR-0012): turn order, delegated children,
history for the next turn, and version changes between turns."""

from __future__ import annotations

from pathlib import Path

import pytest

from dd_sdk.agent import AgentResult, RunContext
from dd_sdk.contract.models import (
    Frozen,
    GroundingMode,
    InvocationRequest,
    Message,
    new_invocation_id,
)
from workbench import conversations
from workbench.testing import (
    ScriptedAgent,
    make_conductor,
    message,
    record,
    reply_over,
    request,
    review_of_input,
)


def relay(req: InvocationRequest, ctx: RunContext) -> AgentResult:
    assert ctx.delegate is not None
    return reply_over(ctx, ctx.delegate("fake.none", record()))


def turn(agent_id: str, conversation_id: str, input: Frozen) -> InvocationRequest:
    return request(agent_id, input).model_copy(update={"conversation_id": conversation_id})


@pytest.mark.requirement("DD-CONVERSATION")
def test_turns_are_in_order_with_children_nested_and_history_built(tmp_path: Path) -> None:
    conductor = make_conductor(
        tmp_path,
        ScriptedAgent(GroundingMode.DELEGATION, relay),
        ScriptedAgent(GroundingMode.NONE, review_of_input),
    )
    conv = new_invocation_id()
    first = conductor.invoke(turn("fake.delegation", conv, message("review this")))
    second = conductor.invoke(turn("fake.delegation", conv, message("and again")))
    conductor.invoke(request("fake.none"))  # outside any conversation

    found = conversations.get_conversation(conductor.store, conv)
    assert found is not None
    assert [t["invocation_id"] for t in found["turns"]] == [
        first.invocation_id,
        second.invocation_id,
    ]
    assert [t["turn_index"] for t in found["turns"]] == [0, 1]
    [child] = found["turns"][0]["children"]
    assert child["invocation_id"] == first.delegations[0].delegated_invocation_id
    assert found["turns"][0]["input"]["message_text"] == "review this"
    assert found["inputs"][child["invocation_id"]]["schema_class"] == "MetadataRecord"
    assert found["version_changes"] == []

    history = found["history"]
    assert [h["role"] for h in history] == ["user", "agent", "user", "agent"]
    assert history[0]["turn_text"] == "review this"
    assert history[1]["turn_agent_id"] == "fake.delegation"
    assert history[1]["turn_agent_version"] == "0"
    assert history[1]["turn_invocation_id"] == first.invocation_id
    assert history[1]["turn_text"].startswith("fake.none:")  # the Reply text
    # The history is valid Message.history, so the next turn can carry it.
    Message(message_text="next", history=history)

    [summary] = conversations.list_conversations(conductor.store)
    assert summary["conversation_id"] == conv
    assert summary["turns"] == 2
    assert summary["agent_id"] == "fake.delegation"
    assert conversations.get_conversation(conductor.store, new_invocation_id()) is None


@pytest.mark.requirement("DD-CONVERSATION")
def test_a_version_change_between_turns_is_reported(tmp_path: Path) -> None:
    conv = new_invocation_id()
    for version in ("1", "1", "2"):
        conductor = make_conductor(
            tmp_path, ScriptedAgent(GroundingMode.NONE, review_of_input, version=version)
        )
        conductor.invoke(turn("fake.none", conv, record()))
    found = conversations.get_conversation(conductor.store, conv)
    assert found is not None
    assert found["version_changes"] == [
        {"turn_index": 2, "agent_id": "fake.none", "from": "1", "to": "2"}
    ]
    # A structured turn shows in the history as its JSON.
    assert found["history"][0]["turn_text"].startswith('{"creators":')
