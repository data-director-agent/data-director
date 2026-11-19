"""Doubles for this agent's tests: a model's reply in the shape its schema asks for."""

from __future__ import annotations

import json
from collections.abc import Sequence


def writer_reply(recommendations: Sequence[tuple[str, str]] = ()) -> str:
    """A `WriterReply` as a model sends it: recommendations as (check, recommendation)."""
    return json.dumps(
        {"recommendations": [{"check": c, "recommendation": r} for c, r in recommendations]}
    )
