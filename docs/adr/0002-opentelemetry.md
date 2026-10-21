# ADR-0002: OpenTelemetry as the trace substrate, adopted in two stages

**Status:** Accepted
**Date:** 2026-09-04

## Context

Blueprint R10 and C13 require every agent action to be recorded, attributable and auditable, and
C14 requires a log of reasoning steps and decision points. The grounding invariant (retrieval
precedes any model call; nothing is recommended that was not retrieved) needs a trace to check
against. The standards-advisor experiment wrote its own `events.jsonl`; a bespoke trace format is
one more thing for every consumer to learn.

OpenTelemetry has a maintained SDK, a span-tree model that matches an agent invocation, and
exporters for every backend. Its GenAI semantic conventions (`gen_ai.*`) are still in development
and SDKs disagree on attribute names, so aligning to them now would mean chasing renames.

## Decision

- **Stage one (v0):** OpenTelemetry SDK spans with a fixed span-name vocabulary — `invoke_agent`,
  `policy_gate`, `retrieval`, `chat`, `execute_tool` — and a small owned attribute set under the
  `dd.` prefix: `dd.operation`, `dd.agent_id`, `dd.source_id`, `dd.content_hash`, `dd.model_id`,
  `dd.input_tokens`, `dd.output_tokens`, `dd.outcome`. The grounding linter reads only these.
  Spans are exported in memory (for the linter and tests) and as one JSON object per line to
  `runs/<invocation_id>/spans.jsonl`; an OTLP endpoint is optional via the standard environment
  variables.
- **Stage two (v0.2):** a span processor that copies the owned attributes onto whichever GenAI
  semantic-convention names are Stable at that point. The owned attributes remain the source of
  truth; the convention names are derived.

## Dependencies introduced

| Dependency | Tier | Fallback if this dependency is abandoned |
|---|---|---|
| `opentelemetry-sdk` | Runtime path | `dd_sdk.tracing` is the only module that imports it; the span helpers (`retrieval_span`, `chat_span`, …) take a dict of owned attributes and could write them to a JSON-lines file directly. The linter reads a plain span-record structure, not SDK objects. |

## Consequences

- Traces are readable by any OpenTelemetry tool today.
- Renaming an owned attribute is a contract change and needs an ADR.
- No JSON-file exporter exists in the SDK; the file exporter is `ConsoleSpanExporter` pointed at a
  file with a one-line JSON formatter. This is adequate and documented in `tracing.py`.
