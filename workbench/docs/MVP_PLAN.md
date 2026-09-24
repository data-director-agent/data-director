# Data Director Workbench — MVP Software Plan

**Status:** Draft for discussion
**Derived from:** `Data_Director_Development_Environment_Design_and_Delivery_Plan.md` §7A–§7B, §8, §11
**Date:** 4 September 2026

---

## 1. Purpose

Build the smallest Workbench that demonstrates the Data Director contract end to end: one real agent, one non-success path, and a conformance report that says truthfully what is and is not substantiated. Everything not needed for that is deferred, but each deferral leaves behind the interface, schema slot or sentence that lets it arrive later without a migration.

Two rules govern the plan:

1. **Decide formats now; build components later.** Identifiers, envelope shape, trace structure and slot URIs are cheap to fix at v0 and expensive to change once a JSONL store or a conformance report exists. Anything that sits behind an interface can arrive in any version.
2. **Adopt the plumbing; own the governance.** Every layer that moves, validates, traces, renders or measures data has a maintained community implementation. Every layer that decides whether an action is permitted, whether evidence is sufficient, or whether the system should decline has none. Bespoke code is reserved for the second category.

---

## 2. What the MVP delivers

- A LinkML-defined **contract**: the invocation envelope, a minimal `DatasetProfile`, and the outcome vocabulary, with generated JSON Schema and SHACL.
- **R3** (vocabulary/ontology/format recommender) running over FAIRsharing, emitting valid envelopes with evidence hashes and OpenTelemetry spans, with the grounding linter passing over those spans.
- An **abstaining stub agent** that returns `abstained` with a reason code, unconditionally.
- A **read-only shell** that renders both agents' output from schema, with an evidence drawer and an AI-derived/verified badge.
- A **generated `CONFORMANCE.md`** with requirement-to-test traceability and an explicit *unsubstantiated* verdict for any requirement without a passing test.

Not in the MVP: payload editing, feedback capture, streaming, the `suspended` interrupt, ontology term-level retrieval, energy measurement, property-based tests, policy engines, attestations. See §6 and §7.

---

## 3. Architecture

### 3.1 Contract layer (owned; formats decided at v0)

| Element | Decision |
|---|---|
| Schema language | LinkML, generating JSON Schema (for validation and rendering) and SHACL |
| `invocation_id` | UUIDv7 (RFC 9562) — time-ordered, so the append-only JSONL store is sortable without a secondary index |
| `failed` / `suspended` outcomes | RFC 9457 Problem Details object; extension members carry the resumption condition |
| `abstained` / `referred` outcomes | Bespoke, with reason codes. This is the specification contribution (Blueprint §13.2) |
| `DatasetProfile` | LinkML class with only the slots R3 reads — title, description, keywords, discipline, distribution media types, tabular header where present. Every slot has an external `slot_uri` (DCAT / Frictionless), not a Data Director namespace |
| Structured validation output | W3C SHACL Validation Report vocabulary (Frictionless report for tabular). No bespoke `ValidationReport` type. At v0 only JSON Schema validation that fails loudly is implemented |
| `telemetry.energy_estimate_j` / `energy_method` | Slots present; populated `null` / `not_measured` |
| Tier 1 transport | Resolved in ADR-0001 (A2A JSON-RPC binding, with or without a plain REST `POST /invoke` alongside). Other decisions depend on this |

### 3.2 Agents

**R3.** Pipeline: retrieve → rank → explain. Retrieval from FAIRsharing precedes any model call; the LLM explains recommendations and never determines their identity (the grounding invariant). Two backends behind a single retrieval adapter interface:

- **REST** — live and refresh runs
- **Snapshot** — committed file, used in CI and offline

The MCP and Signpost backends from the R3 blueprint are not built. Candidate ranking is bespoke; if lexical scoring is needed, use `rank_bm25` rather than implementing BM25.

**Abstaining stub.** Returns `abstained` unconditionally. Costs about an hour. Guarantees the shell, outcome vocabulary and conformance report are exercised against something other than a successful recommendation, and stops the renderer growing features only one agent needs.

### 3.3 Trace and evidence

- **Trace substrate:** OpenTelemetry SDK, span-tree structure (`invoke_agent` containing retrieval, `chat` and `execute_tool` spans), OTLP/file exporter.
- **Owned attribute set** (about six): operation kind, source identifier, content hash, model identifier, token counts, outcome. The grounding linter reads only these. GenAI semantic-convention alignment is deferred because no `gen_ai.*` attribute is yet Stable.
- **Grounding linter:** bespoke rule over the span tree proving retrieval preceded the model call. The rule is ours; the trace format is not.
- **Evidence hashing:** `content_hash` over the canonicalised retrieved content the grounding claim rests on — not the HTTP body. This stays ours.
- **Record/replay:** VCR.py via `pytest-recording`. Cassettes in version control, credential headers filtered. Replaces the bespoke cassette layer entirely.
- **Provenance:** Process Run Crate via `ro-crate-py` (settled in §7A).

