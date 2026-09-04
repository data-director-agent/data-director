"""OpenTelemetry setup and the owned attribute set (ADR-0002).

This is the only module that imports the OpenTelemetry SDK. Everything else asks for a
`Tracer` and uses the span helpers below, which fix the span names and attribute keys so an
agent cannot misspell them. The grounding linter (`workbench.grounding`) reads plain
`SpanRecord`s produced by `records_from_spans`, never SDK objects.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import Span, Tracer

# --- Span names -------------------------------------------------------------------------------

INVOKE_AGENT = "invoke_agent"
POLICY_GATE = "policy_gate"
RETRIEVAL = "retrieval"
CHAT = "chat"
EXECUTE_TOOL = "execute_tool"

# --- Owned attributes (the linter reads only these) -------------------------------------------

ATTR_OPERATION = "dd.operation"
ATTR_AGENT_ID = "dd.agent_id"
ATTR_SOURCE_ID = "dd.source_id"
ATTR_CONTENT_HASH = "dd.content_hash"
ATTR_MODEL_ID = "dd.model_id"
ATTR_INPUT_TOKENS = "dd.input_tokens"
ATTR_OUTPUT_TOKENS = "dd.output_tokens"
ATTR_OUTCOME = "dd.outcome"

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


@dataclass
class Tracing:
    """A tracer plus the in-memory exporter the conductor reads spans back from."""

    provider: TracerProvider
    memory: InMemorySpanExporter
    _file_handle: IO[str] | None = None

    @property
    def tracer(self) -> Tracer:
        return self.provider.get_tracer("workbench")

    def finished_records(self, trace_id: str | None = None) -> list[SpanRecord]:
        records = records_from_spans(list(self.memory.get_finished_spans()))
        if trace_id is not None:
            records = [r for r in records if r.trace_id == trace_id]
        return records

    def write_jsonl(self, path: Path, trace_id: str) -> None:
        """Write the finished spans of one trace as one JSON object per line.

        The SDK has no JSON-file exporter; `ReadableSpan.to_json` is stable and complete, so
        the file is written directly rather than through `ConsoleSpanExporter`.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            for span in self.memory.get_finished_spans():
                ctx = span.get_span_context()
                if ctx is not None and format(ctx.trace_id, "032x") == trace_id:
                    fh.write(span.to_json(indent=None) + "\n")

    def clear(self) -> None:
        self.memory.clear()

    def shutdown(self) -> None:
        self.provider.shutdown()
        if self._file_handle is not None:
            self._file_handle.close()


def make_tracing(console: IO[str] | None = None) -> Tracing:
    """An isolated provider (not the global one) so tests and CLI runs never share state.

    OTLP export is deliberately not wired here: the standard OTEL_EXPORTER_OTLP_* variables
    work with the `opentelemetry-exporter-otlp` package, which is not a v0 dependency.
    """
    resource = Resource.create({"service.name": "data-director-workbench"})
    provider = TracerProvider(resource=resource)
    memory = InMemorySpanExporter()
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
def invoke_agent_span(tracer: Tracer, agent_id: str) -> Iterator[Span]:
    with tracer.start_as_current_span(INVOKE_AGENT) as span:
        span.set_attribute(ATTR_OPERATION, INVOKE_AGENT)
        span.set_attribute(ATTR_AGENT_ID, agent_id)
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
