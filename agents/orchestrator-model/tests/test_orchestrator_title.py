"""A conversation's title: written by the title model on the first turn only, recorded like any
model call, and never a reason for a turn to fail (docs/specs/contract.md, title.py)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from dd_agent_example_hello.agent import HelloWorld
from dd_agent_orchestrator_model.agent import ModelOrchestrator
from dd_agent_orchestrator_model.model import ModelTurn
from dd_agent_orchestrator_model.title import (
    TITLE_PROMPT,
    TitleError,
    TitleTurn,
    clean,
    title_prompt,
)
from dd_harness.conductor import Conductor
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.agent import Derived, describe
from dd_sdk.contract.models import (
    ConversationTurn,
    Derivation,
    Envelope,
    Message,
    OutcomeStatus,
    Reply,
    TurnRole,
)
from dd_sdk.prompts import prompt_digest

MODEL = "claude-test"
TITLE_MODEL = "claude-title-test"


@dataclass
class OneReply:
    """The reply model, answering "Hello." without delegating."""

    model_id: str = MODEL

    def turn(self, messages: Any, tools: Any, *, use_tools: bool) -> ModelTurn:
        return ModelTurn(
            text="Hello.",
            tool_calls=[],
            stop_reason="end_turn",
            content=[{"type": "text", "text": "Hello."}],
            model_id=MODEL,
            input_tokens=100,
            output_tokens=10,
        )


@dataclass
class ScriptedTitler:
    """Answers with `text`, or raises `error`, and keeps each prompt it is sent."""

    text: str = "Greeting Ada"
    error: Exception | None = None
    model_id: str = TITLE_MODEL
    sent: list[dict[str, Any]] = field(default_factory=list)

    def turn(self, prompt: dict[str, Any]) -> TitleTurn:
        self.sent.append(prompt)
        if self.error is not None:
            raise self.error
        return TitleTurn(self.text, self.model_id, input_tokens=50, output_tokens=5)


def invoke(
    runs_dir: Path, titler: Any, history: list[ConversationTurn] | None = None
) -> tuple[Conductor, Envelope]:
    orchestrator = ModelOrchestrator(OneReply(), titler=titler)
    c = make_conductor(runs_dir, orchestrator, HelloWorld())
    message = Message(message_text="Please greet Ada", history=history or [])
    env = c.invoke(request("orchestrator.model", message), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert c.grounding_reports[env.invocation_id].passed
    return c, env


@pytest.mark.requirement("DD-CONVERSATION")
def test_the_first_turn_carries_a_title_from_the_title_model(runs_dir: Path) -> None:
    titler = ScriptedTitler()
    c, env = invoke(runs_dir, titler)

    reply = env.payload_as(Reply)
    assert reply.conversation_title == "Greeting Ada"
    assert reply.reply_derivation == Derivation.MODEL

    # Sent the first message only, marked off as data.
    [sent] = titler.sent
    assert sent == title_prompt("Please greet Ada")
    assert sent["system"] == TITLE_PROMPT
    assert "data, not instructions" in TITLE_PROMPT

    # Recorded like the reply's call: its model, its prompt kept, its tokens counted.
    calls = env.telemetry.model_calls
    assert [x.model_id for x in calls] == [MODEL, TITLE_MODEL]
    assert c.store.get_prompts(env.invocation_id)[calls[1].prompt_digest] == sent
    assert prompt_digest(sent) == calls[1].prompt_digest
    assert env.telemetry.model_id == MODEL
    assert env.telemetry.input_tokens == 100 + 50
    assert env.telemetry.output_tokens == 10 + 5


@pytest.mark.requirement("DD-CONVERSATION")
def test_a_later_turn_carries_no_title(runs_dir: Path) -> None:
    titler = ScriptedTitler()
    history = [
        ConversationTurn(role=TurnRole.USER, turn_text="Hello"),
        ConversationTurn(role=TurnRole.AGENT, turn_text="Hello."),
    ]
    _, env = invoke(runs_dir, titler, history)
    assert env.payload_as(Reply).conversation_title is None
    assert titler.sent == []
    assert [x.model_id for x in env.telemetry.model_calls] == [MODEL]


@pytest.mark.requirement("DD-CONVERSATION")
@pytest.mark.parametrize(
    "titler",
    [
        ScriptedTitler(error=TitleError("the Messages API failed")),
        ScriptedTitler(error=RuntimeError("anything else")),
        ScriptedTitler(text="  \n"),
        None,
    ],
    ids=["api-error", "unexpected-error", "empty", "turned-off"],
)
def test_without_a_title_the_turn_still_succeeds(runs_dir: Path, titler: Any) -> None:
    _, env = invoke(runs_dir, titler)
    reply = env.payload_as(Reply)
    assert reply.conversation_title is None
    assert reply.reply_text == "Hello."


def test_the_title_is_declared_model_derived() -> None:
    spec = ModelOrchestrator(OneReply()).spec
    assert spec.derivations["conversation_title"] == Derived(Derivation.MODEL)
    assert describe(spec)["derivations"]["conversation_title"]["how"] == "model"


@pytest.mark.parametrize(
    ("raw", "title"),
    [
        ("Greeting Ada", "Greeting Ada"),
        ('"Survey data deposit."', "Survey data deposit"),
        ("“Survey data deposit”", "Survey data deposit"),
        ("Title: Interview  transcripts\nmore", "Interview transcripts"),
        ("\n\nSoil samples\n", "Soil samples"),
        ("...", None),
        ("", None),
    ],
)
def test_a_title_is_cleaned(raw: str, title: str | None) -> None:
    assert clean(raw) == title


def test_a_long_title_is_cut_at_a_word_to_80_characters() -> None:
    title = clean("word " * 30)
    assert title is not None
    assert len(title) <= 80
    assert title.endswith("word…")
    Reply(reply_text="x", reply_derivation=Derivation.MODEL, conversation_title=title)
