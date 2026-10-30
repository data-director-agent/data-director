# advisor.files

**Alpha** (`0.1.0a1`), and a **mock**: it does not yet do the File Archivist's real work.

The File Archivist is one of the personas of the agent roster (ADR-0033). It serves one step of the
Blueprint's process flow:

| Step | What the mock does |
|---|---|
| `preparation.files` (clean and version the data files) | Lists each file of the project's inventory with the format its media type or extension suggests, and whether the format is open. |

## Input and output

The input is the core contract's `FileInventory`: what `dd-inventory` wrote for the dataset's
folder ([`inventory/`](../../inventory/README.md), ADR-0034), with each file's path, size, digest,
media type, PRONOM identifiers and, for a table, its fields. The files themselves are never sent.

`FormatAssessment` holds one `FileAssessment` per file, in the inventory's order, with its `path`,
`extension`, `format_name`, `media_type`, `open_format` and what the judgement rests on
(`judged_by`), and a `limitations` list stating what the mock does not do. A file whose media type
and extension are both missing from the rule table gives the format `unknown` and `open_format`
false. An inventory with no files abstains with `INSUFFICIENT_INPUT`.

## How it decides

The mock looks up the media type the inventory gives, which fido may have read from the file's
content, in `formats.yaml`. If that media type is absent or not in the table, it looks up the file
name's last extension, case ignored. It reads no file, consults no source and calls no model, so
its grounding mode is `none` and it cites only its input.

## What it does not do

- It does not open or read any file.
- It does not weigh the inventory's PRONOM identifiers or table fields.
- It does not suggest conversions, check that files open, or version them.

The real archivist is TODO(#354).
