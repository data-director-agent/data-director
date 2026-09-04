"""The grounding linter: bespoke rules over a generic trace substrate (ADR-0008).

The linter reads the span tree of one `invoke_agent` and the envelope it produced, and applies
the rule set for the grounding mode the envelope declares. It never needs to know the payload
class: it walks the payload document for `grounded_on` lists (the `Grounded` mixin), and a
payload that has none is a violation. Nothing passes because the linter did not recognise it.

Structural, every mode (G0):
  exactly one `invoke_agent` root; the envelope's `grounding_mode` is valid and equals the root
  span's `dd.grounding_mode`; a payload, if present, has `schema_class` and a root `grounded_on`;
  every grounding reference is well formed.

`retrieval` — the agent retrieves before it reasons:
  G1 every `chat` span starts after at least one `retrieval` span has ended.
  G2 every `grounded_on` entry, at any depth, matches a `retrieval` span on both `dd.source_id`
     and `dd.content_hash`. Nothing is asserted that was not retrieved. A succeeded payload with
     no grounding reference at all is a G2 violation.
  G3 every `content_hash` in the envelope's evidence appears on a `retrieval` span.
  G4 every `grounded_on` hash appears in the envelope's evidence: the envelope is complete about
     what it rests on.

`input_only` — the agent works over what it was given; it may call a model:
  R1 no `retrieval` span exists.
  R2 every `grounded_on` entry and every evidence item cites the input: `source_id` is
     `input:<invocation_id>` and `content_hash` equals the root span's `dd.input_hash`.
  R3 a succeeded envelope cites the input at least once.

`none` — deterministic over the input: R1-R3 and
  N1 no `chat` span exists.

The linter reads `SpanRecord`s and a plain envelope document, so it runs at invocation time (the
conductor) and offline over `spans.jsonl` + `envelope.json` (the CLI).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from workbench.contract.models import GroundingMode, input_source_id
from workbench.tracing import (
    ATTR_CONTENT_HASH,
    ATTR_GROUNDING_MODE,
    ATTR_INPUT_HASH,
    ATTR_SOURCE_ID,
    CHAT,
    INVOKE_AGENT,
    RETRIEVAL,
    SpanRecord,
)


@dataclass(frozen=True)
class GroundingReport:
    passed: bool
    mode: str | None = None
    violations: list[str] = field(default_factory=list)
    retrieval_count: int = 0
    chat_count: int = 0

    def summary(self) -> str:
        mode = self.mode or "unknown mode"
        if self.passed:
            return (
                f"grounding: passed [{mode}] ({self.retrieval_count} retrieval, "
                f"{self.chat_count} chat spans)"
            )
        return f"grounding: FAILED [{mode}]\n  - " + "\n  - ".join(self.violations)


@dataclass(frozen=True)
class Tree:
    """The span tree of one invocation, indexed the way the rules read it."""

    root: SpanRecord
    retrievals: list[SpanRecord]
    chats: list[SpanRecord]

    @property
    def retrieved(self) -> set[tuple[str, str]]:
        return {
            (str(r.attributes.get(ATTR_SOURCE_ID)), str(r.attributes.get(ATTR_CONTENT_HASH)))
            for r in self.retrievals
        }

    @property
    def retrieved_hashes(self) -> set[str]:
        return {h for _, h in self.retrieved}


@dataclass(frozen=True)
class Refs:
    """Every grounding reference the payload makes, and the envelope's evidence, as pairs."""

    grounded_on: list[tuple[str, str]]
    evidence: list[tuple[str, str]]


Rule = Callable[[Tree, dict[str, Any], Refs], list[str]]


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


