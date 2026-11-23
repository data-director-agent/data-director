# mcp-subjects: an MCP server for subject classifications

A read-only [MCP](https://modelcontextprotocol.io) server for the subject classifications that
repositories ask a dataset's categories from, so any agent framework can offer a field of
research and cite where it came from. It serves the schemes packaged with
[`dd-subjects`](../subjects/README.md) and reaches no network.

| Tool | Answers |
|---|---|
| `list_terms` | a scheme with every field in it: each field's code, label and the code of the field it is under |
| `get_term` | one field of a scheme by its code |

| Scheme id | Classification | Also named |
|---|---|---|
| `anzsrc-for` | ANZSRC 2020 Fields of Research, divisions and groups | ANZSRC Fields of Research, ANZSRC FoR, Fields of Research |
| `oecd-fos` | OECD Fields of Research and Development (Frascati Manual 2015) | OECD Fields of Science and Technology, OECD FOS |

A scheme is named by its id, its name or one of the other names in the table, which are the
names repositories write in a DataCite `subjectScheme` (ORDA writes "ANZSRC Fields of Research"),
matched without regard to case.

It is framework-neutral ([System](../docs/specs/system.md)): it imports only `dd-subjects`,
which imports nothing beyond the standard library, so the two can be published on their own.

## Answers

Each tool answers `structuredContent` `{"records": [...]}`, valid against its `outputSchema`:

- **Found:** one record, identified by `id`: the scheme's id for `list_terms` (`anzsrc-for`),
  and `<scheme>:<code>` for `get_term` (`anzsrc-for:4106`). A client that records each record by
  `id` never gives two records the same identifier. Every record also carries the scheme's
  name, version, source, licence and attribution.
- **Not found:** no records, for a scheme or code the server does not know.
- **Error** (`isError`): the input names no scheme, or `get_term` names no code.

Records hold strings only, so a client can hash them under any JSON canonicalisation. The Data
Director's tool gateway records them by `id` and hashes them whole (`dd-json-document-v1`).

## What is sent, and to whom

Nothing. Every answer comes from the data packaged with `dd-subjects`.

## Running it

```sh
uv run dd-mcp-subjects serve --port 8314   # MCP at http://127.0.0.1:8314/subjects/mcp
```

| Setting | Meaning |
|---|---|
| `DD_SUBJECTS_HOSTS` | Comma-separated host names clients reach the server by, beyond loopback. Any other `Host` header is refused (DNS-rebinding protection). |

`GET /healthz` answers when the server is up, with the version of each scheme served.

In a Data Director deployment, list it in the tool servers file (`DD_TOOLS_CONFIG`):

```yaml
servers:
  - name: subjects
    url: http://127.0.0.1:8314/subjects/mcp
    id_field: id
    canonicalisation: dd-json-document-v1
    tools_sha256: "…"   # from `dd-harness tools pins`
```

and grant it to the Metadata Librarian in the institutional profile
(`tool_servers: {advisor.metadata: [subjects]}`).

## Sources and licences

The code is under the MIT licence (`LICENSE`). The schemes are their publishers', as
[`dd-subjects`](../subjects/README.md#sources-and-licences) records: ANZSRC 2020 under CC BY 4.0
(© Commonwealth of Australia (Australian Bureau of Statistics) and Stats NZ), and the OECD's
Fields of R&D as an excerpt with acknowledgement. Every record carries its scheme's licence and
attribution, so a client that shows a field can credit it.

## Limits

- Fields of research only, the ones `dd-subjects` holds: no keyword vocabularies or ontologies.
  Which terminology services to look keywords up in is the spike
  [#956](https://github.com/data-director-agent/data-director/issues/956).
- No search: a client chooses from `list_terms`, which is short enough to read whole (236 ANZSRC
  fields, 48 OECD).
- No crosswalk between schemes (#1407).

## Dependencies

[`dd-subjects`](../subjects/README.md), the MCP Python SDK, Starlette and Uvicorn. Its tests use
the Data Director's tool gateway (`data-director-harness[gateway]`) and SDK, as dev dependencies
only.
