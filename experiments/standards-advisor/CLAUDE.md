# standards-advisor

A prototype of Blueprint requirement **R3** — recommending controlled vocabularies, ontologies, and
open data formats. `docs/architecture.md` is the design; `docs/glossary.md` defines terms.

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

Python 3.12, `uv`, LangChain/LangGraph v1. All of it lives in this directory; **nothing goes at the
repository root** (see the root `CLAUDE.md`).

```bash
uv sync --all-extras
uv run pytest                                   # network disabled; no API key needed
uv run ruff check . && uv run ruff format .
uv run mypy                                     # strict, and currently clean
uv run python scripts/export_schemas.py         # after changing any model in models/
```

Where things are: `nodes/` one module per stage, `models/` the §6 documents as Pydantic (the source
of truth for `schemas/`), `profiling/` the only fully implemented subsystem (§5.1 tier 1),
`registry/` the §7.2 seam, `provenance/` the run record.

Five things are load-bearing and easy to break by accident:

- **`schemas/` is generated.** Never hand-edit; change the Pydantic model and regenerate.
  `test_schemas_current` byte-compares.
- **A rule with missing inputs returns `None` (skipped), never `0.0`** (§7.2, `ranking/rules.py`).
- **Exceptions are for programmer and configuration errors only.** Content problems — nothing
  retrieved, a response that will not parse, a dropped recommendation — go into `state["failures"]`
  and the output document. A run that declines everything exits 0. See `errors.py`.
- **Only column *metadata* may reach a model** — names, inferred types, counts. Never sample values
  (§1.4). `nodes/explain.py::_profile_digest` is the chokepoint, and a test asserts it.
- **Prompts and ranking weights are versioned by file, with hashes.** To change one, add a new
  version alongside the old and repoint `prompts/manifest.toml`; editing in place is a hard failure.

Environment variables are documented in `env.example` (named without the leading dot on purpose).
`DD_REGISTRY_ROUTE` defaults to `empty`, which refuses to search rather than returning no results —
so the abstention says "we could not look", not "we looked and found nothing".
