"""Doubles for this agent's tests: a model's reply in the shape its schema asks for."""

from __future__ import annotations

import json
from collections.abc import Sequence


def match_reply(
    pairings: Sequence[tuple[str, str, str | None]] = (),
    equivalences: Sequence[tuple[str, str, str, str | None]] = (),
) -> str:
    """A `MatchReply` as a model sends it: pairings as (committed, planned, reason) and
    equivalences as (aspect, committed, planned, reason)."""
    return json.dumps(
        {
            "pairings": [{"committed": c, "planned": p, "reason": r} for c, p, r in pairings],
            "equivalences": [
                {"aspect": a, "committed": c, "planned": p, "reason": r}
                for a, c, p, r in equivalences
            ],
        }
    )
