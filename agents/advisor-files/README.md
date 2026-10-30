# advisor.files

**Alpha** (`0.1.0a1`), and a **mock**: it does not yet do the File Archivist's real work.

The File Archivist is one of the personas of the agent roster (ADR-0033). It serves one step of the
Blueprint's process flow:

| Step | What the mock does |
|---|---|
| `preparation.files` (clean and version the data files) | Lists each file with the format its name's extension suggests, that format's media type, and whether the format is open. |

## Input and output

`FileList` lists the dataset's files, each a `FileEntry` with a `name` and, when known, its
`size_bytes` and `media_type`. The files themselves are not sent.

`FileInventory` holds one `InventoryEntry` per file, in the order given, with its `extension`,
`format_name`, `media_type` and `open_format`, and a `limitations` list stating what the mock does
not do. An extension missing from the rule table gives the format `unknown`, no media type, and
`open_format` false. An empty list abstains with `INSUFFICIENT_INPUT`.

## How it decides

The mock looks up each file name's last extension, case ignored, in `formats.yaml`. It reads no
file, consults no source and calls no model, so its grounding mode is `none` and it cites only its
input.

## What it does not do

- It does not open or read any file, so it cannot tell a misnamed file from a correct one.
- It does not identify formats from content (PRONOM, with fido), describe tables (Frictionless
  table schemas) or record digests (#198, #13).
- It does not suggest conversions, check that files open, or version them.

The real archivist is TODO(#354).