### 3.4 Policy

Declarative YAML institutional profiles (approved repositories, PID systems, actions requiring approval), referenced by `policy_bundle_ref`. Readable and ideally writable by the Library RDM team. Policy gate wiring in the conductor is small and bespoke. Policy engines (OPA, Cedar) are rejected for v0 and recorded as an ADR; if genuine conditional logic appears later, compile YAML to Rego rather than replacing it. The profile README states that the rights and licensing subset will be ODRL when repository selection or deposit arrives.

### 3.5 Shell

- **Protocol:** AG-UI, run-completed events only. With one synchronous agent there is nothing else to carry; streaming and the human-review interrupt arrive with `suspended`.
- **Renderer:** react-jsonschema-form or JSON Forms, driven by the LinkML-generated JSON Schema. No per-agent templates.
- **AI-derived vs verified distinction:** a custom widget plus a `uiSchema` convention, declared per field, so a new agent inherits the treatment by declaring which fields are model-derived.
- **Scope:** render envelope and payload; evidence drawer; badge. Read-only. Workshop participants evaluate a fixed output on paper or in a form; they do not edit it.

### 3.6 Conformance

- pytest tests carrying requirement-identifier markers, example-based at v0.
- `pytest-json-report` for the machine-readable run record (commit, timestamp).
- A small bespoke script applying the traceability rule — a declared requirement with no passing test renders as **unsubstantiated** — and rendering Markdown.
- Output: `CONFORMANCE.md`, published in the repository. A report in which most rows are honestly unsubstantiated is the intended first governance artefact, and the direct counter to unfounded conformance claims.

---

## 4. Dependency rule

External dependencies are held to about eight at v0. Each is placed in one of three tiers, and every ADR carries the line *fallback if this dependency is abandoned*. If the line cannot be filled in, the dependency is in the wrong tier.

| Tier | Rule | v0 members |
|---|---|---|
| Evaluation and CI path | Unconstrained; abandonment does not affect a deployed instance | VCR.py, `pytest-json-report`, Inspect AI |
| Runtime path | Thin internal interface plus named fallback; the conductor calls our interface, the library sits behind it | OpenTelemetry, JSON Schema renderer, `ro-crate-py`, LinkML |
| Rejected for v0 | Not adopted; ADR records the reason | Policy engines, attestation frameworks, general agent frameworks |

---

## 5. Delivery

### 5.1 Milestones

| Milestone | Scope | Estimate |
|---|---|---|
| **D0 — Skeleton** | LinkML schema (envelope, minimal `DatasetProfile`, outcome vocabulary, Problem Details, UUIDv7, energy slots); generated JSON Schema and SHACL; ADR-0001 (Tier 1 transport); ADRs for OpenTelemetry two-stage adoption and YAML-not-OPA; dependency-budget line in the ADR template | 4 pd |
| **D1 — R3 on the harness** | Retrieval adapter interface; FAIRsharing REST and snapshot backends; VCR.py cassettes; OTel span tree with owned attributes; grounding linter; evidence hashing; abstaining stub agent | 4 pd |
| **D2 — Shell** | Read-only schema-driven rendering; evidence drawer; AI-derived/verified `uiSchema` widget; AG-UI run-completed events | 2.5 pd |
| **D3 — Conformance** | Requirement-marked tests; `pytest-json-report`; traceability script and Markdown rendering; `CONFORMANCE.md` published | 2 pd |
| **MVP total** | | **12.5 pd** |

At roughly 3 person-days per month, the MVP lands in **December 2026**. This is inside the six-month pilot but not comfortably, and the §8 trip-wire applies.

### 5.2 RDA Plenary 27 (6–8 October)

About 3 person-days remain before the Plenary. The MVP is not the Plenary artefact and should not be presented as though it will be. What can exist by 6 October:

- D0 complete: the published contract.
- D1 partial: R3 running from the command line over a FAIRsharing snapshot, emitting valid envelopes.
- A generated `CONFORMANCE.md` with most rows honestly marked unsubstantiated.

That is the right thing to show. It makes the case for the traceability rule more clearly than a working shell would.

### 5.3 Verification before the ADRs are written

1. Tier 1 transport and its testing consequence — resolve inside ADR-0001.
2. Whether FAIRsharing publishes an official Python client — before writing a REST client.
3. AG-UI and the JSON Schema renderer — confirm complementary rather than overlapping, and that run-completed events alone suffice for a read-only shell. Fold into the §11.2 half-day spike.

---

## 6. Deferred to v0.2 and later

