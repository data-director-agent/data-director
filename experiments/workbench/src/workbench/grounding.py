"""The grounding linter: a bespoke rule over a generic trace substrate.

Three rules, checked over the span tree of one `invoke_agent` and the envelope it produced:

- **G1** every `chat` span starts after at least one `retrieval` span in the same tree has
  ended. Retrieval precedes any model call: the model explains, it does not choose.
- **G2** every recommended `fairsharing_id` appears as `dd.source_id` on a `retrieval` span.
  Nothing is recommended that was not retrieved.
- **G3** every `content_hash` in the envelope's evidence matches a `dd.content_hash` on a
  `retrieval` span, and every recommendation's `evidence_hashes` are among them. The
  evidence the envelope cites is the evidence the trace saw.

The linter reads `SpanRecord`s and a plain envelope document, so it can run at invocation
time (the conductor) and offline over `spans.jsonl` + `envelope.json` (the CLI).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from workbench.tracing import (
    ATTR_CONTENT_HASH,
    ATTR_SOURCE_ID,
    CHAT,
    INVOKE_AGENT,
    RETRIEVAL,
    SpanRecord,
)


@dataclass(frozen=True)
class GroundingReport:
    passed: bool
    violations: list[str] = field(default_factory=list)
    retrieval_count: int = 0
    chat_count: int = 0

    def summary(self) -> str:
        if self.passed:
            return (
                f"grounding: passed ({self.retrieval_count} retrieval, "
                f"{self.chat_count} chat spans)"
            )
        return "grounding: FAILED\n  - " + "\n  - ".join(self.violations)


def _descendants(root: SpanRecord, records: list[SpanRecord]) -> list[SpanRecord]:
    by_parent: dict[str | None, list[SpanRecord]] = {}
    for r in records:
        by_parent.setdefault(r.parent_id, []).append(r)
    out: list[SpanRecord] = []
    stack = [root]
    while stack:
        node = stack.pop()
        for child in by_parent.get(node.span_id, []):
            out.append(child)
            stack.append(child)
    return out


def lint(records: list[SpanRecord], envelope: dict[str, Any]) -> GroundingReport:
    roots = [r for r in records if r.name == INVOKE_AGENT]
    if len(roots) != 1:
        return GroundingReport(
            passed=False,
            violations=[f"expected exactly one {INVOKE_AGENT} span, found {len(roots)}"],
        )
    tree = _descendants(roots[0], records)
    retrievals = [r for r in tree if r.name == RETRIEVAL]
    chats = [r for r in tree if r.name == CHAT]
    violations: list[str] = []

    # G1
    first_retrieval_end = min((r.end_ns for r in retrievals), default=None)
    for chat in chats:
        if first_retrieval_end is None:
            violations.append("G1: a chat span exists but no retrieval span does")
            break
        if chat.start_ns < first_retrieval_end:
            violations.append(
                f"G1: chat span {chat.span_id} started before the first retrieval span ended"
            )

    retrieved_ids = {str(r.attributes.get(ATTR_SOURCE_ID)) for r in retrievals}
    retrieved_hashes = {str(r.attributes.get(ATTR_CONTENT_HASH)) for r in retrievals}

    # G2
    payload = envelope.get("payload") or {}
    for item in payload.get("items", []):
        rid = item.get("resource", {}).get("fairsharing_id")
        if rid not in retrieved_ids:
            violations.append(f"G2: recommended {rid!r} was not retrieved in this invocation")
        # G3 (per recommendation)
        for h in item.get("evidence_hashes", []):
            if h not in retrieved_hashes:
                violations.append(
                    f"G3: recommendation for {rid!r} cites evidence hash {h[:12]}… not in trace"
                )

    # G3 (envelope evidence list)
    for ev in envelope.get("evidence", []):
        if ev.get("content_hash") not in retrieved_hashes:
            violations.append(
                f"G3: evidence {ev.get('source_id')!r} hash "
                f"{str(ev.get('content_hash'))[:12]}… not in trace"
            )

    return GroundingReport(
        passed=not violations,
        violations=violations,
        retrieval_count=len(retrievals),
        chat_count=len(chats),
    )
