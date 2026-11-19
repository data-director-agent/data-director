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
| `psycopg[binary]` | Harness (`postgres` extra) | `dd_harness.postgres`: the PostgreSQL backend of the run and project storage, in plain SQL ([Storage](storage.md)) | Another PostgreSQL driver behind the same module; the file backends for a single host. |
| `psycopg-pool` | Harness (`postgres` extra) | `dd_harness.postgres`: a pool of connections per store, sized by `DD_POSTGRES_POOL_SIZE` ([Storage](storage.md)) | A connection per call, as before the pool; another pool behind the same module. |
| `watchfiles` | SDK | uvicorn's `--reload`, for development only | uvicorn's polling reloader, which it uses when `watchfiles` is absent. |
| `httpx` | SDK, harness, app, agents | `dd_sdk.delegate`, `dd_sdk.registry` (FAIRsharing's API and pinned archive downloads), `dd_harness.remote`, `dd_harness.identity`, the app's sign-in and feedback modules, each agent's `live` module, the repository advisor's `registry` (the re3data export), the policy advisor's `ror` (the ROR dump and API), `opf` (Jisc Open Policy Finder), `crossref` (Crossref's journals) and `policy_text` (policy pages); `dd_mcp_pid.http`, the PID resolver's client of DataCite, Crossref, ORCID and ROR | `urllib.request`. |
| `rocrate` | Harness | `dd_harness.provenance`; the deposit package in `dd_harness.deposit` | Write `ro-crate-metadata.json` directly. |
| `pyshacl` (with `rdflib`) | Harness | `dd_harness.shacl`, which runs the shapes `dd_harness.deposit` generates from a repository's requirements and the shapes an agent's payload class carries on its card | Checks written in Python that emit the same `sh:` vocabulary. |
| `pyyaml` | Harness, agents | Profile, registry, source and requirement loaders; agents' packaged data | `ruamel.yaml`, or the same documents as JSON. |
| `python-dotenv` | Harness | `dd_harness.settings` | `uv run --env-file`, or variables exported in the shell. |
| `joserfc` | Harness, app | ID-token verification in `dd_harness.identity`; the RS256 JWT a GitHub App presents in `dd_app.github_auth` | Another JOSE library, or RS256 with `cryptography`. |
| `ag-ui-protocol` | Harness | `dd_harness.transport.agui` | The seven pydantic event models the AG-UI binding sends, and an SSE encoder. |
| `pypdf` | Policy advisor | `pdf_text`: the text of a policy published as PDF | No PDF is read: the policy is reported unreadable, and its registry record's obligations stand. |
| `pypdf`, `python-docx` | Harness | `dd_harness.projects.extract`: the text of a PDF or Word document a researcher attaches to a project ([Projects](projects.md), Documentation) | That kind of file is refused, saying the deployment cannot read it; a document may still be attached as text or Markdown. |
| `rank-bm25` (with numpy) | Retrieving agents | Each agent's `snapshot` module | About forty lines of BM25. |
| `anthropic` | SDK (optional `anthropic` extra), which each model-backed adviser's `model` extra and the orchestrator install | `dd_sdk.model_anthropic`, the Claude adapter behind `dd_sdk.model` | The rule-based orchestrator stub, an adviser's template explainer or the editor's template writer; another adapter behind `dd_sdk.model`; any HTTP client against the Messages API. |
| `openai` | SDK (optional `openai` extra), which each model-backed adviser's `model` extra and the orchestrator install | `dd_sdk.model_openai`, the adapter behind `dd_sdk.model` for any OpenAI-compatible Chat Completions endpoint: OpenAI, Gemini, a local server or a gateway | Another adapter behind `dd_sdk.model`; an `httpx` call to `{base}/chat/completions`, which is one request and one response. |
| `mcp` (with `mcp-types` and `httpx2`) | SDK (optional `tools` extra), harness (optional `gateway` extra, pinned to a minor version) | `dd_sdk.tools_client`, an agent's client of the tool gateway; `dd_harness.gateway.upstream`, the gateway's client of each MCP server; `dd_harness.gateway.endpoint`, the gateway's MCP endpoint, which uses the SDK's per-request entry for the stateless transport from a private module, hence the pin ([Agents](agents.md#tools-mcp-servers-and-agent-skills)); `dd_mcp_pid.app`, the PID resolver's servers, through the SDK's public session manager, pinned to the gateway's minor version since the gateway is its client | JSON-RPC 2.0 over `httpx`: the gateway's endpoint answers `tools/list` and `tools/call` with one JSON response each, and a server is reached the same way. The records, their hashes and `tool_retrievals` do not change. |
| `opf-fido` | `dd-inventory` | `dd_inventory.identify` | Media types from file extensions, with no PRONOM identifier. |
| `frictionless` | `dd-inventory` | `dd_inventory.tables` | The researcher gives a table's fields by hand. |
| `presidio-analyzer`, pinned exactly (pattern recognisers only; it installs `spacy`, which the command does not use, and the browser bundle replaces with a stand-in), with `tldextract` given only its bundled public-suffix list | `dd-inventory` | `dd_inventory.personal`, behind its `Detector` protocol ([Personal data and disclosure control](personal-data.md)) | Another local detector behind the same protocol (#39 compares GLiNER-PII and others); failing that, the keyword table for field and file names alone, with the limitations saying values were not checked. |
| `detect-secrets`, pinned exactly (its named plugins only; its last release, 1.5.0, was in May 2024) | App | `dd_app.documentation_check`, for secrets in an attached document (#473) | Patterns of our own for the keys and tokens of known services; failing that, no secret check, and the dialog says only personal data was looked for. |
| `acro` (with `pandas`) | `dd-inventory` (planned, #611, #612) | `dd_inventory.summaries`, `dd_inventory.quasi` | The thresholds, suppression and rounding in [Personal data and disclosure control](personal-data.md) written in Python; failing that, no summary values, as before #611. |
| `react`, `react-dom` | App shell | The shell's components | Preact with `preact/compat`. |
| `react-aria-components` | App shell | The few widgets that need an ARIA pattern | The WAI-ARIA Authoring Practices patterns by hand, or Radix primitives. |
| `react-markdown`, `remark-gfm` | App shell | `ui/Markdown`, the one component that renders Markdown: an agent's reply or a drafted document | Another sanitising Markdown renderer, or plain text with its line breaks kept. |
| `lucide-react` | App shell | Icons | Inline SVG. |
| `@ag-ui/client` (with `rxjs`) | App shell | `run/transport` and `run/cassette`: `HttpAgent` for a live turn's stream, and `CassetteAgent`, an `AbstractAgent` that replays a recorded one | `fetch` and the stream's `text/event-stream` lines parsed by hand into the run reducer. |
| `@fontsource-variable/inter` | App shell | The stylesheet's font stack | The system font stack. |

Validation against SHACL shapes uses `pyshacl` in the harness only, behind its one validation
module, `dd_harness.shacl`, which deposit validation ([Deposit](deposit.md)) and the conductor's
shape check ([Contract](contract.md)) both call. The SDK generates the shapes with LinkML's
`gen-shacl` at development time, and reads a payload as JSON-LD without an RDF library, so it adds
no runtime dependency.

### Evaluation and CI

Unconstrained, and listed so that nothing moves into the runtime tier unnoticed: `pytest` and
its plugins, `linkml` (schema generation only; the generated files are committed, so runtime code
never imports it), `roc-validator` (the RO-Crate validator, which a harness test runs on the
deposit package), `ruff`, `mypy` and its stubs, `inspect-ai` (the workbench's `eval` extra),
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
- **re3data's REST API at run time.** The repository advisor reads re3data's monthly export,
  pinned and built into a local registry, so every record it cites can be verified and a run
  makes no request to re3data. The API's search returns identifiers only, and each record cost
  one more request.
  ROR is different, and the policy advisor may ask its API (`DD_POLICY_ROR=live`): one search
  returns whole records, a new organisation can appear there before the next dump, and the route
  falls back to the registry built from the pinned dump, which is the default. Evidence from the
  live route is cited as `ror:live:<date>`, which no deployment pins, so the source check reports
  it unresolved, as it does FAIRsharing's live route.
  Jisc Open Policy Finder and Crossref's journals API are read live only, by the policy advisor
  (#302, #905). Open Policy Finder states no licence for its records that would let a copy be
  committed, nor a rate limit, so there is no pinned copy to fall back to: when its route fails,
  or no key is given, the run says so and FAIRsharing still answers. Crossref is asked only for
  the publisher a journal belongs to. Their evidence is cited as `open-policy-finder:live:<date>`
  and `crossref-journals:live:<date>`, which the source check reports unresolved. TODO(#952):
  revisit a pinned copy once Jisc's terms for the data are known.
- **`any-llm`, LiteLLM's SDK or `pydantic-ai` as the model layer.** Each puts its own abstraction
  over many providers where `dd_sdk.model` already is one, and `any-llm` installs each provider's
  SDK beneath it anyway. The OpenAI-compatible Chat Completions format is the shared, open
  interface: OpenAI, Gemini, local servers (Ollama, vLLM, llama.cpp, LM Studio) and gateways all
  serve it, so one adapter (`dd_sdk.model_openai`) reaches them. The LiteLLM proxy remains an
  optional gateway a deployment may run (`deploy/llm-gateway/`). Open Responses, a newer open
  specification, is not yet served as widely.
- **Gradio and `pydantic-ai`** for the app. The app is a shell drawn from agent manifests
  ([The app](app.md)) and runs no agent in its own process.
- **Vendoring** a library to keep the runtime tier short. A vendored copy is an unmaintained
  dependency that the register no longer shows.

## Non-functional requirements

- A deployed instance needs only its runtime tier. Nothing in the evaluation tier may be
  imported on a runtime path; a module that imports one is in the wrong package.
- The workbench viewer still loads its browser libraries from a CDN at run time. It is a
  development tool, not a deployed component, but this is to be removed: TODO(#84).
