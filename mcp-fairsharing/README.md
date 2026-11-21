# mcp-fairsharing: a FAIRsharing MCP server

A read-only [MCP](https://modelcontextprotocol.io) server for [FAIRsharing](https://fairsharing.org),
the registry of standards, databases and policies, so any agent framework can look them up
without carrying its own client. It is the framework-neutral capability that the Data Director's
advisers (`advisor.standards`, `advisor.repository`, `advisor.policy`) each hold a copy of
today (#280).

| Tool | Answers | Account |
|---|---|---|
| `get_record` | the record for a `FAIRsharing.xxxxx` identifier, its DOI (`10.25504/...`), a fairsharing.org URL or a numeric id | none: FAIRsharing's public record route |
| `search_records` | records matching some words, in FAIRsharing's relevance order, optionally of one record type | the server's own (`FAIRSHARING_LOGIN`, `FAIRSHARING_PASSWORD`) |

It is framework-neutral ([System](../docs/specs/system.md)): it imports nothing of the Data
Director, so it can be published on its own.

## Answers

Each tool answers `structuredContent` `{"records": [...]}`, valid against its `outputSchema`:

- **Found:** the record: `id`, `doi`, `name`, `abbreviation`, `registry`, `record_type`,
  `status`, `description`, `homepage`, `subjects`, `domains`, `url` and `licence`. `id` is the
  field a client identifies the record by. Both routes give the same record.
- **Not found:** no records.
- **Error** (`isError`): the input is not an identifier, FAIRsharing could not be asked (busy
  or failing services are retried twice), or `search_records` was called on a server with no
  account. `get_record` still works then.

## What is sent, and to whom

A query sends the identifier, or the words searched for, to FAIRsharing, and nothing about the
person or project. Requests carry a User-Agent naming this server and its source, and no e-mail
address. FAIRsharing content is [CC BY-SA 4.0](https://fairsharing.org/licence); every record
carries that notice.

The account is the server's, so a person never registers and what a run retrieves does not depend
on who ran it. The credentials stay in the server's environment and reach neither a client nor an
answer. Before a public deployment, FAIRsharing should agree to a shared automated account, and
the account should belong to an organisation, not a person (#280). FAIRsharing also publishes its
own server, [`FAIRsharing/fairsharing-mcp`](https://github.com/FAIRsharing/fairsharing-mcp)
(GraphQL, API key); this one differs in answering the small, stable records a client can hash,
and in needing no account for a record.

## Running it

```sh
uv run dd-mcp-fairsharing serve --port 8311   # MCP at http://127.0.0.1:8311/fairsharing/mcp
```

| Setting | Meaning |
|---|---|
| `FAIRSHARING_LOGIN`, `FAIRSHARING_PASSWORD` | A FAIRsharing account, needed only by `search_records`. |
| `DD_FAIRSHARING_HOSTS` | Comma-separated host names clients reach the server by, beyond loopback. Any other `Host` header is refused (DNS-rebinding protection). |

`GET /healthz` answers when the server is up.

## Not yet

- The advisers still use their own clients. Moving them onto this server needs the A2A-or-MCP
  decision (#280) and a check that the harness derives the same evidence hash from a record the
  gateway recorded as from the adviser's own projection.
- Caching (#327).