def _walk_grounded_on(node: Any) -> Iterator[Any]:
    """Yield every value under a `grounded_on` key, at any depth, in document order."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "grounded_on":
                yield value
            else:
                yield from _walk_grounded_on(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_grounded_on(item)


def _collect_refs(envelope: dict[str, Any]) -> tuple[Refs, list[str]]:
    violations: list[str] = []
    grounded: list[tuple[str, str]] = []
    for lst in _walk_grounded_on(envelope.get("payload")):
        if not isinstance(lst, list):
            violations.append("G0: grounded_on is not a list")
            continue
        for ref in lst:
            if (
                not isinstance(ref, dict)
                or not isinstance(ref.get("source_id"), str)
                or not isinstance(ref.get("content_hash"), str)
            ):
                violations.append(f"G0: malformed grounding reference {ref!r}")
                continue
            grounded.append((ref["source_id"], ref["content_hash"]))
    evidence = [
        (str(ev.get("source_id")), str(ev.get("content_hash")))
        for ev in envelope.get("evidence") or []
    ]
    return Refs(grounded_on=grounded, evidence=evidence), violations


# --- Rules ------------------------------------------------------------------------------------


def g1_retrieval_before_chat(tree: Tree, envelope: dict[str, Any], refs: Refs) -> list[str]:
    out: list[str] = []
    first_retrieval_end = min((r.end_ns for r in tree.retrievals), default=None)
    for chat in tree.chats:
        if first_retrieval_end is None:
            out.append("G1: a chat span exists but no retrieval span does")
            break
        if chat.start_ns < first_retrieval_end:
            out.append(
                f"G1: chat span {chat.span_id} started before the first retrieval span ended"
            )
    return out


def g2_asserted_was_retrieved(tree: Tree, envelope: dict[str, Any], refs: Refs) -> list[str]:
    out: list[str] = []
    retrieved = tree.retrieved
    for source_id, content_hash in refs.grounded_on:
        if (source_id, content_hash) not in retrieved:
            out.append(
                f"G2: payload rests on {source_id!r} ({content_hash[:12]}…) which was not "
                "retrieved in this invocation"
            )
    if _succeeded(envelope) and envelope.get("payload") is not None and not refs.grounded_on:
        out.append("G2: a succeeded retrieval-mode payload rests on nothing")
    return out


def g3_evidence_was_retrieved(tree: Tree, envelope: dict[str, Any], refs: Refs) -> list[str]:
    hashes = tree.retrieved_hashes
    return [
        f"G3: evidence {source_id!r} hash {content_hash[:12]}… not in trace"
        for source_id, content_hash in refs.evidence
        if content_hash not in hashes
    ]


def g4_evidence_is_complete(tree: Tree, envelope: dict[str, Any], refs: Refs) -> list[str]:
    cited = {h for _, h in refs.evidence}
    return [
        f"G4: payload rests on {source_id!r} ({content_hash[:12]}…) absent from evidence"
        for source_id, content_hash in refs.grounded_on
        if content_hash not in cited
    ]


def r1_no_retrieval(tree: Tree, envelope: dict[str, Any], refs: Refs) -> list[str]:
    if tree.retrievals:
        return [f"R1: {len(tree.retrievals)} retrieval span(s) in an agent that declared none"]
    return []


def r2_everything_cites_the_input(tree: Tree, envelope: dict[str, Any], refs: Refs) -> list[str]:
    expected = (
        input_source_id(str(envelope.get("invocation_id"))),
        str(tree.root.attributes.get(ATTR_INPUT_HASH)),
    )
    out: list[str] = []
    for label, pairs in (("payload", refs.grounded_on), ("evidence", refs.evidence)):
        for pair in pairs:
            if pair != expected:
                out.append(
                    f"R2: {label} cites {pair[0]!r} ({pair[1][:12]}…); an input-grounded agent "
                    f"may cite only {expected[0]!r} ({expected[1][:12]}…)"
                )
    return out


def r3_succeeded_cites_the_input(tree: Tree, envelope: dict[str, Any], refs: Refs) -> list[str]:
    if _succeeded(envelope) and not refs.evidence:
        return ["R3: a succeeded input-grounded envelope cites no evidence"]
    return []


def n1_no_chat(tree: Tree, envelope: dict[str, Any], refs: Refs) -> list[str]:
    if tree.chats:
        return [f"N1: {len(tree.chats)} chat span(s) in an agent that declared no model call"]
    return []


def _succeeded(envelope: dict[str, Any]) -> bool:
    return bool((envelope.get("outcome") or {}).get("status") == "succeeded")


RULES: dict[GroundingMode, tuple[Rule, ...]] = {
    GroundingMode.RETRIEVAL: (
        g1_retrieval_before_chat,
        g2_asserted_was_retrieved,
        g3_evidence_was_retrieved,
        g4_evidence_is_complete,
    ),
    GroundingMode.INPUT_ONLY: (
        r1_no_retrieval,
        r2_everything_cites_the_input,
        r3_succeeded_cites_the_input,
    ),
    GroundingMode.NONE: (
        r1_no_retrieval,
        r2_everything_cites_the_input,
        r3_succeeded_cites_the_input,
        n1_no_chat,
    ),
}


# --- Entry point ------------------------------------------------------------------------------


def lint(records: list[SpanRecord], envelope: dict[str, Any]) -> GroundingReport:
    declared = envelope.get("grounding_mode")
    roots = [r for r in records if r.name == INVOKE_AGENT]
    if len(roots) != 1:
        return GroundingReport(
            passed=False,
            mode=str(declared) if declared else None,
            violations=[f"G0: expected exactly one {INVOKE_AGENT} span, found {len(roots)}"],
        )
    root = roots[0]
    descendants = _descendants(root, records)
    tree = Tree(
        root=root,
        retrievals=[r for r in descendants if r.name == RETRIEVAL],
        chats=[r for r in descendants if r.name == CHAT],
    )
    violations: list[str] = []

    # G0: mode.
    try:
        mode = GroundingMode(str(declared))
    except ValueError:
        return GroundingReport(
            passed=False,
            mode=str(declared) if declared else None,
            violations=[f"G0: envelope declares no valid grounding_mode ({declared!r})"],
            retrieval_count=len(tree.retrievals),
            chat_count=len(tree.chats),
        )
    span_mode = root.attributes.get(ATTR_GROUNDING_MODE)
    if span_mode != mode.value:
        violations.append(
            f"G0: envelope declares grounding_mode {mode.value!r} but the root span carries "
            f"{span_mode!r}"
        )

    # G0: payload shape.
    payload = envelope.get("payload")
    if payload is not None:
        if not isinstance(payload, dict):
            violations.append("G0: payload is not an object")
        else:
            if "schema_class" not in payload:
                violations.append("G0: payload lacks schema_class")
            if "grounded_on" not in payload:
                violations.append(
                    f"G0: payload {payload.get('schema_class')!r} lacks grounded_on; an "
                    "ungroundable payload is a violation, not a pass"
                )
    refs, ref_violations = _collect_refs(envelope)
    violations.extend(ref_violations)

    for rule in RULES[mode]:
        violations.extend(rule(tree, envelope, refs))

    return GroundingReport(
        passed=not violations,
        mode=mode.value,
        violations=violations,
        retrieval_count=len(tree.retrievals),
        chat_count=len(tree.chats),
    )
