"""Test doubles for advisor.ethics: replies shaped like the reader's schema, for
`dd_sdk.testing.FakeModel`."""

from __future__ import annotations

import json
from collections.abc import Sequence


def reader_reply(flags: Sequence[tuple[str, str, str]] = (), questions: Sequence[str] = ()) -> str:
    """A reply adding `flags`, each (field, category, reason), and `questions`."""
    return json.dumps(
        {
            "flags": [{"field": f, "category": c, "reason": r} for f, c, r in flags],
            "questions": list(questions),
        }
    )
