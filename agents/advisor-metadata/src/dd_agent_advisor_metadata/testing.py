"""Doubles for this agent's tests: a model's reply in the shape its schema asks for."""

from __future__ import annotations

import json
from collections.abc import Mapping


def suggestion_reply(answers: Mapping[str, str | None]) -> str:
    """A `SuggestionReply` as a model sends it: a suggested value by question identifier."""
    return json.dumps(
        {"suggestions": [{"question_id": q, "answer": a} for q, a in answers.items()]}
    )
