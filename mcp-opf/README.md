# mcp-opf: a client and MCP server for Jisc Open Policy Finder

A read-only client and [MCP](https://modelcontextprotocol.io) server for
[Jisc Open Policy Finder](https://openpolicyfinder.jisc.ac.uk), which replaced Sherpa Romeo, Juliet
and Fact. It tells any agent framework what a funder requires of the outputs it funds, including
any data archiving requirement, and where a version of an article may be deposited in a journal or
a publisher's titles, after what embargo and under which licence. The Data Director's Policy
Adviser (`advisor.policy`) reads it as a library.

| Tool | Answers |
|---|---|
| `search_records` | the records of one item type (`publication` for a journal, `publisher` or `funder`) whose name has the words given (at most ten) |
| `get_record` | the record with an Open Policy Finder identifier or, for a journal, an ISSN |
| `get_journal_by_issn` | the journal with an ISSN, print or electronic, with its publishers' identifiers |

It is framework-neutral ([System](../docs/specs/system.md)). It imports nothing of the Data
Director, so it can be published on its own. `dd_mcp_opf.client.OpenPolicyFinder` is the client
without the server.

## Answers

Every tool answers `structuredContent` `{"records": [...]}`, valid against its `outputSchema`:

- **Found:** one record each, with `item_type`, `id`, `page` (the record's public page, to cite),
  `names`, `acronyms`, `country`, `url` (the organisation's home page, not its policy), `issns`,
  `publishers` (`id`, `name`, `relationship`, for a journal), `identifiers` and `policies`, as the
  record states them.
- **Not found:** no records.
- **Error** (`isError`): the input cannot be used, Open Policy Finder could not be asked, or the
  server has no API key. That is not the same as finding nothing.

A record holds no numbers or flags: they are strings (`"24"`, `"yes"`), so it hashes the same after
a round trip through a format whose numbers are doubles. Search matches whole words of a name, so
keep only the records that name the one meant.

## What is sent, and to whom

Each lookup asks `https://api.openpolicyfinder.jisc.ac.uk` for a name or an identifier, and nothing
else. The key goes in the `x-api-key` header, never in the address, and is never in an error.
Requests name this package and where its source is (`User-Agent:
data-director-mcp-opf/<version> (+https://github.com/data-director-agent/data-director)`). A
deployment may add its operators' contact address (`DD_REGISTRY_CONTACT`), never a person's own.

## Running it

A free key comes from Jisc
([how to request one](https://openpolicyfinder.jisc.ac.uk/help/developers/how-to-request-a-new-api-key)).

```sh
OPEN_POLICY_FINDER_API_KEY=... uv run dd-mcp-opf serve --port 8314   # MCP at http://127.0.0.1:8314/opf/mcp
OPEN_POLICY_FINDER_API_KEY=... uv run dd-mcp-opf check               # try the route; --record DIR keeps the answers
```

| Setting | Meaning |
|---|---|
| `OPEN_POLICY_FINDER_API_KEY` or `..._FILE` | The key, or a file holding it (a relative name is read under `CREDENTIALS_DIRECTORY`). Without one the server starts and each call says one is needed. |
| `DD_OPF_HOSTS` | Comma-separated host names clients reach the server by, beyond loopback. Any other `Host` header is refused (DNS-rebinding protection). |
| `DD_REGISTRY_CONTACT` | The operators' contact address, added to the User-Agent as `mailto:`. |

`GET /healthz` answers when the server is up.

## Sources and licences

The code is under the MIT licence (`LICENSE`). Jisc licenses the Open Policy Finder data under
[CC BY-NC-ND 4.0](https://creativecommons.org/licenses/by-nc-nd/4.0/), and its API is for
non-commercial use. That binds whoever runs this server, not only its authors. No-derivatives rules
out a projected copy, so nothing is copied or cached: every answer is read live, and there is no
snapshot to fall back to. Jisc states no rate limit. Whether answering with projected records is a
derivative has not been settled. TODO(#302)

The answers in `tests/data/` are written by hand in the shape of the Sherpa v2 API, which Jisc says
the platform replicates, not recorded from the live service.

## Depends on

`httpx` for the API, and the MCP Python SDK, Starlette and Uvicorn for the server. Nothing else of
the Data Director.

## Not yet

- The client was written without a key. Its endpoints, filter fields and operators follow Jisc's
  [documentation](https://openpolicyfinder.jisc.ac.uk/help/developers/api-types/object-retrieval-api);
  where a funder's record keeps its policies is a guess from the Sherpa v2 shape. `dd-mcp-opf check
  --record DIR` records real answers to replace the fixtures. TODO(#302)
- No deployment lists the server behind the tool gateway, and no canonicalisation is registered
  for its records. `advisor.policy` reads Open Policy Finder as a library. TODO(#1143)
