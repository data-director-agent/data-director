"""OpenTelemetry setup and the owned attribute set (ADR-0002).

This is the only module that imports the OpenTelemetry SDK. Everything else asks for a
`Tracer` and uses the span helpers below, which fix the span names and attribute keys so an
agent cannot misspell them. The workbench's grounding linter reads plain `SpanRecord`s produced
by `records_from_spans` and `records_from_jsonl`, never SDK objects.

An agent's spans are recorded in the agent's own process (`dd_sdk.serve`) and imported into the
conductor's `Tracing` with `import_spans`, so one trace holds both sides of an invocation.
"""

from __future__ import annotations

import contextlib
import json
import threading
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    ConsoleSpanExporter,
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.trace import Link, Span, SpanContext, Tracer

# --- Span names -------------------------------------------------------------------------------

INVOKE_AGENT = "invoke_agent"
POLICY_GATE = "policy_gate"
RETRIEVAL = "retrieval"
CHAT = "chat"
EXECUTE_TOOL = "execute_tool"
DELEGATE = "delegate"  # ADR-0012: an agent asks the workbench to invoke another agent

# --- Owned attributes (the linter reads only these) -------------------------------------------

ATTR_OPERATION = "dd.operation"
ATTR_AGENT_ID = "dd.agent_id"
ATTR_SOURCE_ID = "dd.source_id"
ATTR_CONTENT_HASH = "dd.content_hash"
ATTR_MODEL_ID = "dd.model_id"
ATTR_INPUT_TOKENS = "dd.input_tokens"
ATTR_OUTPUT_TOKENS = "dd.output_tokens"
ATTR_OUTCOME = "dd.outcome"
ATTR_GROUNDING_MODE = "dd.grounding_mode"  # ADR-0008: the mode the linter must apply
ATTR_INPUT_HASH = "dd.input_hash"  # ADR-0009: what an input_only agent's evidence must equal

OWNED_ATTRIBUTES = frozenset(
    {
        ATTR_OPERATION,
        ATTR_AGENT_ID,
        ATTR_SOURCE_ID,
        ATTR_CONTENT_HASH,
        ATTR_MODEL_ID,
        ATTR_INPUT_TOKENS,
        ATTR_OUTPUT_TOKENS,
        ATTR_OUTCOME,
        ATTR_GROUNDING_MODE,
        ATTR_INPUT_HASH,
    }
)


@dataclass(frozen=True)
class SpanRecord:
    """The subset of a span the linter and the provenance writer need."""

    name: str
    span_id: str
    parent_id: str | None
    trace_id: str
    start_ns: int
    end_ns: int
    attributes: dict[str, Any] = field(default_factory=dict)


def records_from_spans(spans: list[ReadableSpan]) -> list[SpanRecord]:
    out: list[SpanRecord] = []
    for s in spans:
        ctx = s.get_span_context()
        assert ctx is not None
        out.append(
            SpanRecord(
                name=s.name,
                span_id=format(ctx.span_id, "016x"),
                parent_id=format(s.parent.span_id, "016x") if s.parent is not None else None,
                trace_id=format(ctx.trace_id, "032x"),
                start_ns=s.start_time or 0,
                end_ns=s.end_time or 0,
                attributes={k: v for k, v in (s.attributes or {}).items() if k in OWNED_ATTRIBUTES},
            )
        )
    return out


def records_from_jsonl(lines: list[dict[str, Any]]) -> list[SpanRecord]:
    """Rebuild records from the JSON-lines file exporter's output (`ReadableSpan.to_json`)."""
    out: list[SpanRecord] = []
    for d in lines:
        ctx = d["context"]
        parent = d.get("parent_id")
        out.append(
            SpanRecord(
                name=d["name"],
                span_id=_strip_hex(ctx["span_id"]),
                parent_id=_strip_hex(parent) if parent else None,
                trace_id=_strip_hex(ctx["trace_id"]),
                start_ns=_iso_to_ns(d["start_time"]),
                end_ns=_iso_to_ns(d["end_time"]),
                attributes={
                    k: v for k, v in d.get("attributes", {}).items() if k in OWNED_ATTRIBUTES
                },
            )
        )
    return out


