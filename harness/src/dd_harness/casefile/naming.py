"""Content named, not carried: a case that must leave the institution keeps its records' structure
and writes their text as RFC 6920 `ni:` digests (docs/specs/casefile.md, Named content).

The rule is an allow-list, so it fails safe: a string is kept only when the key it sits under says
it is structure (an identifier, a time, a status, a code, a version, a digest, a title or a name),
and every other string is written as the `ni:` URI of its UTF-8 bytes. A field added to a record
later is therefore named, not carried. Numbers, booleans, nulls and mapping keys are kept. This
follows the provenance spec's invariants 5 and 6: titles, file names and a principal's identifier
and display name are carried; text is not.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any, Literal

from dd_harness.provenance_graph.nodes import digest_of, ni

Content = Literal["carried", "named"]
CONTENT: tuple[Content, ...] = ("carried", "named")

KEPT_SUFFIXES = (
    "_id",
    "_ids",
    "_at",
    "_time",
    "_digest",
    "_hash",
    "_version",
    "_code",
    "_status",
    "_mode",
    "_kind",
    "_schema",
    "_ref",
    "_uri",
    "_title",
)
KEPT_KEYS = frozenset(
    {
        "at",
        "time",
        "event",
        "outcome",
        "status",
        "kind",
        "mode",
        "digest",
        "name",
        "title",
        "type",
        "format",
        "scope",
        "model",
        "provider",
        "assurance",
        "vouched_by",
        # A journal line's unit and priority, and the service a security event names.
        "unit",
        "priority",
        "service",
        # The checks' own reports: rule codes, source identifiers and hash prefixes.
        "violations",
        "unresolved",
    }
)
# Span attributes: the fixed `dd.*` trace vocabulary (identifiers and hashes), and which model was
# asked for what kind of call.
KEPT_PREFIXES = ("dd.",)
KEPT_GEN_AI = frozenset(
    {
        "gen_ai.operation.name",
        "gen_ai.provider.name",
        "gen_ai.system",
        "gen_ai.request.model",
        "gen_ai.response.model",
    }
)


def is_kept(key: str) -> bool:
    """Whether a string under `key` is structure, and kept."""
    return (
        key in KEPT_KEYS
        or key in KEPT_GEN_AI
        or key.endswith(KEPT_SUFFIXES)
        or key.startswith(KEPT_PREFIXES)
    )


def named(text: str) -> str:
    """The `ni:` URI of `text`'s UTF-8 bytes."""
    return ni(digest_of(text))


def name_content(value: Any, key: str = "") -> Any:
    """`value` with every string not under a kept key written as its `ni:` URI. A list's items
    sit under the key of the list."""
    if isinstance(value, str):
        return value if is_kept(key) else named(value)
    if isinstance(value, Mapping):
        return {k: name_content(v, str(k)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [name_content(item, key) for item in value]
    return value


def _json_bytes(data: bytes, *, compact: bool) -> bytes:
    value = name_content(json.loads(data))
    if compact:
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()


def name_artifact(name: str, data: bytes) -> bytes:
    """A stored artifact with its content named: a JSON document or JSON lines walked as records.
    Any other artifact is one of the checks' own text reports and is kept."""
    if name.endswith(".jsonl"):
        lines = [line for line in data.decode().splitlines() if line.strip()]
        return b"".join(_json_bytes(line.encode(), compact=True) + b"\n" for line in lines)
    if name.endswith((".json", ".jsonld")):
        return _json_bytes(data, compact=False)
    return data


Shape = Callable[[Any], Any]


def shaper(content: Content) -> Shape:
    """What a record goes through on its way into a case."""
    if content not in CONTENT:
        raise ValueError(f"a case's content is one of {', '.join(CONTENT)}, not {content!r}")
    return name_content if content == "named" else _same


def _same(value: Any) -> Any:
    return value
