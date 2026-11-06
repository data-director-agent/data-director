# Dependencies

## Intent and scope

Data Director adopts maintained community libraries for everything that moves, validates,
traces, renders or measures data. It writes its own code only where a decision is made: whether
an action is permitted, whether evidence suffices, whether to decline. Adopted libraries can be
abandoned, change licence or turn hostile, and an instance at a university may have to run for
years on what it was deployed with. This spec keeps the loss of any one library a local problem.

It covers every external dependency of every workspace member and of `app/web`. Standard library
modules are not dependencies here.

## Invariants

1. Every external dependency is in exactly one tier:

   | Tier | Rule |
   |---|---|
   | **Evaluation and CI** | Unconstrained. Losing it does not affect a deployed instance. |
   | **Runtime** | Sits behind a thin internal interface (one module, or one module per package that uses it) and has a named fallback. Our code calls the interface; the library sits behind it. |
   | **Rejected** | Not adopted; the reason is recorded below. |

2. A runtime dependency has a fallback that can be written down: what replaces it, and which
   interface keeps the replacement local. If no fallback can be written, the dependency is in the
   wrong tier, and a reviewer rejects the pull request that adds it.
3. The register below is the dependency budget. A pull request that adds, removes or re-tiers a
   dependency edits the register in the same change.
