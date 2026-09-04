"""Evidence hashing.

The hash covers the canonicalised *projection* of a retrieved record that a grounding claim
rests on, not the HTTP body. Two routes to the same record (the public JSON route, the
authenticated API, a snapshot) yield the same hash if they agree on those fields, which is
what lets a snapshot cassette and a live run be compared.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

CANONICALISATION = "json-sorted-utf8-v1"
HASH_ALGORITHM = "sha256"

# The fields a recommendation's grounding rests on. Adding one changes every hash; do it
# deliberately and bump CANONICALISATION.
PROJECTED_FIELDS = (
    "fairsharing_id",
    "doi",
    "name",
    "abbreviation",
    "record_type",
    "status",
    "description",
    "subjects",
    "domains",
)


def canonicalise(record: dict[str, Any]) -> bytes:
    """Project to PROJECTED_FIELDS, then JSON with sorted keys, no whitespace, UTF-8.

    Lists of labels are sorted so that ordering differences between routes do not change the
    hash. Values are strings, lists of strings or null, so Python's json module is adequate;
    RFC 8785 number canonicalisation is not needed.
    """
    projection: dict[str, Any] = {}
    for key in PROJECTED_FIELDS:
        value = record.get(key)
        if isinstance(value, list):
            value = sorted(str(v) for v in value)
        projection[key] = value
    return json.dumps(projection, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def content_hash(record: dict[str, Any]) -> str:
    return hashlib.sha256(canonicalise(record)).hexdigest()
