"""The orchestrator's own tools (`agent.py`), which delegate to no agent and run nothing:
`ask_questions` puts questions to the researcher, `name_project` names a project no person has
named, and `set_entry_point` records where the researcher joins the process flow. Each call is
read here, and answered with what was taken or why nothing was.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from dd_agent_orchestrator_model.provisional import fixed
from dd_agent_orchestrator_model.title import clean
from dd_sdk.contract.models import (
    CHOICE_OPTIONS_MAX,
    CHOICE_OPTIONS_MIN,
    NEW_PROJECT_TITLE_MAX,
    QUESTION_KEY_PATTERN,
    QUESTIONS_MAX,
    SHORT_TEXT_MAX,
    Question,
    QuestionKind,
)
from dd_sdk.model import ToolCall, ToolResult, ToolSpec
from dd_sdk.process_flow import ENTRIES

# The one tool that is not a delegation: it asks the researcher questions, and runs nothing.
QUESTIONS_TOOL = "ask_questions"
QUESTIONS_TOOL_DEFINITION = ToolSpec(
    name=QUESTIONS_TOOL,
    description=(
        "Ask the researcher one or more questions, shown to them as form fields one at a time and "
        "answered together in their next message. It runs nothing and ends your turn: call it "
        "alone, after the text of your reply. Ask several at once only when you need several "
        "facts before you can go on; use a choice question when the answer is one of a few known "
        "options, and a text question otherwise."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "minItems": 1,
                "maxItems": QUESTIONS_MAX,
                "description": "The questions in the order to ask them.",
                "items": {
                    "type": "object",
                    "properties": {
                        "question_key": {
                            "type": "string",
                            "pattern": QUESTION_KEY_PATTERN,
                            "description": "A short identifier, unique among these questions.",
                        },
                        "question_prompt": {
                            "type": "string",
                            "description": "The question, in one line.",
                        },
                        "question_kind": {
                            "type": "string",
                            "enum": [k.value for k in QuestionKind],
                            "description": (
                                "choice: pick from options; short_text: a name, a number or a "
                                f"date in their own words, at most {SHORT_TEXT_MAX} characters; "
                                "long_text: anything longer in their own words, such as a "
                                "policy, a description or a method. When unsure, use long_text."
                            ),
                        },
                        "question_help": {
                            "type": "string",
                            "description": "Optional: a sentence that helps them answer.",
                        },
                        "question_options": {
                            "type": "array",
                            "minItems": CHOICE_OPTIONS_MIN,
                            "maxItems": CHOICE_OPTIONS_MAX,
                            "description": (
                                "Choice questions only: the options in the order to show them; "
                                "values unique."
                            ),
                            "items": {
                                "type": "object",
                                "properties": {
                                    "option_value": {
                                        "type": "string",
                                        "description": "A short identifier.",
                                    },
                                    "option_label": {
                                        "type": "string",
                                        "description": "What the researcher reads.",
                                    },
                                    "option_help": {
                                        "type": "string",
                                        "description": (
                                            "Optional: one sentence telling this option apart; "
                                            "for an option an agent recommended, the agent's "
                                            "reason for it."
                                        ),
                                    },
                                },
                                "required": ["option_value", "option_label"],
                                "additionalProperties": False,
                            },
                        },
                        "question_multiple": {
                            "type": "boolean",
                            "description": "Choice questions only: true if several may be chosen.",
                        },
                        "question_other": {
                            "type": "boolean",
                            "description": (
                                "Choice questions only: true if the researcher may answer in "
                                "their own words instead."
                            ),
                        },
                    },
                    "required": ["question_key", "question_prompt", "question_kind"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["questions"],
        "additionalProperties": False,
    },
)


# The tool that names a project no person has named: it runs nothing, and the turn goes on.
NAME_TOOL = "name_project"
NAME_TOOL_DEFINITION = ToolSpec(
    name=NAME_TOOL,
    description=(
        "Name the researcher's project, so they can tell it apart from their others. Call it "
        "once you know what the research or the dataset is, from what the researcher has said "
        "or the project holds, not from a greeting or a general question. Give a short noun "
        "phrase saying what the data are, such as 'River sediment cores, Humber estuary 2025'. "
        "Rename a project you named only when what you have learned shows the name is wrong. "
        "It runs nothing and your turn goes on; the researcher can rename the project."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "maxLength": NEW_PROJECT_TITLE_MAX,
                "description": "The project's name, in one line, without quotes.",
            },
        },
        "required": ["name"],
        "additionalProperties": False,
    },
)


# The tool that records the entry point the model worked out from what the researcher said: it
# runs nothing, and the turn goes on.
ENTRY_TOOL = "set_entry_point"
ENTRY_TOOL_DEFINITION = ToolSpec(
    name=ENTRY_TOOL,
    description=(
        "Record where the researcher joins the process flow, so that their journey and the "
        "suggested next step match what you tell them. Call it as soon as you know, from what "
        "the researcher has said or from their answer to your question, in the same turn as you "
        "tell them; not from a guess. The entry points: "
        + "; ".join(f"{e.number}, {e.text} (starts at Phase {e.starts_at})" for e in ENTRIES)
        + ". It runs nothing and your turn goes on; the researcher can change it."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "entry": {
                "type": "integer",
                "enum": [e.number for e in ENTRIES],
                "description": "The entry point's number.",
            },
        },
        "required": ["entry"],
        "additionalProperties": False,
    },
)


def questions_of(calls: Sequence[ToolCall]) -> tuple[list[Question] | None, str | None]:
    """The questions asked by a turn whose only tool call is `ask_questions`, or why they are not
    asked: None and None when the turn does not call the tool."""
    if not any(call.name == QUESTIONS_TOOL for call in calls):
        return None, None
    if len(calls) > 1:
        return None, (
            "Not shown: ask questions alone, in your final message, once the agents you need "
            "have answered."
        )
    try:
        given = calls[0].input.get("questions")
        if not isinstance(given, list):
            raise ValueError("questions must be a list")
        if not 1 <= len(given) <= QUESTIONS_MAX:
            raise ValueError(f"ask between 1 and {QUESTIONS_MAX} questions")
        questions = [fixed(Question.model_validate(q)) for q in given]
        if len({q.question_key for q in questions}) != len(questions):
            raise ValueError("each question has a key of its own")
        return questions, None
    except ValueError as exc:  # pydantic's ValidationError
        errors = getattr(exc, "errors", None)
        reasons = "; ".join(str(e["msg"]) for e in errors()) if callable(errors) else str(exc)
        return (
            None,
            f"Not shown: these are not valid questions ({reasons}). Fix them or ask in prose.",
        )


def name_of(call: ToolCall, *, offered: bool) -> tuple[str | None, ToolResult]:
    """The name a `name_project` call gives, tidied as a title is, and the tool result to send
    back: None and an error when the tool was not offered or the name is empty."""
    if not offered:
        return None, tool_result(call, "Not named: a person has named this project.", is_error=True)
    given = call.input.get("name")
    name = clean(given) if isinstance(given, str) else None
    if name is None:
        return None, tool_result(
            call, "Not named: give the name as one line of text.", is_error=True
        )
    return name, tool_result(
        call, f"Named {json.dumps(name)}. Carry on with your reply.", is_error=False
    )


def entry_of(call: ToolCall, *, offered: bool) -> tuple[int | None, ToolResult]:
    """The entry point a `set_entry_point` call records and the tool result to send back: None
    and an error when the tool was not offered or the entry point is not one of the flow's."""
    if not offered:
        return None, tool_result(
            call, "Not recorded: the researcher chose the entry point themselves.", is_error=True
        )
    given = call.input.get("entry")
    numbers = {e.number: e for e in ENTRIES}
    if isinstance(given, bool) or not isinstance(given, int) or given not in numbers:
        return None, tool_result(
            call, f"Not recorded: give one of the entry points {sorted(numbers)}.", is_error=True
        )
    found = numbers[given]
    return given, tool_result(
        call,
        f"Recorded entry point {given} ({found.text}), starting at Phase {found.starts_at}. "
        "Carry on with your reply; tell the researcher they can change it on their journey.",
        is_error=False,
    )


def tool_result(call: ToolCall, content: str, *, is_error: bool) -> ToolResult:
    """The result sent back for one tool call."""
    return ToolResult(call.id, content, is_error=is_error)