> **Amended 2026-09-04.** The harness was generalised to many agent kinds before v0.2: polymorphic
> input and payload (ADR-0007), declared grounding modes and a per-mode linter (ADR-0008),
> registered evidence canonicalisations (ADR-0009), and an agent registry with one manifest
> (ADR-0010). R3 is not yet ported to the new interface and is registered as unavailable; its
> tests are xfailed. Two demonstration agents (`quality.reviewer`, `fact.checker`) exercise the
> other grounding modes. Conversation, orchestration and streaming remain deferred.

Each item below has a defined place in the v0 architecture so that adoption is additive.

| Item | Existing option | What v0 carries | Why deferred |
|---|---|---|---|
| Ontology term-level retrieval in R3 | OAK (`oaklib`), `curies`, `bioregistry` | Retrieval adapter interface | FAIRsharing is R3's spine; OAK coverage outside life sciences is unverified against the ORDA corpus |
| GenAI semantic-convention alignment | OTel GenAI conventions via span processor | Owned attribute set | No `gen_ai.*` attribute is Stable; SDKs disagree on names |
| Energy measurement (P14) | EcoLogits (hosted); CodeCarbon / Zeus / NVML (local) | `energy_estimate_j` = `null`, `energy_method` = `not_measured` | Local serving stack not yet chosen |
| Runtime SHACL validation | `pyshacl` | SHACL Validation Report fixed as the format | Nothing yet consumes structured validation output |
| Rights and licensing in the policy bundle | ODRL (donated components) | README sentence | R3 is read-only and advisory; no rights question arises |
| Format identification | PRONOM via Siegfried or fido | Nothing | Format sub-requirement deferred; Siegfried would be the only non-Python CI dependency |
| Property-based contract tests | `hypothesis-jsonschema` (or Schemathesis if REST kept) | Example-based tests; transport fixed in ADR-0001 | Example-based tests suffice for a truthful `CONFORMANCE.md` |
| Payload editing and feedback capture | RJSF / JSON Forms editing mode | Read-only renderer | Workshop does not need it |
| Streaming and `suspended` interrupt | AG-UI full event set | AG-UI declared as the protocol | One synchronous agent; nothing to stream |
| DMP models | RDA DMP Common Standard (maDMP) | Nothing | Adopt when DMP alignment arrives; noted so it is not reinvented |
| **D4 — Evaluation and workshop pack** | Inspect AI over the stratified ORDA corpus, seeded-defect pack, Exercise 4 materials | — | 5 pd, early 2027 |
| **v0.2 total** | | | ~8 pd |

Before v0.2, verify: OAK's disciplinary coverage against the stratified corpus; EcoLogits provider coverage for the chosen local stack; which OTel GenAI schema version to pin.

---

## 7. Rejected for v0 (with reason recorded)

| Item | Reason |
|---|---|
| Policy engines (OPA, Cedar) | Institutional profiles must be legible to data stewards; YAML is, Rego is not. A second language for every contributor to learn |
| Attestations (in-toto, Sigstore) | Right direction, wrong time. One sentence in `CONFORMANCE.md` stating the intent |
| General agent frameworks | See §7A.6 |
| Bespoke cassette layer | VCR.py does it |
| Bespoke `ValidationReport` type | SHACL Validation Report does it |
| Bespoke trace format | OpenTelemetry does it |
| MCP and Signpost FAIRsharing backends | MCP server unconfirmed as public; four backends for one source is three too many |

---

## 8. What stays bespoke

| Component | Why |
|---|---|
| `abstained` and `referred` outcomes with reason codes | The specification contribution; Blueprint §13.2 is open because no standard covers it |
| Grounding linter rule | Domain-specific check over a generic trace substrate |
| Requirement-to-test traceability and the *unsubstantiated* verdict | Addresses the Appendix D conformance-claims problem; no general tool encodes it |
| Policy gate wiring in the conductor | Small; complexity is in profile content, not mechanism |
| `content_hash` over canonicalised evidence | The hash must cover what the grounding claim rests on |
| R3 candidate ranking | Bespoke logic; libraries for scoring primitives |

---

## 9. ADR log at v0

| ADR | Decision |
|---|---|
| 0001 | Tier 1 transport (A2A JSON-RPC; REST `POST /invoke` retained or not) and its testing consequence |
| 0002 | OpenTelemetry as trace substrate, two-stage: structure and owned attributes at v0, GenAI convention normalisation at v0.2 |
| 0003 | YAML institutional profiles; policy engines deferred; compile-to-Rego if conditional logic appears |
| 0004 | UUIDv7 for `invocation_id`; RFC 9457 for `failed` / `suspended` |
| 0005 | `DatasetProfile` as a minimal profile with external slot URIs; SHACL Validation Report as the validation format |
| 0006 | Dependency tiering rule and mandatory fallback line |
