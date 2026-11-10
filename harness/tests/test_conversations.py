"""Conversations read back from the invocation store (docs/specs/orchestration.md): turn order,
delegated children, history for the next turn, and version changes between turns."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from dd_harness import conversations
from dd_harness.testing import (
    TEST_PRINCIPAL,
    ScriptedAgent,
    make_conductor,
    message,
    record,
    reply_over,
    request,
    review_of_input,
)
from dd_sdk.agent import AgentResult, RunContext
from dd_sdk.contract.models import (
    ChoiceOption,
    Frozen,
    GroundingMode,
    InvocationRequest,
    Message,
    Question,
    QuestionAnswer,
    QuestionKind,
    Reply,
    ReplyAnswers,
    new_invocation_id,
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
    first = conductor.invoke(
        turn("fake.delegation", conv, message("review this")), acting_for=TEST_PRINCIPAL
    )
    second = conductor.invoke(
        turn("fake.delegation", conv, message("and again")), acting_for=TEST_PRINCIPAL
    )
    conductor.invoke(request("fake.none"), acting_for=TEST_PRINCIPAL)  # outside any conversation

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
    assert found["inputs"][child["invocation_id"]]["schema_class"] == "ProbeRecord"
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

    [summary] = conversations.list_conversations(conductor.store, limit=50).items
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
        conductor.invoke(turn("fake.none", conv, record()), acting_for=TEST_PRINCIPAL)
    found = conversations.get_conversation(conductor.store, conv)
    assert found is not None
    assert found["version_changes"] == [
        {"turn_index": 2, "agent_id": "fake.none", "from": "1", "to": "2"}
    ]
    # A structured turn shows in the history as its JSON.
    assert found["history"][0]["turn_text"].startswith('{"creators":')


def titled_reply(req: InvocationRequest, ctx: RunContext) -> AgentResult:
    """A first turn's Reply with a model-written title; later turns carry none."""
    result = relay(req, ctx)
    assert isinstance(result.payload, Reply) and isinstance(req.input, Message)
    title = None if req.input.history else "Soil survey deposit"
    payload = result.payload.model_copy(update={"conversation_title": title})
    return dataclasses.replace(result, payload=payload)


@pytest.mark.requirement("DD-CONVERSATION")
def test_a_conversation_is_titled_by_its_first_turns_reply(tmp_path: Path) -> None:
    conductor = make_conductor(
        tmp_path,
        ScriptedAgent(GroundingMode.DELEGATION, titled_reply),
        ScriptedAgent(GroundingMode.NONE, review_of_input),
    )
    conv = new_invocation_id()
    first = conductor.invoke(
        turn("fake.delegation", conv, message("I want to deposit my soil survey")),
        acting_for=TEST_PRINCIPAL,
    )
    assert first.payload_as(Reply).conversation_title == "Soil survey deposit"
    found = conversations.get_conversation(conductor.store, conv)
    assert found is not None
    later = Message(message_text="And the licence?", history=found["history"])
    conductor.invoke(turn("fake.delegation", conv, later), acting_for=TEST_PRINCIPAL)

    [summary] = conversations.list_conversations(conductor.store, limit=50).items
    assert summary["turns"] == 2
    assert summary["title"] == "Soil survey deposit"
    assert summary["title_source"] == "model"


@pytest.mark.requirement("DD-CONVERSATION")
def test_without_a_model_title_a_conversation_is_named_by_its_first_message(
    tmp_path: Path,
) -> None:
    """As with orchestrator.stub, which writes no title."""
    conductor = make_conductor(
        tmp_path,
        ScriptedAgent(GroundingMode.DELEGATION, relay),
        ScriptedAgent(GroundingMode.NONE, review_of_input),
    )
    short, long = new_invocation_id(), new_invocation_id()
    conductor.invoke(
        turn("fake.delegation", short, message("Which  licence\nshould I use?")),
        acting_for=TEST_PRINCIPAL,
    )
    text = "I have interview transcripts from a study of farmers and want to share them openly"
    conductor.invoke(turn("fake.delegation", long, message(text)), acting_for=TEST_PRINCIPAL)

    listed = conversations.list_conversations(conductor.store, limit=50).items
    found = {s["conversation_id"]: s for s in listed}
    assert found[short]["title"] == "Which licence should I use?"
    assert found[short]["title_source"] == "message"
    title = found[long]["title"]
    assert title.endswith("…") and text.startswith(title.removesuffix("…"))
    assert len(title) <= conversations.MESSAGE_TITLE_MAX
    assert found[long]["title_source"] == "message"


QUESTION = Question(
    question_key="repository",
    question_prompt="Which repository will you deposit in?",
    question_kind=QuestionKind.CHOICE,
    question_options=[
        ChoiceOption(option_value="zenodo", option_label="Zenodo"),
        ChoiceOption(option_value="figshare", option_label="Figshare"),
    ],
    question_other=True,
)
TITLE = Question(
    question_key="title",
    question_prompt="What is the dataset called?",
    question_kind=QuestionKind.SHORT_TEXT,
)
METHOD = Question(
    question_key="method",
    question_prompt="How were the data collected?",
    question_kind=QuestionKind.LONG_TEXT,
)


