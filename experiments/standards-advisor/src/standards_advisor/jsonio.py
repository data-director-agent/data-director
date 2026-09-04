"""Reading a JSON object from disk without raising.

Three things the pipeline reads are JSON objects written by someone else: a repository metadata
record, a Frictionless Table Schema, and a file of intake answers. All three are *content*, so a
malformed one is a fact to record rather than a crash (see `errors`) — and all three want the
same lenient treatment, described once here instead of three times.

The error is returned rather than raised so the caller decides what it means. A malformed
metadata record degrades a profile; a malformed data dictionary leaves nothing to profile at
all. Only the caller knows which.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json_object(path: Path) -> tuple[dict[str, Any], str | None]:
    """Read a JSON object.

    Returns `(object, None)` on success and `({}, reason)` on any failure — absent, unreadable,
    malformed, or valid JSON that is not an object. The empty mapping means a caller that does
    not care why can ignore the second element and still behave correctly.
    """
    if not path.is_file():
        return {}, "not a readable file"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {}, f"could not be read: {exc}"
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError as exc:
        return {}, f"is not valid JSON: {exc}"
    if not isinstance(loaded, dict):
        return {}, f"is not a JSON object but a {type(loaded).__name__}"
    return loaded, None


def text_list(value: Any) -> list[str]:
    """The strings in a JSON value, tolerating a bare string where a list was expected.

    Used for every list-of-strings field read off untrusted JSON — keywords, enumerations,
    missing-value codes. Non-strings are dropped rather than coerced: `str()` on a number would
    invent a formatting decision, and a code list is exactly where that would matter.
    """
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return []
