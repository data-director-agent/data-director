# ADR-0006: Dependency tiering and the mandatory fallback line

**Status:** Accepted
**Date:** 2026-09-04

## Context

The workbench adopts community implementations for everything that moves, validates, traces,
renders or measures data, and writes bespoke code only where a decision is made (whether an
action is permitted, whether evidence suffices, whether to decline). Adopted libraries can be
abandoned. The project needs a rule that keeps abandonment a local problem.

## Decision

Every external dependency is placed in one of three tiers, and every ADR that introduces one
fills in the line *fallback if this dependency is abandoned*. If the line cannot be filled in,
the dependency is in the wrong tier.

| Tier | Rule |
|---|---|
| **Evaluation and CI path** | Unconstrained. Abandonment does not affect a deployed instance. |
| **Runtime path** | Sits behind a thin internal interface with a named fallback. The conductor calls our interface; the library sits behind it. |
| **Rejected for v0** | Not adopted; the ADR records the reason. |

### The v0 dependency table

| Dependency | Tier | Interface it sits behind | Fallback |
|---|---|---|---|
| `pydantic` | Runtime | `contract/models.py` | dataclasses + the generated JSON Schema |
| `jsonschema` | Runtime | `contract/validate.py` | `fastjsonschema` |
| `httpx` | Runtime | `agents/r3/fairsharing/live.py` | `urllib.request` |
| `opentelemetry-sdk` | Runtime | `tracing.py` | direct JSON-lines writer (ADR-0002) |
| `rank-bm25` (+ numpy) | Runtime | `agents/r3/fairsharing/snapshot.py` | forty lines of BM25 |
| `a2a-sdk[http-server]` | Runtime | `transport/a2a.py` | hand-written JSON-RPC handler (ADR-0001) |
| `ag-ui-protocol` | Runtime | `transport/agui.py` | two pydantic models + SSE lines |
| `rocrate` | Runtime | `provenance.py` | write `ro-crate-metadata.json` directly |
| `pyyaml` | Runtime | `policy.py` | JSON profiles |
| `uvicorn` | Runtime | `cli.py serve` | any ASGI server |
| `anthropic` (optional extra) | Runtime | `agents/r3/explain.py::Explainer` | `TemplateExplainer`, or any HTTP client against the Messages API |
| `pytest`, `pytest-recording`, `pytest-json-report`, `linkml`, `ruff`, `mypy` | Evaluation/CI | — | — |
| `inspect-ai` (workbench `eval` extra; ADR-0013) | Evaluation/CI | `workbench/evaluation.py` | a loop over the case file calling `Conductor.invoke` |
| OPA/Cedar; in-toto/Sigstore; LangChain/LangGraph and other agent frameworks; a bespoke cassette layer; a bespoke trace format; MCP and Signpost FAIRsharing backends | Rejected | — | — |

The runtime tier has eleven members against the MVP plan's target of about eight. The three
most easily removed are `rocrate`, `anthropic` and `ag-ui-protocol`, each behind a single
module. The overshoot is recorded here rather than hidden by vendoring.

## Consequences

- Reviewers can reject a pull request that adds a runtime dependency without an interface and a
  fallback line.
- The table above is the dependency budget; changing it means editing this ADR.
