"""How a draft marks a gap and names the question that asks for it (docs/specs/drafting.md)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

# How the draft marks what the researcher writes. A person's edit replaces it.
PLACEHOLDER = "_To be written by the researcher: {ask}_"
# What follows a placeholder: the question that asks for it. Not shown in the rendered README.
GAP_MARKER = "<!-- dd:gap {question_id} -->"
# How many hexadecimal digits of the gap's SHA-256 a question identifier keeps.
QUESTION_ID_DIGITS = 16


def question_id(target: Mapping[str, str]) -> str:
    """A question's identifier, derived from the gap it targets and never from its position, so
    that the same gap has the same identifier in every version (docs/specs/drafting.md)."""
    canonical = json.dumps(target, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"q-{digest[:QUESTION_ID_DIGITS]}"