4. A dependency is declared by the workspace member that imports it, and only that member
   (see [System and boundaries](system.md)). A runtime dependency used only for one command or
   one package (`dd-inventory`, an agent) is declared there and nowhere else. CI runs
   `scripts/check_dependencies.py`, which runs [deptry](https://deptry.com) once per member in the
   workspace environment and fails on an import the member does not declare, a declared package it
   never imports, and a package it reaches only through another. The first-party members are the
   business of `scripts/check_boundaries.py`; deptry covers everything else. A deliberate
   exception is a `[tool.deptry.per_rule_ignores]` entry in the member's `pyproject.toml`, with the
   reason beside it; a package whose import name differs from its distribution name is mapped in
   `IMPORT_NAMES` in the script, never ignored.
5. Our own fixed formats never depend on a library's representation. Envelopes, evidence and
   span records are plain documents that survive the library that produced them, which is what
   makes each fallback possible.

## The register

### Runtime

| Dependency | Used by | Interface | Fallback |
|---|---|---|---|
| `pydantic` | SDK, harness, workbench, agents | `dd_sdk.contract.models`; each agent's class module | Dataclasses checked against the generated JSON Schema. |
| `jsonschema` | SDK | `dd_sdk.contract.validate` | `fastjsonschema`, at the same single call site. |
| `opentelemetry-sdk`, `opentelemetry-api` | SDK, harness | `dd_sdk.tracing` (span helpers); the trace-context propagator in the A2A client and server | Write the owned span attributes to a JSON-lines file directly; the linter reads plain span records, not SDK objects. `traceparent` is a W3C format that can be written and parsed by hand. |
| `a2a-sdk[http-server]` | SDK, harness | `dd_sdk.serve`, `dd_sdk.delegate`; `dd_harness.remote`, `dd_harness.transport.a2a` | A hand-written JSON-RPC 2.0 `message/send` client and handler over httpx and Starlette. The request and envelope documents do not change. |
| `protobuf` | SDK, harness | `dd_sdk.serve`, `dd_harness.transport.a2a`: A2A messages to and from plain documents | Whatever `a2a-sdk` uses; it is declared because the code imports it directly. |
| `starlette` | SDK, harness, workbench, app | The ASGI applications in `dd_sdk.serve`, `dd_harness.server`, `dd_app.app` | Any ASGI framework; each application is a handful of routes. |
| `uvicorn` | SDK, harness (`serve` extra), workbench, app | The `serve` commands | Any ASGI server. |
| `watchfiles` | SDK | uvicorn's `--reload`, for development only | uvicorn's polling reloader, which it uses when `watchfiles` is absent. |
| `httpx` | SDK, harness, app, agents | `dd_sdk.delegate`, `dd_harness.remote`, `dd_harness.identity`, the app's sign-in and feedback modules, each agent's `live` module | `urllib.request`. |
| `rocrate` | Harness | `dd_harness.provenance` | Write `ro-crate-metadata.json` directly. |
| `pyyaml` | Harness, agents | Profile, registry, source and requirement loaders; agents' packaged data | `ruamel.yaml`, or the same documents as JSON. |
| `python-dotenv` | Harness | `dd_harness.settings` | `uv run --env-file`, or variables exported in the shell. |
| `joserfc` | Harness | ID-token verification in `dd_harness.identity` | Another JOSE library, or RS256 verification with `cryptography`. |
| `ag-ui-protocol` | Workbench | `workbench.transport.agui` | Two pydantic event models and an SSE encoder. |
| `rank-bm25` (with numpy) | Retrieving agents | Each agent's `snapshot` module | About forty lines of BM25. |
| `anthropic` | Orchestrator (required); retrieving advisers (optional extra) | `dd_agent_orchestrator_model.model`; each adviser's `explain` module | The rule-based orchestrator stub, or an adviser's template explainer; any HTTP client against the Messages API. |
| `opf-fido` | `dd-inventory` | `dd_inventory.identify` | Media types from file extensions, with no PRONOM identifier. |
| `frictionless` | `dd-inventory` | `dd_inventory.tables` | The researcher gives a table's fields by hand. |
| `react`, `react-dom` | App shell | The shell's components | Preact with `preact/compat`. |
| `react-aria-components` | App shell | The few widgets that need an ARIA pattern | The WAI-ARIA Authoring Practices patterns by hand, or Radix primitives. |
| `react-markdown`, `remark-gfm` | App shell | `ui/Markdown`, the one component that renders Markdown: an agent's reply or a drafted document | Another sanitising Markdown renderer, or plain text with its line breaks kept. |
| `lucide-react` | App shell | Icons | Inline SVG. |
| `@fontsource-variable/inter` | App shell | The stylesheet's font stack | The system font stack. |

Validation against SHACL shapes is meant to use `pyshacl` in the harness only, behind its one
validation module, with checks written in Python that emit the same `sh:` vocabulary as the
fallback. It is not yet declared, because validation is not yet built: TODO(#19).

### Evaluation and CI

Unconstrained, and listed so that nothing moves into the runtime tier unnoticed: `pytest` and
its plugins, `linkml` (schema generation only; the generated files are committed, so runtime code
never imports it), `rdflib` (harness tests that read a disclosure's PROV-O graph as RDF), `ruff`,
`mypy` and its stubs, `inspect-ai` (the workbench's `eval` extra),
MkDocs and its theme, and the shell's build and test tools (`vite`, `typescript`, `vitest`,
Testing Library, `jsdom`, `jest-axe`, Playwright, axe-core, ESLint, Stylelint).

Which licences are acceptable is not yet decided or enforced: TODO(#82).

## Rejected alternatives

- **OPA, Cedar or another policy engine.** Institutional policy is a declarative profile read by
  our own gate ([Policy and identity](policy-and-identity.md)); an engine adds a language and a
  runtime for rules that are currently lookups.
- **LangChain, LangGraph or another agent framework.** The harness must see and govern every
  step an agent takes, through one contract it owns. A framework would own the loop and hide
  steps behind its abstractions, and would couple every agent to its release cycle.
- **in-toto or Sigstore**, for now. The run record is RO-Crate written by the harness
  ([Contract](contract.md)). The intent is to attest the conformance report with one of them once
  the project has a release process, since an attestation names a commit that already exists.
- **A bespoke trace format or cassette layer.** OpenTelemetry and `pytest-recording` already do
  this, and a format of our own would be one more fixed format to maintain.
- **A JCS (RFC 8785) library** for evidence canonicalisation. For documents of strings, lists of
  strings and nulls, sorted-key `json.dumps` gives the same bytes. Documents that carry numbers
  reopen the question ([Evidence and grounding](grounding.md)).
- **`authlib`** for ID tokens. `joserfc` is that project's JOSE core alone, typed, with no web
  framework attached.
- **MCP or Signpost back ends for FAIRsharing.** Agents read a pinned snapshot and the live REST
  API. Whether the official MCP server changes this is open: TODO(#8).
- **Gradio and `pydantic-ai`** for the app. The app is a shell drawn from agent manifests
  ([The app](app.md)) and runs no agent in its own process.
- **Vendoring** a library to keep the runtime tier short. A vendored copy is an unmaintained
  dependency that the register no longer shows.

## Non-functional requirements

- A deployed instance needs only its runtime tier. Nothing in the evaluation tier may be
  imported on a runtime path; a module that imports one is in the wrong package.
- The workbench viewer still loads its browser libraries from a CDN at run time. It is a
  development tool, not a deployed component, but this is to be removed: TODO(#84).
