"""Conversations, derived from the run storage (docs/specs/orchestration.md).

A conversation is the set of top-level invocations sharing a `conversation_id`. There is no
conversation store: each turn is an ordinary invocation, so everything here is read back from the
stored envelopes and requests (`RunStorage`, docs/specs/storage.md). Turn order is the order the
envelopes were stored, which is the order the conductor finished the turns in. A child invocation
(one with `parent_invocation_id`) is not a turn; it is listed under the turn that delegated it.

`history` is the conversation as a `Message.history` list, so a caller can send the next turn
without rebuilding it. `version_changes` marks where an agent's version differs from the version
that agent had earlier in the same conversation, which is what a developer needs to see when an
agent is rebuilt mid-conversation.

A summary's `title` is derived like everything else: the first turn's
`Reply.conversation_title`, which a model-backed orchestrator writes (docs/specs/contract.md),
with `title_source` `model`; otherwise the start of the first turn's message, with `title_source`
`message`. The harness calls no model to make one.

A reply may ask a series of questions (`Reply.reply_questions`): choices, or answers in the
researcher's own words. `history` writes the questions after the reply's text, so a conversational
agent sees on a later turn what it asked; `answer_problem` is how the caller checks a researcher's
`ReplyAnswers` against those questions before sending the turn.

The run storage lists conversations a page at a time, for the readers allowed to see them
(`RunStorage.list_conversations`, docs/specs/storage.md, "Listing"); this module adds each one's
title, reading the first turn of each conversation on the page.
"""

from __future__ import annotations

import json
from typing import Any

from dd_harness.answers import question_answer_problem
from dd_harness.listing import Page, Readable
from dd_harness.storage import RunStorage
from dd_sdk.contract.models import (
    ConversationTurn,
    Question,
    QuestionKind,
    ReplyAnswers,
    TurnRole,
    to_document,
)

# How much of the first message names a conversation that has no model-written title.
MESSAGE_TITLE_MAX = 60
ELLIPSIS = "…"


def list_conversations(
    store: RunStorage,
    *,
    readable: Readable | None = None,
    limit: int,
    before: str | None = None,
) -> Page:
    """A page of conversation summaries, most recently active first, each with its title; with
    `readable`, only the conversations whose first turn it includes."""
    page = store.list_conversations(readable=readable, limit=limit, before=before)
    items = []
    for summary in page.items:
        first_turn = store.get(summary["first_invocation_id"])
        title = title_of(store, first_turn) if first_turn else untitled(summary)
        items.append({**summary, **title})
    return Page(items, page.next)


def title_of(store: RunStorage, first_turn: dict[str, Any]) -> dict[str, str]:
    """A conversation's `title` and `title_source`, from its first turn's envelope."""
    payload = first_turn.get("payload") or {}
    if payload.get("schema_class") == "Reply" and payload.get("conversation_title"):
        return {"title": str(payload["conversation_title"]), "title_source": "model"}
    request = store.get_request(first_turn["invocation_id"]) or {}
    document = request.get("input") or {}
    if document.get("schema_class") == "Message":
        text = str(document.get("message_text", ""))
    else:
        text = str(document.get("schema_class", ""))
    return {"title": shorten(text) or first_turn["agent_id"], "title_source": "message"}


def untitled(summary: dict[str, Any]) -> dict[str, str]:
    """The title of a conversation whose first turn cannot be read: its agent."""
    return {"title": summary["agent_id"], "title_source": "message"}


def shorten(text: str, limit: int = MESSAGE_TITLE_MAX) -> str:
    """`text` on one line, cut at a word to at most `limit` characters."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[: limit - len(ELLIPSIS)]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:.-") + ELLIPSIS


def get_conversation(store: RunStorage, conversation_id: str) -> dict[str, Any] | None:
    """Every turn of one conversation, with its children, the inputs of both, version changes and
    history.

    None if no invocation carries `conversation_id`.
    """
    top: list[dict[str, Any]] = []
    children: dict[str, list[dict[str, Any]]] = {}
    for envelope in store.iter_envelopes(conversation_id=conversation_id):
        parent = envelope.get("parent_invocation_id")
        if parent:
            children.setdefault(parent, []).append(envelope)
        else:
            top.append(envelope)
    if not top and not children:
        return None

    turns: list[dict[str, Any]] = []
    for index, envelope in enumerate(top):
        request = store.get_request(envelope["invocation_id"]) or {}
        turns.append(
            {
                "turn_index": index,
                "invocation_id": envelope["invocation_id"],
                "agent_id": envelope["agent_id"],
                "agent_version": envelope["agent_version"],
                "status": envelope["outcome"]["status"],
                "completed_at": envelope["completed_at"],
                "input": request.get("input"),
                "envelope": envelope,
                "children": children.get(envelope["invocation_id"], []),
            }
        )
    # Every stored input, the delegated children's too, so a reader can inspect any of them.
    inputs: dict[str, Any] = {}
    for envelope in [*top, *(c for cs in children.values() for c in cs)]:
        stored = store.get_request(envelope["invocation_id"])
        if stored is not None:
            inputs[envelope["invocation_id"]] = stored.get("input")
    return {
        "conversation_id": conversation_id,
        "project_id": next((t["envelope"].get("project_id") for t in turns), None),
        "turns": turns,
        "inputs": inputs,
        "version_changes": version_changes(turns),
        "history": [to_document(t) for t in history(turns)],
    }


def version_changes(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Where an agent's version differs from its version earlier in the conversation.

    Children count as well as turns, so an orchestrator's sub-agent being rebuilt is reported.
    """
    seen: dict[str, str] = {}
    changes: list[dict[str, Any]] = []
    for turn in turns:
        for envelope in [*turn["children"], turn["envelope"]]:
            agent_id, version = envelope["agent_id"], envelope["agent_version"]
            before = seen.get(agent_id)
            if before is not None and before != version:
                changes.append(
                    {
                        "turn_index": turn["turn_index"],
                        "agent_id": agent_id,
                        "from": before,
                        "to": version,
                    }
                )
            seen[agent_id] = version
    return changes


