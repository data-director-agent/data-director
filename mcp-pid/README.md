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

It is framework-neutral ([System](../docs/specs/system.md)): it imports nothing of the Data
Director, so it can be published on its own. In the Data Director it sits behind the harness's
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
  asked. Busy or failing services are retried twice first.

Records are identified at their top level: `doi` (bare and lower-case), `orcid` (as a URL) or `id`
(the ROR URL). They hold no integers: a publication year is text.

Each server is a separate path because a client such as the gateway identifies a server's records
by one field.

## What is sent, and to whom

| Registry | What a query sends | Terms | Limits |
|---|---|---|---|
| DataCite | the DOI | metadata [CC0](https://support.datacite.org/docs/datacite-data-file-use-policy) | no key; rate-limited per IP |
| Crossref | the DOI | metadata openly available, facts not copyrightable ([terms](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)) | no key; the public pool is rate-limited |
| ORCID | the iD | public data; ORCID's [public API terms](https://info.orcid.org/public-client-terms-of-service/) | no key for single records |
| ROR | the identifier, or the name searched for, and only when the dump cannot answer | [CC0](https://ror.org/about/faqs/) | no key; client IDs are announced but not yet enforced |

Only identifiers, and organisation names for `search_organisations`, ever leave the server. It
never sends research data, the person's details or the project's.

Requests carry a User-Agent naming this server and its source repository, and no e-mail address.

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
| `DD_PID_HOSTS` | Comma-separated host names that clients reach the server by, beyond loopback, such as a container's service name. Any other `Host` header is refused (DNS-rebinding protection). |

`GET /healthz` answers when the server is up.

A client lists each path as its own MCP server. The Data Director's tool configuration is
[`app/config/tools.yaml`](../app/config/tools.yaml), and Docker Compose's [`docker/tools.yaml`](../docker/tools.yaml).

## Not yet

- Grants: `resolve_grant`, through Crossref grant DOIs and the OpenAIRE Graph for awards that have
  none (#953).
- Caching (#327) and an offline mode beyond the ROR dump (#792).
