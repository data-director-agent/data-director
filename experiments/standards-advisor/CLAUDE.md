# standards-advisor

A prototype of Blueprint requirement **R3** — recommending controlled vocabularies, ontologies, and
open data formats. `docs/architecture.md` is the design; `docs/glossary.md` defines terms.

It serves two of the Blueprint's entry points: a dataset that exists (§5.1), and a project about to
start, with a README and a draft data dictionary and no data at all (§8, Blueprint Phase 1).

Two invariants drive the whole design and should be respected in any work here:

- **Nothing leaves the system that isn't grounded.** Every recommendation must trace to a real
  FAIRsharing record an actual query returned, checked mechanically after the fact (§5.5). The model
  may direct retrieval and weigh in on ranking (§5.6) — it is not confined to writing explanations —
  but it cannot make a made-up standard pass the grounding check. This is what makes failures
  diagnosable rather than embarrassing.
- **Abstention is a first-class output** (R3.6). "No suitable resource exists" is an equal output to
  a recommendation, not an error path.

Sections are cross-referenced by number — preserve `§n` numbering when editing `architecture.md`.

## Working on the code

Python 3.14, `uv`, LangChain/LangGraph v1. All of it lives in this directory; **nothing goes at the
repository root** (see the root `CLAUDE.md`).

```bash
uv sync --all-extras
uv run pytest                                   # network disabled; no API key needed
uv run ruff check . && uv run ruff format .
uv run mypy                                     # strict, and currently clean
uv run python scripts/export_schemas.py         # after changing any model in models/
```

Where things are: `nodes/` one module per stage, `models/` the §6 documents as Pydantic (the source
of truth for `schemas/`), `profiling/` tier 1 for data that exists (§5.1), `planning/` the same job
from a README and a data dictionary for data that does not (§8), `intake/` the versioned question
set, `registry/` the §7.2 seam, `provenance/` the run record.

**`DatasetProfile` is the pipeline's only interface to the input.** Nothing after the profile stage
reads `DatasetInput` or touches the filesystem, which is why §8 is a second *producer* of that
document rather than a second pipeline. Keep it that way.

Eight things are load-bearing and easy to break by accident:

- **`schemas/` is generated.** Never hand-edit; change the Pydantic model and regenerate.
  `test_schemas_current` byte-compares.
- **A rule with missing inputs returns `None` (skipped), never `0.0`** (§7.2, `ranking/rules.py`).
- **Exceptions are for programmer and configuration errors only.** Content problems — nothing
  retrieved, a response that will not parse, a dropped recommendation — go into `state["failures"]`
  and the output document. A run that declines everything exits 0. See `errors.py`.
- **Only column *metadata* may reach a model** — names, inferred types, counts (§1.4).
  `nodes/explain.py::_profile_digest` is the chokepoint, and a test asserts it. The line is
  **declared schema versus observed data**: a data dictionary's `permitted_values` and
  `description` may go, because a codebook is a statement of intent the researcher wrote;
  `example_values` never may, because those were read out of a real file. The two are separate
  fields so the chokepoint can tell them apart.
- **Prompts, ranking weights and the intake question set are versioned by file, with hashes.** To
  change one, add a new version alongside the old and repoint `prompts/manifest.toml` (or the
  `DD_*_CONFIG` name); editing in place is a hard failure.
- **Nothing before an `interrupt()` may be non-deterministic or have side effects.** LangGraph
  re-runs a paused node from the top, so the intake questions are fixed configuration rather than
  anything a model writes — otherwise a researcher could answer one set of questions and have the
  answers matched against another. See `nodes/elicit.py`.
- **A pause is control flow, not a stage outcome.** LangGraph's signals inherit from `Exception`,
  so `nodes/support.py::stage` catches `GraphBubbleUp` first and re-raises it untouched. Without
  that clause a pause is recorded as a degraded stage and written to disk twice.
- **Adding a stage means six places, not one:** `StageName` (declaration order *is* pipeline
  order), `graph.PIPELINE_ORDER`, `graph.build_graph`'s explicit `add_node` calls,
  `nodes.support.STAGE_ORDER`, `state.PipelineState` *and* `state.initial_state`, and
  `provenance/prov.py`'s stage-to-entity mapping.

Environment variables are documented in `env.example` (named without the leading dot on purpose).
`DD_REGISTRY_ROUTE` defaults to `empty`, which refuses to search rather than returning no results —
so the abstention says "we could not look", not "we looked and found nothing".
