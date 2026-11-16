"""Doubles for this agent's tests: a model's reply in the shape its schema asks for."""

from __future__ import annotations

import json
from collections.abc import Mapping

from dd_agent_advisor_documentation.prose import OVERVIEW


def prose_reply(paragraphs: Mapping[str, str | None]) -> str:
    """A `ProseReply` as a model sends it: the overview under `overview`, the rest by heading."""
    return json.dumps(
        {
            "overview": paragraphs.get(OVERVIEW),
            "sections": [
                {"section": heading, "paragraph": paragraph}
                for heading, paragraph in paragraphs.items()
                if heading != OVERVIEW
            ],
        }
    )


def suggestion_reply(answers: Mapping[str, str | None]) -> str:
    """A `SuggestionReply` as a model sends it: a suggestion by question identifier."""
    return json.dumps(
        {"suggestions": [{"question_id": q, "answer": a} for q, a in answers.items()]}
    )
