# Data Director R3 Prototype

A prototype implementation of functional requirement **R3** from the *Data Director Agentic AI Blueprint* ([v1.0 FINAL](../../docs/BLUEPRINT.md)): recommending controlled vocabularies, ontologies and open data formats for research datasets.

This is a single slice through the Blueprint's five-layer reference architecture, built so that its claims can be tested against named Blueprint requirements — not a reference implementation of the full Data Director. See `docs/architecture.md` for the plan.

## Why R3

- **Read-only.** No writes, no irreversible actions — human-in-the-loop and rollback obligations are satisfied by construction.
- **Grounded.** Every recommendation resolves to a FAIRsharing registry record, converting hallucinated standards from a research problem into an engineering constraint.
- **Measurable.** FAIRsharing-verifiable outputs make R3 one of the few Blueprint requirements testable today.
- **High leverage.** Used at multiple points in the process flow: pre-collection vocabulary/ontology selection and open-format recommendation.

## Scope

R3 decomposes into six sub-obligations:

| ID | Obligation |
|---|---|
| R3.1 | Controlled vocabulary recommendations for concept linkage (field values → concept URIs) |
| R3.2 | Ontology recommendations for schema/model alignment |
| R3.3 | Open data format recommendations (dataset and file level) |
| R3.4 | Field-level format standards (date/time, geospatial, units, codes) |
| R3.5 | Support for emerging standards — no hard-coded standards list |
| R3.6 | Explicit abstention where no suitable resource exists, instead of a generic answer |

The alignment/linkage distinction (R3.1 vs R3.2) and abstention-as-first-class-output (R3.6) are the two design decisions the rest of the system is built around.

## The one rule everything follows from

> Nothing leaves the system that cannot be traced to a real record an actual registry query
> returned. The model may direct retrieval and weigh in on ranking (§5.6) — it is not confined to
> writing explanations for a candidate set and order it had no part in producing.

This makes the failure modes diagnosable — wrong candidates retrieved, or badly ranked — rather than embarrassing, and gives explainability, quality control and auditability by construction, without confining the model to an explanation-only role that the Blueprint never asked for.

## Architecture

A six-stage pipeline — **profile → retrieve → rank → explain → check → output** — running through all five Blueprint layers. Recommendations and "we found nothing suitable" are equal outputs, and both require human review by the output format itself.

Full detail — outputs, the FAIRsharing integration, evaluation approach and delivery plan — is in [`docs/architecture.md`](docs/architecture.md).

## Status

Plan, draft for comment, plus a walking skeleton in code.

The six stages exist as a runnable pipeline, but only **§5.1 tier-1 profiling** is genuinely
implemented — file formats, column type inference, counts, all local and with no model involved.
There is no FAIRsharing route yet, so every run declines all four kinds of recommendation and says
why. That output is the point: it is honest, schema-valid, and the baseline every registry route
added later has to keep honest.

```bash
cd experiments/standards-advisor
uv sync --all-extras
uv run pytest
uv run standards-advisor run samples/soil-chemistry.csv \
  --metadata samples/soil-chemistry.metadata.json
```

No API key is needed for any of that, and the test suite runs with network access disabled.

This is a technical experiment, and it can fail. §1.2 of the architecture document says what we are testing and what would make us stop; §9.1 has the first fortnight of work, which begins by checking three things about FAIRsharing that the design depends on. The milestones after that are a destination, not a commitment.

There is no human-subject evaluation: no ethics or approval route is in place, so the measurements in §8 are mechanical or checked against fixtures we wrote ourselves. Whether the recommendations are *good* in a data steward's judgement is the obvious next question and deliberately not this experiment's question.

Nothing here is authoritative — see [`experiments/README.md`](../README.md). This experiment has no separate licence, governance or citation metadata; it inherits the repository's.
