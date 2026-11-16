"""Doubles for this agent's tests: a model's reply in the shape its schema asks for."""

from __future__ import annotations

import json
from collections.abc import Sequence


def rights_reply(
    reuse: Sequence[str] = (), licences: Sequence[str] = (), questions: Sequence[str] = ()
) -> str:
    """A `RightsReply` as a model sends it."""
    return json.dumps(
        {"reuse": list(reuse), "licences": list(licences), "questions": list(questions)}
    )