def history(turns: list[dict[str, Any]]) -> list[ConversationTurn]:
    """The conversation so far as `Message.history`: each turn's input, then the agent's reply.

    A `Message` turn contributes its text; any other input contributes its JSON, so a structured
    turn is still visible to a conversational agent. An agent turn is the reply text if the
    payload is a `Reply`, otherwise the outcome statement.
    """
    out: list[ConversationTurn] = []
    for turn in turns:
        document = turn["input"] or {}
        if document.get("schema_class") == "Message":
            text = str(document.get("message_text", ""))
        else:
            text = json.dumps(document, sort_keys=True, separators=(",", ":"))
        out.append(ConversationTurn(role=TurnRole.USER, turn_text=text))
        envelope = turn["envelope"]
        payload = envelope.get("payload") or {}
        reply = payload.get("reply_text") if payload.get("schema_class") == "Reply" else None
        text = str(reply or envelope["outcome"]["statement"])
        questions = reply_questions(envelope)
        if questions:
            text = f"{text}\n\n{questions_text(questions)}"
        out.append(
            ConversationTurn(
                role=TurnRole.AGENT,
                turn_text=text,
                turn_agent_id=envelope["agent_id"],
                turn_agent_version=envelope["agent_version"],
                turn_invocation_id=envelope["invocation_id"],
            )
        )
    return out


def reply_questions(envelope: dict[str, Any]) -> list[Question]:
    """The questions a turn's `Reply` asks, in order; empty if it asks none."""
    payload = envelope.get("payload") or {}
    if payload.get("schema_class") != "Reply":
        return []
    return [Question.model_validate(q) for q in payload.get("reply_questions") or []]


_KIND_TEXT = {
    QuestionKind.SHORT_TEXT: "(To be answered in a line of the researcher's own words.)",
    QuestionKind.LONG_TEXT: "(To be answered in the researcher's own words, at any length.)",
}


def questions_text(questions: list[Question]) -> str:
    """The questions a reply asked as plain text, as history presents them to an agent."""
    blocks = [_question_text(q) for q in questions]
    if len(blocks) == 1:
        return blocks[0]
    lead = f"(The researcher was asked these {len(blocks)} questions, one at a time.)"
    return "\n\n".join([lead, *(f"{n}. {b}" for n, b in enumerate(blocks, start=1))])


def _question_text(question: Question) -> str:
    lines = [question.question_prompt]
    if question.question_kind is not QuestionKind.CHOICE:
        return "\n".join([*lines, _KIND_TEXT[question.question_kind]])
    lines += [f"- {o.option_label}" for o in question.question_options or []]
    if question.question_other:
        lines.append("- or something else, in the researcher's own words")
    choose = "one or more" if question.question_multiple else "one"
    return "\n".join([*lines, f"(The researcher was offered these to choose {choose}.)"])


def answer_problem(conversation: dict[str, Any] | None, answers: ReplyAnswers) -> str | None:
    """Why `answers` cannot be sent as the next turn of `conversation`, or None if they can.

    The answers name the latest turn, whose reply asked questions, and each answers one of those
    questions; a question may be skipped. A choice answer's values are options of its question,
    at most one unless several may be chosen, with words in place of an option only where the
    question allows it; a text answer is words alone, within its kind's length; and every answer
    chooses or says something.
    """
    turns = (conversation or {}).get("turns") or []
    if not turns or turns[-1]["invocation_id"] != answers.answer_to:
        return "the answers do not name the latest turn of the conversation"
    asked = {q.question_key: q for q in reply_questions(turns[-1]["envelope"])}
    if not asked:
        return "the latest turn asked no question"
    for answer in answers.given_answers:
        question = asked.get(answer.answered_key)
        if question is None:
            return f"not a question the latest turn asked: {answer.answered_key}"
        if problem := question_answer_problem(question, answer):
            return f"{answer.answered_key}: {problem}"
    return None