def asking(req: InvocationRequest, ctx: RunContext) -> AgentResult:
    """A reply that asks QUESTION, TITLE and METHOD on the first turn only."""
    result = relay(req, ctx)
    assert isinstance(result.payload, Reply) and isinstance(req.input, Message)
    questions = None if req.input.history else [QUESTION, TITLE, METHOD]
    return dataclasses.replace(
        result, payload=result.payload.model_copy(update={"reply_questions": questions})
    )


def _answers(invocation: str, *given: dict[str, object]) -> ReplyAnswers:
    return ReplyAnswers(
        answer_to=invocation, given_answers=[QuestionAnswer.model_validate(g) for g in given]
    )


@pytest.mark.requirement("DD-CONVERSATION")
def test_questions_show_in_history_and_answers_are_checked_against_them(
    tmp_path: Path,
) -> None:
    conductor = make_conductor(
        tmp_path,
        ScriptedAgent(GroundingMode.DELEGATION, asking),
        ScriptedAgent(GroundingMode.NONE, review_of_input),
    )
    conv = new_invocation_id()
    first = conductor.invoke(
        turn("fake.delegation", conv, message("I want to deposit")), acting_for=TEST_PRINCIPAL
    )
    found = conversations.get_conversation(conductor.store, conv)
    assert found is not None
    asked = found["history"][1]["turn_text"]
    assert (
        "Which repository will you deposit in?\n- Zenodo\n- Figshare\n- or something else" in asked
    )
    assert TITLE.question_prompt in asked and METHOD.question_prompt in asked

    def problem(*given: dict[str, object]) -> str | None:
        return conversations.answer_problem(found, _answers(first.invocation_id, *given))

    def choice(**kw: object) -> dict[str, object]:
        return {"answered_key": "repository", **kw}

    assert problem(choice(answer_values=["zenodo"])) is None
    assert problem(choice(answer_words="Our institutional repository")) is None
    assert "dryad" in (problem(choice(answer_values=["dryad"])) or "")
    assert "one answer" in (problem(choice(answer_values=["zenodo", "figshare"])) or "")
    assert "one answer" in (problem(choice(answer_values=["zenodo"], answer_words="ours")) or "")
    assert "nothing" in (problem(choice()) or "")
    assert "empty" in (problem(choice(answer_words="  ")) or "")
    # Text questions take words alone, within their kind's length; any question may be skipped.
    assert problem({"answered_key": "title", "answer_words": "Bird counts"}) is None
    assert problem({"answered_key": "method", "answer_words": "By survey.\nTwice."}) is None
    assert problem({"answered_key": "title", "answer_values": ["zenodo"]}) is not None
    assert problem({"answered_key": "title"}) is not None
    assert problem({"answered_key": "title", "answer_words": "a\nb"}) is not None
    assert problem({"answered_key": "title", "answer_words": "x" * 201}) is not None
    assert problem({"answered_key": "unasked", "answer_words": "x"}) is not None
    stale = _answers(new_invocation_id(), choice(answer_values=["zenodo"]))
    assert "latest turn" in (conversations.answer_problem(found, stale) or "")
    assert conversations.answer_problem(None, stale) is not None

    # The next turn answers; its reply asks nothing, so nothing can answer it.
    answers = _answers(
        first.invocation_id,
        choice(answer_values=["zenodo"]),
        {"answered_key": "method", "answer_words": "By survey."},
    )
    second = conductor.invoke(
        turn(
            "fake.delegation",
            conv,
            Message(message_text="Zenodo", history=found["history"], reply_answers=answers),
        ),
        acting_for=TEST_PRINCIPAL,
    )
    found = conversations.get_conversation(conductor.store, conv)
    assert found is not None
    given = found["turns"][1]["input"]["reply_answers"]["given_answers"]
    assert [g["answered_key"] for g in given] == ["repository", "method"]
    again = _answers(second.invocation_id, choice(answer_values=["zenodo"]))
    assert "no question" in (conversations.answer_problem(found, again) or "")


def test_a_question_that_takes_several_answers_accepts_them() -> None:
    several = QUESTION.model_copy(update={"question_multiple": True, "question_other": False})
    invocation = new_invocation_id()
    found = {
        "turns": [
            {
                "invocation_id": invocation,
                "envelope": {
                    "payload": {
                        "schema_class": "Reply",
                        "reply_questions": [several.model_dump(mode="json")],
                    }
                },
            }
        ]
    }

    def problem(**kw: object) -> str | None:
        given = {"answered_key": "repository", **kw}
        return conversations.answer_problem(found, _answers(invocation, given))

    assert problem(answer_values=["zenodo", "figshare"]) is None
    assert "more than once" in (problem(answer_values=["zenodo", "zenodo"]) or "")
    assert "only its options" in (problem(answer_words="ours") or "")
