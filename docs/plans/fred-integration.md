# Plan: integrating FRED (FAIRsharing Record Exploration and Discovery)

Status: draft for discussion. Nothing here is built. It answers TODO(#8), whether the official
FAIRsharing MCP server changes how agents reach FAIRsharing, and it is the first real consumer
of the tool gateway that TODO(#1143) calls for.

## 1. What FRED is, and what we do not yet know

FRED is an open-source MCP server built by the FAIRsharing team with the Oxford AI Competency
Centre. It lets a model ask structured questions of FAIRsharing's linked records, such as which
repositories implement which standards and which policies require them. It supersedes FAIRsharing's
earlier GraphQL-based approach. It is hosted at <https://mcp.fairsharing.org/>.

Facts checked on 2026-11-19:

- The root of `mcp.fairsharing.org` serves a Streamlit chat page, so it is a human front end.
- `/mcp`, `/sse`, `/health` and `/.well-known/mcp` all return the same page, and a POST to `/mcp`
  returns 405. **The machine endpoint is therefore not discoverable from outside.**

Related, from #8: FAIRsharing also publishes
[FAIRsharing/fairsharing-mcp](https://github.com/FAIRsharing/fairsharing-mcp), which wraps the
GraphQL API in 97 tools, authenticates with a free API key and is licensed under the GPL. It is not
yet known whether FRED is that server hosted, a fork of it, or a separate build. If FRED is
GPL-licensed, we may run it as a separate process but must not import or vendor it into our MIT
code (#8 asks for that decision). Phase 0 is the spike #8 already describes, widened to FRED.

Open questions, all of which block the design below. Each goes to the FAIRsharing team before
any code is written:

| # | Question | Why it matters |
|---|---|---|
| Q1 | What is the streamable-HTTP endpoint, and is it stateless? | The gateway's upstream client needs the URL (`servers[].url`). |
| Q2 | Which tools exist, and does each declare an `outputSchema` and return `structuredContent`? | The gateway grounds only structured results with an identifier per record (specs/agents.md, item 5). Prose answers are never evidence. |
| Q3 | Does a record carry the FAIRsharing identifier (DOI or numeric id), and is it the same record shape the snapshot holds? | Decides the `id_field` and whether `json-sorted-utf8-v1` can be reused. |
| Q4 | Is authentication needed, and does the existing FAIRsharing login apply? | Decides credential handling (security.md, TODO(#883)). |
| Q5 | Licence and terms for the returned records, rate limits and an SLA. | The snapshot is CC BY-SA 4.0. Pinning, caching and quoting depend on the answer. |
| Q6 | Is a pinned or versioned copy of the data behind the server available? | Without one, the source check cannot resolve `tool:fairsharing/<id>` and runs stay unresolved. |
| Q8 | What is FRED's relationship to `fairsharing-mcp`, and what is its licence? | Decides whether we may only run it, or also reuse code (#8). |
| Q7 | Does FRED expose natural-language tools (an LLM inside the server)? | A server that calls its own model sends our query text to a further third party. |

## 2. Decision: FRED is an MCP source behind the gateway, not a persona

The repository already decides this (specs/system.md, specs/agents.md):

- A source useful without our contract is a framework-neutral MCP server; the agent is a thin
  wrapper that adds classes, grounding and evidence. FRED is exactly that, and it is not ours.
- A persona reaches a server only through `dd_harness.gateway`, under a grant. It never connects
  itself, and `mcp` is imported only in the gateway.
- Only the gateway fills `tool_retrievals`. The conductor, not the agent, hashes the records.

So FRED is **not** a new agent, and it is **not** exposed to researchers as a free-form chat tool.
Its conversational interface is for FAIRsharing's own users. For us it supplies structured,
auditable lookups to the existing advisers.

## 3. Where it helps

| Agent | Today | With FRED |
|---|---|---|
| `advisor.standards` | BM25 over a 169-record snapshot, or the REST search (needs a login, no cassette, unresolved) | Relational queries: standards used by a named repository, standards that implement a given format, standards in a subject area. Fills the live route that has no resolver (TODO(#246)). |
| `advisor.policy` | FAIRsharing policy records via REST and a snapshot | Policies by funder or journal, and the standards and repositories each recommends or requires. |
| `advisor.repository` | re3data export, with FAIRsharing as a secondary source | Which repositories implement the standards the standards adviser chose, which is the Phase 2 to Phase 3 hand-off. |

Start with `advisor.standards`: it has the clearest gap and the smallest surface.

## 4. Phases

Each phase is its own pull request and its own issue, sized M or smaller, with acceptance
criteria written when the issue is made. Issue numbers are to be filed; none is invented here.

### Phase 0: Discovery (no code)

- Get answers to Q1 to Q8 from FAIRsharing. Record them in an RFC or a spec change, as the
  planning guide requires for a decision that others depend on.
- Run `tools/list` against the real endpoint from a development machine. Save the tool
  definitions as a fixture.
- Outcome: go or no-go for Phase 1, and the list of tools worth granting.

### Phase 1: Register FRED with the gateway

- Add a `fairsharing` entry to a deployment's tools file (`DD_TOOLS_CONFIG`):
  `url`, `id_field`, `canonicalisation: json-sorted-utf8-v1` (or a new registered name if Q3
  shows a different record shape), `snapshot_ref` if Q6 allows, and `tools_sha256` from
  `dd-harness tools pins`.
- It is `remote`, so `remote_tool_content` in the profile decides what may go to it. Keep the
  default, under which no `researcher` facts go to a remote tool server.
- Add `config/examples/tools.yaml` and a section in `docs/guide/operations/configuration.md`.
- Add an in-process double of FRED to `dd_harness.testing.tools` with the recorded tool
  definitions, so CI never calls the network.
- Acceptance: the gateway lists `fairsharing.<tool>`, refuses an ungranted call, and marks the
  server unavailable when the pinned digest differs.

### Phase 2: Move `advisor.standards` onto it (closes the standards half of TODO(#1143))

- Declare the FRED tools on the card (`AgentSpec.tools`) and grant them in the profile
  (`tool_servers`).
- The deterministic shell makes the first retrieval through `ctx.tools`. The model gets only
  read-only follow-up tools, limited by `DD_STANDARDS_MAX_LOOKUPS`.
- Cite `tool:fairsharing/<id>` from the conductor's `tool_retrievals`; remove the agent's own
  `retrieval` span for the live route.
- Keep the snapshot as the default and the fallback. The adviser reads it under one `retrieval`
  span when no server is granted, as `advisor.rights` does with its packaged table.
- Tool results reach the model as numbered, untrusted records in the user turn, never in the
  system prompt.
- Acceptance: with a double, a run cites only gateway-recorded records; a profile that grants no
  `fairsharing` server still runs from the snapshot and says so in `limitations`; `uv run pytest`
  passes with the network blocked.

### Phase 3: Policy and repository advisers

Repeat Phase 2 for `advisor.policy` (policy records and their linked standards) and
`advisor.repository` (repositories by implemented standard). Do these one at a time.

### Phase 4: Evaluation and conformance

- Extend the seeded-defect evaluation with cases where the relational answer differs from the
  lexical one. Evaluation is not conformance; baselines change in their own commit.
- Record one real, redacted cassette of a live run, which retires the "live search unsubstantiated"
  note in `CONFORMANCE.md`. Do not edit that file by hand.
- Compare snapshot, REST and FRED on the same cases for precision and cost.

### Phase 5: Retire or keep the older routes

Decide with evidence from Phase 4 whether the REST search in `dd_sdk.registry.fairsharing` stays
as a fallback. The dependency register's "rejected" entry for MCP back ends for FAIRsharing
(docs/specs/dependencies.md) is replaced in the same pull request that adds FRED, whichever way
that goes.

## 5. Risks and mitigations

| Risk | Mitigation |
|---|---|
| FRED returns prose, not records | Phase 0 stops here. Fallback: ask FAIRsharing for structured tools, or keep the REST route. Never ground on free text. |
| Tool descriptions change under us (prompt injection by drift) | Pinned `tools_sha256`; a changed list makes the server unavailable until reviewed. |
| Third-party availability | Snapshot fallback stays; the run reports the fallback and marks the snapshot reference stale. |
| Query text leaves the institution | Server is `remote`; `remote_tool_content` governs it; send search terms only, never data values. Disclose it in the agent's About text. |
| Records cannot be verified later | Needs Q6. Without a pinned copy, evidence is `tool:` sourced and reported unresolved, as live routes are today. State this plainly. |
| Terms of use | Q5 before any caching or committed fixtures. Fixtures hold identifiers and short projections only. |
| Upstream is an LLM-backed service | Q7. If so, treat its output as untrusted and do not rely on its ordering. |

## 6. Governance checklist for the pull requests

- Edit `docs/specs/agents.md`, `grounding.md` and `dependencies.md` in the same pull request as
  the behaviour they describe; a new canonicalisation goes in `dd_sdk.evidence.CANONICALISATIONS`.
- No agent imports `mcp`; only the gateway does. Run `scripts/check_boundaries.py` and
  `scripts/check_dependencies.py`.
- Policy choices go in the institutional profile, not an environment variable.
- Pull request titles are Conventional Commits, for example
  `feat(harness): Register the FRED server with the tool gateway`.
- Mark every open item with a to-do marker that names a real issue (AGENTS.md), and file the Phase 0 to 4 issues first.

## 7. Immediate next steps

1. Contact the FAIRsharing and Oxford team with Q1 to Q8.
2. File one issue per phase and link them to #8 and #1143.
3. Do Phase 0, then decide go or no-go before any code.
