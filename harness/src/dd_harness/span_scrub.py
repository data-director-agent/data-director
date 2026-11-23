"""Keep secrets out of the spans the harness imports from a remote agent
(docs/specs/security.md, invariant 2; docs/specs/transport.md, invariant 11).

The harness writes no secret-bearing attribute itself, but it stores a remote agent's spans as the
agent sent them, in `spans.jsonl`, the Process Run Crate and every export of the run. So before
they join the conductor's trace, each attribute of a span, of its events, links and resource is
dropped if

- its name says it holds a secret (a segment such as `token`, `password` or `authorization`),
- its value is shaped like a bearer credential or a JSON Web Token, or
- its value contains a secret the harness itself issued for this invocation (the delegation,
  tool or model grant).

Dropping is not a redaction pass over the record: it is applied at the one boundary where the
harness does not control what is written, and each drop is a security event, so an operator
learns which agent leaked what kind of value and can fix it. The run is not failed: what the
agent returned is still checked as any other run's.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from dd_sdk.security_log import SecurityEvent, emit

# A name segment that says the value is a secret. Segments are split on `.`, `_` and `-`, so
# `dd.delegation_token` is caught and `gen_ai.usage.input_tokens` is not.
SECRET_SEGMENTS = frozenset(
    {
        "apikey",
        "authorization",
        "cookie",
        "credential",
        "credentials",
        "key",
        "passwd",
        "password",
        "secret",
        "token",
    }
)
_SEGMENT = re.compile(r"[._\-]")
_BEARER = re.compile(r"\b(bearer|basic)\s+[A-Za-z0-9._~+/=\-]{8,}", re.IGNORECASE)
_JWT = re.compile(r"\beyJ[A-Za-z0-9_\-]{4,}\.[A-Za-z0-9_\-]{4,}\.[A-Za-z0-9_\-]*")

# Where in a `ReadableSpan.to_json` document attributes are kept.
_NESTED = ("events", "links")


class Reason:
    """Why an attribute was dropped; the security event's reason code."""

    NAME = "secret-named-attribute"
    SHAPE = "secret-shaped-value"
    ISSUED = "issued-secret"


@dataclass
class Scrubbed:
    """The spans with every secret-bearing attribute dropped, and the reason for each drop."""

    spans: tuple[dict[str, Any], ...]
    reasons: list[str] = field(default_factory=list)


def secret_named(name: str) -> bool:
    """Whether an attribute's name says it holds a secret."""
    segments = {s.lower() for s in _SEGMENT.split(name) if s}
    return bool(segments & SECRET_SEGMENTS)


def _values(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list | tuple):
        for item in value:
            yield from _values(item)


def why_dropped(name: str, value: Any, issued: Collection[str]) -> str | None:
    """The reason an attribute must not be stored, or None if it may be."""
    if secret_named(name):
        return Reason.NAME
    for text in _values(value):
        if any(secret and secret in text for secret in issued):
            return Reason.ISSUED
        if _BEARER.search(text) or _JWT.search(text):
            return Reason.SHAPE
    return None


def _clean(attributes: Any, issued: Collection[str], reasons: list[str]) -> Any:
    if not isinstance(attributes, Mapping):
        return attributes
    kept: dict[str, Any] = {}
    for name, value in attributes.items():
        reason = why_dropped(str(name), value, issued)
        if reason is None:
            kept[name] = value
        else:
            reasons.append(reason)
    return kept


def _scrub_one(
    span: Mapping[str, Any], issued: Collection[str], reasons: list[str]
) -> dict[str, Any]:
    out = dict(span)
    if "attributes" in out:
        out["attributes"] = _clean(out["attributes"], issued, reasons)
    for key in _NESTED:
        items = out.get(key)
        if isinstance(items, list):
            out[key] = [
                {**item, "attributes": _clean(item.get("attributes"), issued, reasons)}
                if isinstance(item, Mapping) and "attributes" in item
                else item
                for item in items
            ]
    resource = out.get("resource")
    if isinstance(resource, Mapping) and "attributes" in resource:
        out["resource"] = {
            **resource,
            "attributes": _clean(resource["attributes"], issued, reasons),
        }
    return out


def scrub(spans: Iterable[Mapping[str, Any]], issued: Collection[str] = ()) -> Scrubbed:
    """The spans with every attribute that could hold a secret dropped. `issued` is each secret
    the harness sent the agent for this invocation."""
    reasons: list[str] = []
    issued = [s for s in issued if s]
    clean = tuple(_scrub_one(span, issued, reasons) for span in spans)
    return Scrubbed(clean, reasons)


def scrub_received(
    spans: Iterable[Mapping[str, Any]],
    issued: Collection[str],
    *,
    agent_id: str,
    invocation_id: str,
    principal: str | None,
) -> tuple[dict[str, Any], ...]:
    """Scrub a remote agent's spans and record one security event per reason found."""
    result = scrub(spans, issued)
    for reason in sorted(set(result.reasons)):
        emit(
            SecurityEvent.SPAN_SECRET_DROPPED,
            outcome="failure",
            service="harness",
            principal=principal,
            reason=reason,
            agent_id=agent_id,
            invocation_id=invocation_id,
        )
    return result.spans
