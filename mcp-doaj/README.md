# mcp-doaj: a client and MCP server for DOAJ

A read-only client and [MCP](https://modelcontextprotocol.io) server for the
[Directory of Open Access Journals](https://doaj.org) (DOAJ). It tells any agent framework what an
open access journal's terms are: its licences, whether authors keep copyright, its deposit
(self-archiving) policy, its preservation services and charges, its publisher, and the journal's
own pages that state those terms. The Data Director's Policy Adviser (`advisor.policy`) reads it as
a library, so it can say something about a journal without an Open Policy Finder key
([#1517](https://github.com/data-director-agent/data-director/issues/1517)).

| Tool | Answers |
|---|---|
| `get_journal` | the record of the journal with an ISSN, print or electronic |
| `search_journals` | the records of journals whose title matches, in DOAJ's order (at most five) |

It is framework-neutral ([System](../docs/specs/system.md)). It imports nothing of the Data
Director, so it can be published on its own. `dd_mcp_doaj.journals.Doaj` is the client without
the server.

## Answers

Both tools answer `structuredContent` `{"records": [...]}`, valid against their `outputSchema`:

- **Found:** one record per journal. `id` is DOAJ's identifier and `url` the journal's DOAJ page.
  The record also has `title`, `alternative_title`, `eissn`, `pissn`, `publisher`,
  `publisher_country`, `licences` (each `type` and `url`), `author_retains_copyright`,
  `copyright_url`, `deposit_policy` (`has_policy`, `services` such as Open Policy Finder, and
  `url`), `preservation` (`has_preservation`, `services`), `apc` (`has_apc`, `highest` charges
  such as `2477 USD`, and `url`), `has_waiver`, `oa_start`, `pages` (`journal`, `oa_statement`,
  `license_terms` and `author_instructions`, where DOAJ gives them), `subjects` and
  `last_updated`. A flag DOAJ does not give is null.
- **Not found:** no records. DOAJ lists open access journals only, so a journal it does not list
  may still exist.
- **Error** (`isError`): the input is not an ISSN or a title, or DOAJ could not be asked. That is
  not the same as finding nothing.

A record holds no integers: a year and a price are strings, so the record hashes the same after a
round trip through a format whose numbers are doubles (such as a protobuf `Struct`). Lists are
sorted, so the order DOAJ lists things in does not change the record. Editorial, indexing and
plagiarism details are left out.

## What is sent, and to whom

Each lookup asks `https://doaj.org/api/v4/search/journals/` for an ISSN or a title, and nothing
else. Requests name this package and where its source is (`User-Agent:
data-director-mcp-doaj/<version> (+https://github.com/data-director-agent/data-director)`). A
deployment may add its operators' contact address (`DD_REGISTRY_CONTACT`), never a person's own.

DOAJ allows two requests a second, with bursts of five
([API documentation](https://doaj.org/api/docs)). A busy answer (HTTP 429) is retried once after
a second; then the lookup is reported as failed.

## Running it

```sh
uv run dd-mcp-doaj serve --port 8313   # MCP at http://127.0.0.1:8313/doaj/mcp
```

| Setting | Meaning |
|---|---|
| `DD_DOAJ_HOSTS` | Comma-separated host names clients reach the server by, beyond loopback. Any other `Host` header is refused (DNS-rebinding protection). |
| `DD_REGISTRY_CONTACT` | The operators' contact address, added to the User-Agent as `mailto:`. |

`GET /healthz` answers when the server is up.

## Sources and licences

The code is under the MIT licence (`LICENSE`). DOAJ waives all rights in its metadata under CC0
([FAQ](https://doaj.org/docs/faq/)), and the rest of its site is under CC BY-SA 4.0. Nothing is
copied into this package: every answer is read live. The recorded answers in `tests/data/` are
DOAJ's records of *Nature Communications* and *PLOS ONE*, kept for the tests.

## Depends on

`httpx` for the API, and the MCP Python SDK, Starlette and Uvicorn for the server. Nothing else
of the Data Director.

## Not yet

- No deployment lists the server behind the tool gateway, and no canonicalisation is registered
  for its records. `advisor.policy` reads DOAJ as a library, as it reads its other registries.
  TODO(#1143)
- Search by publisher or by subject.
