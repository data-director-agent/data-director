# mcp-spdx: an MCP server for the SPDX licence list

A read-only [MCP](https://modelcontextprotocol.io) server for a pinned release of the
[SPDX License List](https://spdx.org/licenses/), so any agent framework can look a licence up by
its identifier without carrying its own copy. It is the `spdx` server the Data Director's
Rights and Licensing Adviser (`advisor.rights`) retrieves its candidate licences from through the
tool gateway ([Agents](../docs/specs/agents.md#tools-mcp-servers-and-agent-skills)).

| Tool | Answers |
|---|---|
| `get_licence` | the record for an SPDX licence identifier, such as `CC-BY-4.0`, matched without regard to case |

It is framework-neutral ([System](../docs/specs/system.md)): it imports nothing of the Data
Director, so it can be published on its own.

## Answers

`get_licence` answers `structuredContent` `{"records": [...]}`, valid against its `outputSchema`:

- **Found:** one record, with SPDX's own field names: `licenseId`, `name`, `reference` (the
  licence's SPDX page), `isOsiApproved`, `isFsfLibre` (null where SPDX says nothing),
  `isDeprecatedLicenseId` and `seeAlso` (the URLs SPDX lists for its text, sorted). `licenseId` is
  the field a client identifies the record by, in SPDX's spelling whatever case was asked for.
  A deprecated identifier, such as `GPL-2.0`, is found and marked.
- **Not found:** no records.
- **Error** (`isError`): the input is not an identifier.

The record holds the fields the registered `dd-spdx-licence-v1` canonicalisation hashes
(`dd_sdk.evidence`), so a deployment can name that canonicalisation for the server.

## What is sent, and to whom

Nothing. The release is packaged with the server and read from memory; no lookup leaves the
machine.

## Running it

```sh
uv run dd-mcp-spdx serve --port 8312   # MCP at http://127.0.0.1:8312/spdx/mcp
```

| Setting | Meaning |
|---|---|
| `DD_SPDX_HOSTS` | Comma-separated host names clients reach the server by, beyond loopback. Any other `Host` header is refused (DNS-rebinding protection). |

`GET /healthz` answers when the server is up, and names the release it serves as `snapshot_ref`
(`spdx:3.29.0`).

A deployment lists it in its tool configuration (`DD_TOOLS_CONFIG`,
[Configuration](../docs/guide/operations/configuration.md)) as:

```yaml
servers:
  - name: spdx
    url: http://127.0.0.1:8312/spdx/mcp
    id_field: licenseId
    canonicalisation: dd-spdx-licence-v1
    snapshot_ref: spdx:3.29.0
    tools_sha256: "<from `dd-harness tools pins`>"
```

## Sources and licences

The code is under the MIT licence (`LICENSE`). The records in `src/dd_mcp_spdx/data/` are derived
from [`spdx/license-list-data`](https://github.com/spdx/license-list-data), release 3.29.0 of
16 September 2026, and are under CC0-1.0 (`src/dd_mcp_spdx/data/LICENCE.md`). `manifest.json`
records the release, the SHA-256 of the file they were derived from and of the records file; the
server refuses to start from a records file that does not match it.

## Updating to a new release

SPDX publishes a new release of the list about twice a year
([tags](https://github.com/spdx/license-list-data/tags)). To move to one:

1. Rebuild the records from the release's tag. The script downloads `json/licenses.json` at that
   tag and writes the records and the manifest; the same release gives the same bytes.

   ```bash
   uv run --no-project --python 3.14 mcp-spdx/scripts/pin_spdx_list.py v3.29.0
   ```

2. Update the copy each deployment pins for the source check (`app/config/sources.yaml`,
   `workbench/sources.yaml`): the new file's path, its `spdx:<version>` label and its SHA-256
   (`records.sha256` in `manifest.json`).
3. Check the Rights and Licensing Adviser's packaged fallback
   (`agents/advisor-rights/src/dd_agent_advisor_rights/licences.yaml`): each identifier still
   exists, is not deprecated, and has SPDX's name.
4. Update the `spdx:<version>` examples in this README and in the deployment's tool
   configuration. The tool's schema does not change with a release, so its `tools_sha256` pin
   stays the same.

## Not yet

- No deployment lists the server yet: running it under Docker Compose and the development
  switch that grants it to `advisor.rights` are TODO(#1478).
- Search by name or text: `get_licence` needs the identifier.
- Licence texts and exceptions (`exceptions.json`) are not served.
