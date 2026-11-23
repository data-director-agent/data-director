# mcp-pid: a PID resolver MCP server

A read-only [MCP](https://modelcontextprotocol.io) server that resolves persistent identifiers to
small structured records an agent can cite:

| Server path | Tool | Resolves | Through |
|---|---|---|---|
| `/datacite/mcp` | `get_doi` | a DOI DataCite registered | [DataCite REST API](https://support.datacite.org/docs/api) |
| `/crossref/mcp` | `get_doi` | a DOI Crossref registered | [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/) |
| `/orcid/mcp` | `get_orcid` | an ORCID iD, to the person's public name | [ORCID public API v3.0](https://info.orcid.org/documentation/features/public-api/) |
| `/ror/mcp` | `get_organisation` | a ROR identifier | a pinned [ROR data dump](https://doi.org/10.5281/zenodo.6347574), then [ROR's API](https://ror.readme.io/v2/docs/rest-api) |
| `/ror/mcp` | `search_organisations` | an organisation's exact name, acronym or alias | the same |
| `/journals/mcp` | `get_journal` | an ISSN (print, online or linking), to its journal | the [`dd-journals`](../journals/README.md) registry, built from a pinned [OpenAlex](https://openalex.org) snapshot |
| `/journals/mcp` | `search_journals` | a journal's title, the start of one, or an ISSN, to up to 10 journals, likeliest first | the same |

It is framework-neutral ([System](../docs/specs/system.md)): it imports nothing of the Data
Director but [`dd-journals`](../journals/README.md) and
[`dd-registry-cache`](../registry-cache/README.md), standard-library-only libraries each published
on their own, so it can be published on its own too. In the Data Director it sits behind the harness's
tool gateway, which pins each server's tools and records every record an agent reads
([Agents](../docs/specs/agents.md#tools-mcp-servers-and-agent-skills)). The Linking Adviser
(`advisor.linking`) is the first agent to use it (#953, #360).

## Answers

Each tool takes one string and answers `structuredContent` of the form `{"records": [...]}`,
valid against the tool's `outputSchema`, with a one-line summary as text:

- **Found:** the record. `search_organisations` lists every match.
- **Not found:** no records. A DOI one agency did not register is not found there, so ask the
  other agency. A miss is an empty list rather than text alone because an MCP client refuses a
  tool that declares an output schema and answers without structured content.
- **Error** (`isError`): the input is not that kind of identifier, or the registry could not be
  asked and the cache holds no answer. Busy or failing services are retried twice first. Offline,
  an identifier the server holds no answer for is an error, never "not found".

Records are identified at their top level: `doi` (bare and lower-case), `orcid` (as a URL), `id`
(the ROR URL) or `issn_l` (the journal's linking ISSN). They hold no integers: a publication year is text.

Each server is a separate path because a client such as the gateway identifies a server's records
by one field.

## Caching and offline

Each answer from DataCite, Crossref, ORCID or ROR's API is kept in a cache
([`dd-registry-cache`](../registry-cache/README.md)), keyed by registry and normalised identifier,
so that the same identifier is not asked for again within its time to live (Blueprint P14):

- A found record is kept for 7 days and a miss for 1 hour (`DD_PID_CACHE_TTL_FOUND`,
  `DD_PID_CACHE_TTL_MISSING`). An error is never kept.
- A record is stored as its document in canonical JSON and read back through its model. A cached
  record is therefore the same document as a fresh one and hashes the same.
- The summary names where an answer came from: the registry; `from the cache (checked …)`; or
  `from the cache, expired (checked …)` when the registry cannot be asked and only an expired
  answer is held.
- Organisation searches are not cached; ROR's dump answers them.
- In `DD_PID_CACHE_DIR` the cache is a file (`pid.sqlite3`), which survives restarts. Unset, it is
  kept in memory. To clear it, use `dd-registry-cache clear <DD_PID_CACHE_DIR>/pid.sqlite3`.

With `DD_PID_OFFLINE=1`, as in an air-gapped deployment (#792), no registry is asked. ROR is read
from the dump, and everything else from the cache, however old the entry is. An identifier that
neither holds is reported as unavailable (`isError`), never as not found.

## What is sent, and to whom

| Registry | What a query sends | Terms | Limits |
|---|---|---|---|
| DataCite | the DOI | metadata [CC0](https://support.datacite.org/docs/datacite-data-file-use-policy) | no key; rate-limited per IP |
| Crossref | the DOI | metadata openly available, facts not copyrightable ([terms](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)) | no key; the public pool is rate-limited |
| ORCID | the iD | public data; ORCID's [public API terms](https://info.orcid.org/public-client-terms-of-service/) | no key for single records |
| ROR | the identifier, or the name searched for, and only when the dump cannot answer; the operators' client ID, if one is configured | [CC0](https://ror.org/about/faqs/) | from Q3 2026, 50 requests in 5 minutes without a client ID, 2,000 with one |
| Journals (OpenAlex) | nothing: the registry is local | [CC0](https://help.openalex.org/access/snapshot/) | none |
| Cache | nothing: it is a local file, or memory | — | none |

Only identifiers, organisation names for `search_organisations` and ROR's client ID ever leave
the server. A lookup the cache answers sends nothing, and offline mode sends nothing at all. The
server never sends research data, the person's details or the project's.

Requests carry a User-Agent naming this server and its source repository. A deployment may add its
operators' contact address (`DD_REGISTRY_CONTACT`): the DataCite and Crossref clients then send it
as `mailto:` in the User-Agent, which moves the server into each one's identified pool (Crossref's
"polite" pool: 10 lookups a second rather than 5; DataCite: 1,000 requests in 5 minutes per IP
rather than 500). Use a shared operators' mailbox, never a person's own address and never the
signed-in researcher's. ORCID and ROR are not sent it. Without it, no e-mail address is sent.

ROR is sent the deployment's free ROR client ID, if one is configured, as the `Client-Id` header,
which raises its rate limit. The ID identifies the deployment, not a person. It is read from a
credential file (`DD_PID_ROR_CLIENT_ID_FILE`), never from shared settings, and no other registry
is sent it.

## Running it

```sh
uv run dd-mcp-pid serve --port 8310
```

Settings, all from the environment:

| Setting | Meaning |
|---|---|
| `DD_PID_ROR` | `dump` (the default): read ROR from the built registry, and ask the API only when the registry cannot be read. `live`: ask the API only. |
| `DD_PID_ROR_REGISTRY` | The built registry, one ROR organisation per line. In the Data Director this is `agents/advisor-policy/data/ror/registry.jsonl`, built by `uv run dd-sources prepare`. |
| `DD_PID_ROR_SNAPSHOT` | Which dump the registry was built from, as answers name it (such as `ROR dump v2.15`). |
| `DD_REGISTRY_CONTACT` | The operators' contact address sent to DataCite and Crossref as `mailto:` (above). Unset or blank: none. Anything but one plain address stops start-up. |
| `DD_PID_JOURNALS_REGISTRY` | The journal registry's index (`journals.sqlite`), built by `uv run dd-journals fetch`; in the Data Director by `uv run dd-sources prepare`. Unset: where `dd-journals` builds it. Until it is built, each journal look-up is an error that says so; the tools are still listed. |
| `DD_PID_CACHE_DIR` | The directory for the cache file `pid.sqlite3`. Unset: in memory, for the life of the process. |
| `DD_PID_CACHE_TTL_FOUND`, `DD_PID_CACHE_TTL_MISSING` | Seconds a found record (default 604800, 7 days) and a miss (default 3600) are used without asking again. `0` asks every time, but still keeps the answer for when the registry cannot be asked. |
| `DD_PID_OFFLINE` | `1`: ask no registry; answer from the ROR dump and the cache only (above). Cannot be combined with `DD_PID_ROR=live`. |
| `DD_PID_ROR_CLIENT_ID_FILE` | A file holding ROR's client ID; a relative path is under `$CREDENTIALS_DIRECTORY`. A file that cannot be read stops start-up. Unset: ROR is asked anonymously. |
| `DD_PID_HOSTS` | Comma-separated host names that clients reach the server by, beyond loopback, such as a container's service name. Any other `Host` header is refused (DNS-rebinding protection). |

`GET /healthz` answers when the server is up.

A client lists each path as its own MCP server. The Data Director's tool configuration is
[`app/config/tools.yaml`](../app/config/tools.yaml), and Docker Compose's [`docker/tools.yaml`](../docker/tools.yaml).

## Not yet

- Grants: `resolve_grant`, through Crossref grant DOIs and the OpenAIRE Graph for awards that have
  none (#953).
- Offline mode answers only identifiers already in the cache: nothing preloads it.
