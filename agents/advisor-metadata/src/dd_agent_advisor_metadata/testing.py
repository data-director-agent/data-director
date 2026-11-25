"""Doubles for this agent's tests: a model's reply in the shape its schema asks for, and what a
model request offers."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from dd_sdk.model import ModelRequest

_FACTS = "\n\nFacts:\n"


def suggestion_reply(answers: Mapping[str, str | None]) -> str:
    """A `SuggestionReply` as a model sends it: a suggested value by question identifier."""
    return json.dumps(
        {"suggestions": [{"question_id": q, "answer": a} for q, a in answers.items()]}
    )


def _message(sent: ModelRequest) -> str:
    return str(sent.messages[0]["content"])  # type: ignore[index]


def asked_in(sent: ModelRequest) -> list[dict[str, Any]]:
    """The questions a model request offers, from its user message."""
    return list(json.loads(_message(sent).split(_FACTS)[0].split(":\n", 1)[1]))


def facts_in(sent: ModelRequest) -> dict[str, Any]:
    """The facts a model request gives, from its user message."""
    facts: dict[str, Any] = json.loads(_message(sent).split(_FACTS, 1)[1])
    return facts
