# Data Director R3 Prototype — Standards Advisor

A prototype implementation of functional requirement **R3** from the *Data Director Agentic AI Blueprint* ([v1.0 FINAL](../../docs/BLUEPRINT.md)): recommending controlled vocabularies, ontologies and open data formats for research datasets. Functional requirement 3 (R3) specifies that the Data Director must "suggest appropriate vocabularies, ontologies and open data formats."

This is a single slice through the Blueprint's five-layer reference architecture, built so that its claims can be tested against named Blueprint requirements — not a reference implementation of the full Data Director. See `docs/architecture.md` for the plan.

## Audience

This experiment is for people evaluating the Blueprint itself, not for research teams looking for
a production standards-recommendation tool: data stewards and RDM engineers assessing whether R3 is
buildable as specified, and Blueprint maintainers deciding whether to promote any of it out of
`experiments/`. It assumes familiarity with the Blueprint's requirement numbering and reference
architecture; `docs/glossary.md` and `docs/architecture.md` fill in the rest.

## Why R3

This requirement is a suitable target for prototype work for the following reasons:

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

## Architecture

A seven-stage pipeline — **elicit → profile → retrieve → rank → explain → check → output** —
running through all five Blueprint layers. Recommendations and "we found nothing suitable" are equal outputs, and both require human review by the output format itself.

Full detail — outputs, the FAIRsharing integration, evaluation approach and delivery plan — is in [`docs/architecture.md`](docs/architecture.md).

## Project layout

| Path | Contents |
|---|---|
| `src/standards_advisor/` | Package source: `nodes/` (one module per pipeline stage), `models/` (the §6 documents as Pydantic), `profiling/` (§5.1 tier-1, for data that exists), `planning/` (§8, for data that does not), `intake/` (the §8.3 question set), `registry/` (the §7.2 FAIRsharing seam), `provenance/` (run records) |
| `schemas/` | JSON Schema generated from `models/` — never hand-edited |
| `prompts/` | Versioned prompt templates and `manifest.toml` |
| `config/` | Ranking weights and the intake question set, both versioned by filename |
| `samples/` | Example inputs used in the quick start and tests: a collected dataset, and `planned/` for the pre-collection case |
| `tests/` | Test suite (network disabled) |
| `docs/` | `architecture.md` (the design) and `glossary.md` (terms) |
| `scripts/` | Maintenance scripts, e.g. `export_schemas.py` |
| `env.example` | Documented environment variables (copy to `.env`) |

## Installation

Requires Python 3.14 and [`uv`](https://docs.astral.sh/uv/). No API key is required for the current
(profiling-only) functionality; `env.example` documents the variables a future FAIRsharing/model
route will read.

```bash
cd experiments/standards-advisor
uv sync --all-extras
```

## Usage

Run the pipeline against a dataset and its metadata:

```bash
cd experiments/standards-advisor
uv run standards-advisor run samples/soil-chemistry.csv \
  --metadata samples/soil-chemistry.metadata.json
```

### Before any data exists

The Blueprint's first entry point is a researcher starting a project, with a README and a draft
data dictionary and no data (Phase 1, "Pre-collection Setup" — see §8). `plan` serves that case.
It pauses to ask about the project, because with no data the subject and field of research cannot
be inferred at all, and then continues:

```bash
uv run standards-advisor plan \
  --dictionary samples/planned/soil-survey.dictionary.json \
  --readme samples/planned/README.md
```

Supply the answers up front to run without pausing — which is also what makes it scriptable:

```bash
uv run standards-advisor plan \
  --dictionary samples/planned/soil-survey.dictionary.json \
  --readme samples/planned/README.md \
  --answers samples/planned/answers.json
```

A run that paused can be finished later with `standards-advisor resume <run_id>`. The data
dictionary is read as [Frictionless Table Schema](https://specs.frictionlessdata.io/table-schema/);
C5 forbids inventing a format here, and Table Schema is itself a registered standard.

No API key is needed for the current profiling-only functionality; `env.example` documents the
variables a future FAIRsharing/model route will read. See `samples/` for further example inputs and
[`docs/architecture.md`](docs/architecture.md) for the output document format.

## Status

The seven stages exist as a runnable pipeline, but only the two routes into the profile are
genuinely implemented: **§5.1 tier-1 profiling** for data that exists — file formats, column type
inference, counts, all local and with no model involved — and **§8's** reading of a README and a
draft data dictionary for data that does not. There is no FAIRsharing route yet, so every run
declines all four kinds of recommendation and says why. That output is the point: it is honest,
schema-valid, and the baseline every registry route added later has to keep honest.

A pre-collection run declines all four in exactly the same way, and for the same reason. What is
real underneath it is the profile: sixteen planned variables read out of a data dictionary, with
declared date formats, units and permitted values, for a dataset nobody has started collecting.

```bash
uv run pytest
```

The test suite runs with network access disabled; see [Usage](#usage) above to run the pipeline
itself.

This is a technical experiment, and it can fail. §1.2 of the architecture document says what we are
testing and what would make us stop, beginning with three things about FAIRsharing that the design
depends on. **TODO:** the delivery plan and its milestones (M0–M3, referred to from
`docs/glossary.md`) are not written. Whatever they turn out to be, they are a destination rather
than a commitment.

There is no human-subject evaluation: no ethics or approval route is in place, so any measurement
here is mechanical or checked against fixtures we wrote ourselves. Whether the recommendations are
*good* in a data steward's judgement is the obvious next question and deliberately not this
experiment's question. **TODO:** the evaluation approach has not been written up either.

Nothing here is authoritative — see [`experiments/README.md`](../README.md). This experiment has no separate licence, governance or citation metadata; it inherits the repository's.