def _strip_hex(value: str) -> str:
    return value[2:] if value.startswith("0x") else value


def _iso_to_ns(value: str) -> int:
    from datetime import datetime

    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return int(dt.timestamp() * 1_000_000_000)


# --- Provider ---------------------------------------------------------------------------------


class TraceSpanExporter(SpanExporter):
    """Finished spans held in memory by trace id, so one trace can be read and then released.

    The SDK's `InMemorySpanExporter` keeps every span until `clear()` and has no per-trace
    removal, so a long-running conductor would hold every span since start-up and filter all of
    them on each run.
    """

    def __init__(self) -> None:
        self._spans: dict[str, list[ReadableSpan]] = {}
        self._lock = threading.Lock()

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        with self._lock:
            for span in spans:
                ctx = span.get_span_context()
                assert ctx is not None
                self._spans.setdefault(format(ctx.trace_id, "032x"), []).append(span)
        return SpanExportResult.SUCCESS

    def get_finished_spans(self, trace_id: str | None = None) -> list[ReadableSpan]:
        with self._lock:
            if trace_id is not None:
                return list(self._spans.get(trace_id, []))
            return [span for spans in self._spans.values() for span in spans]

    def discard(self, trace_id: str) -> None:
        with self._lock:
            self._spans.pop(trace_id, None)

    def clear(self) -> None:
        with self._lock:
            self._spans.clear()

    def shutdown(self) -> None:
        self.clear()


@dataclass
class Tracing:
    """A tracer plus the in-memory exporter the conductor reads spans back from."""

    provider: TracerProvider
    memory: TraceSpanExporter
    _file_handle: IO[str] | None = None
    # trace id the conductor issued -> span documents a remote agent returned for it. Kept under
    # the conductor's trace id whatever trace id the documents claim, so a span that names a
    # foreign trace still reaches the linter (G0) instead of being filtered out unseen.
    imported: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    @property
    def tracer(self) -> Tracer:
        return self.provider.get_tracer("data-director")

    def import_spans(self, trace_id: str, spans: Iterable[dict[str, Any]]) -> None:
        self.imported.setdefault(trace_id, []).extend(spans)

    def finished_records(self, trace_id: str | None = None) -> list[SpanRecord]:
        records = records_from_spans(self.memory.get_finished_spans(trace_id))
        if trace_id is not None:
            records += records_from_jsonl(self.imported.get(trace_id, []))
        else:
            for spans in self.imported.values():
                records += records_from_jsonl(spans)
        return records

    def write_jsonl(self, path: Path, trace_id: str) -> None:
        """Write the finished spans of one trace as one JSON object per line.

        The SDK has no JSON-file exporter; `ReadableSpan.to_json` is stable and complete, so
        the file is written directly rather than through `ConsoleSpanExporter`.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            for span in self.memory.get_finished_spans(trace_id):
                fh.write(span.to_json(indent=None) + "\n")
            for doc in self.imported.get(trace_id, []):
                fh.write(json.dumps(doc) + "\n")

    def discard(self, trace_id: str) -> None:
        """Release one trace's spans, local and imported, once they have been written out."""
        self.memory.discard(trace_id)
        self.imported.pop(trace_id, None)

    def clear(self) -> None:
        self.memory.clear()
        self.imported.clear()

    def shutdown(self) -> None:
        self.provider.shutdown()
        if self._file_handle is not None:
            self._file_handle.close()


def make_tracing(
    console: IO[str] | None = None, service_name: str = "data-director-workbench"
) -> Tracing:
    """An isolated provider (not the global one) so tests and CLI runs never share state.

    OTLP export is deliberately not wired here: the standard OTEL_EXPORTER_OTLP_* variables
    work with the `opentelemetry-exporter-otlp` package, which is not a v0 dependency.
    """
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    memory = TraceSpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(memory))
    if console is not None:
        provider.add_span_processor(
            SimpleSpanProcessor(
                ConsoleSpanExporter(out=console, formatter=lambda s: s.to_json(indent=None) + "\n")
            )
        )
    return Tracing(provider=provider, memory=memory)


# --- Span helpers -----------------------------------------------------------------------------


@contextlib.contextmanager
def invoke_agent_span(
    tracer: Tracer,
    agent_id: str,
    grounding_mode: str,
    input_hash: str,
    link: SpanContext | None = None,
) -> Iterator[Span]:
    """The root of one invocation. Mode and input hash are set here, by the conductor, so the
    linter reads what the harness declared rather than what the agent claims.

    A delegated invocation passes `link`, the delegating agent's `delegate` span: the child then
    starts a trace of its own, linked to that span rather than nested in it, so each invocation
    is linted over its own tree (ADR-0012).
    """
    kwargs: dict[str, Any] = {}
    if link is not None:
        kwargs = {"context": Context(), "links": [Link(link)]}
    with tracer.start_as_current_span(INVOKE_AGENT, **kwargs) as span:
        span.set_attribute(ATTR_OPERATION, INVOKE_AGENT)
        span.set_attribute(ATTR_AGENT_ID, agent_id)
        span.set_attribute(ATTR_GROUNDING_MODE, grounding_mode)
        span.set_attribute(ATTR_INPUT_HASH, input_hash)
        yield span


@contextlib.contextmanager
def policy_gate_span(tracer: Tracer, agent_id: str) -> Iterator[Span]:
    with tracer.start_as_current_span(POLICY_GATE) as span:
        span.set_attribute(ATTR_OPERATION, POLICY_GATE)
        span.set_attribute(ATTR_AGENT_ID, agent_id)
        yield span


@contextlib.contextmanager
def retrieval_span(tracer: Tracer, source_id: str, content_hash: str) -> Iterator[Span]:
    """One span per record retrieved: this is what grounds a recommendation."""
    with tracer.start_as_current_span(RETRIEVAL) as span:
        span.set_attribute(ATTR_OPERATION, RETRIEVAL)
        span.set_attribute(ATTR_SOURCE_ID, source_id)
        span.set_attribute(ATTR_CONTENT_HASH, content_hash)
        yield span


@contextlib.contextmanager
def chat_span(tracer: Tracer, model_id: str) -> Iterator[Span]:
    with tracer.start_as_current_span(CHAT) as span:
        span.set_attribute(ATTR_OPERATION, CHAT)
        span.set_attribute(ATTR_MODEL_ID, model_id)
        yield span


@contextlib.contextmanager
def delegate_span(tracer: Tracer, agent_id: str) -> Iterator[Span]:
    """One span per delegation, in the delegating agent's trace. `dd.agent_id` names the agent
    delegated to; the caller sets `dd.source_id` and `dd.content_hash` once the child envelope
    is back, so a reader of the trace sees what was relayed."""
    with tracer.start_as_current_span(DELEGATE) as span:
        span.set_attribute(ATTR_OPERATION, DELEGATE)
        span.set_attribute(ATTR_AGENT_ID, agent_id)
        yield span


def record_tokens(span: Span, input_tokens: int | None, output_tokens: int | None) -> None:
    if input_tokens is not None:
        span.set_attribute(ATTR_INPUT_TOKENS, input_tokens)
    if output_tokens is not None:
        span.set_attribute(ATTR_OUTPUT_TOKENS, output_tokens)


@contextlib.contextmanager
def execute_tool_span(tracer: Tracer, tool_name: str) -> Iterator[Span]:
    with tracer.start_as_current_span(EXECUTE_TOOL) as span:
        span.set_attribute(ATTR_OPERATION, EXECUTE_TOOL)
        span.set_attribute("dd.tool_name", tool_name)
        yield span


def current_trace_id() -> str | None:
    ctx = trace.get_current_span().get_span_context()
    return format(ctx.trace_id, "032x") if ctx.is_valid else None
