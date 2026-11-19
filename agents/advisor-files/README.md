# advisor.files

**Alpha** (`0.2.0a1`), a model-backed alpha ([Agents](../../docs/specs/agents.md), invariant 14):
it does not yet do the File Archivist's real work, and its model only writes a summary beside the
rules' findings.

The File Archivist is one of the personas of the agent roster ([Agents](../../docs/specs/agents.md)). It serves one step of the
Blueprint's process flow:

| Step | What it does |
|---|---|
| `preparation.files` (clean and version the data files) | Lists each file of the project's inventory with the format its PRONOM identification, media type or extension suggests, and whether the format is open, and the files a person should look at before deposit. |

## Input and output

The input is the core contract's `FileInventory`: what `dd-inventory` wrote for the dataset's
folder ([`inventory/`](../../inventory/README.md), [Projects](../../docs/specs/projects.md)), with each file's path, size, digest,
media type, PRONOM identifiers and, for a table, its fields. The files themselves are never sent.

`FormatAssessment` holds one `FileAssessment` per file, in the inventory's order, with its `path`,
`extension`, `format_name`, `media_type`, `open_format`, what the judgement rests on
(`judged_by`) and the PRONOM identifier it used (`pronom_id`); a `checks` list of the files a person should look at before deposit (a
`FileCheck` each, with its `path`, `kind`, the word or name that `matched`, the `question` for a
person and, for a copy, its `related_paths`); a `summary` (below); a `limitations` list stating what it does
not do; and `proposed_facts`, for each file it lists, the project fact a person decides about it
before deposit: whether a file with coordinates may be published (`sensitivity`, `undecided`), and
whether any other goes in (`file_inclusion`: `exclude` for an operating-system or empty file,
`undecided` for the rest), each with the checks' questions as `proposed_because`. In a project the
harness records them for a person to decide, and the deposit check pauses on each until one does
([Deposit](../../docs/specs/deposit.md)). A misnamed file proposes nothing. A file whose PRONOM
identifiers, media type and extension are all missing from the rule table gives the format
`unknown` and `open_format` false. A file the inventory identified by PRONOM, but only as formats
the table does not list, is `judged_by` `pronom_unlisted`: also `unknown`, with `pronom_id` giving
the first identifier, so that it is not mistaken for a file nothing is known about. An inventory with no files abstains with `INSUFFICIENT_INPUT`.

## How it decides

It looks up, in `formats.yaml`, the PRONOM identifiers (PUIDs such as `x-fmt/18`) the
inventory gives, which `dd-inventory` read from the file's content with fido: the first one in the
table decides. If there is none, it looks up the media type the inventory gives, then the file name's
last extension, case ignored. A row of the table has a `pronom` list only where we are sure of its
PUIDs, so a format without one is still found by media type or extension. It reads no file and
consults no source, so its grounding mode is `input_only` and it cites only its input.

### Files for a person to look at

The inventory never holds contents, so the problems a dataset most often hides (personal data in
field notes, the coordinates of a sensitive site, a file under someone else's licence) cannot be
found from it (#449). It lists instead the files whose names, size or digest call for a
person to look, by the rules in `hints.yaml`:

| Kind | Called for by |
|---|---|
| `free_text` | A folder or file name such as `notes`, `fieldnotes`, `diary`, `interview`, `transcript` or `consent` |
| `coordinates` | A table field such as `lat`, `lon`, `easting`, `northing`, `gridref` or `location` |
| `third_party` | A folder such as `reference`, `external`, `vendor` or `downloaded` |
| `governance` | A folder or file name such as `agreement`, `licence`, `permission`, `contract` or `governance` |
| `system_file` | `Thumbs.db`, `desktop.ini`, `.DS_Store`, or a name beginning `~$` or `._` |
| `empty` | A size of zero |
| `duplicate` | The same digest as another file that is not empty |
| `extension_mismatch` | A PRONOM identification whose format differs from the one the file name's extension suggests (`matched` is the extension) |

Words are matched whole, case ignored, so `lat` matches `lat` and `site_lat` but not `plateau`.
Each check is a prompt for a person, never a finding or a decision, and a file with none may still
hold personal data, sensitive locations or someone else's material: the statement and the
limitations say so. The app marks the same files in the inventory under **Files to look at**, with
a copy of these rules in `inventory/browser/src/hints.ts`; change both together. Content
detection, and findings carried in the inventory itself, are #470 and #471
([Personal data](../../docs/specs/personal-data.md)).


## Summary

A summariser (`dd_sdk.summary`) writes a short `summary` beside the findings, with
`summary_derivation` saying how it came about. `DD_FILES_SUMMARISER` (`factory.py`,
`config/examples/agents.env`) chooses it:

- `model` (default): a model is sent the findings (each file's path, format and check, never a file's contents) and writes the summary from
  `system_prompt.md`. A reply that is missing, refused, or names a DOI, ORCID iD or web address
  the findings do not give is replaced by the rules' own summary, marked `template`, as is a
  model that cannot be reached. The model and its key are set as for every agent
  ([AI models](../../docs/guide/operations/ai-models.md)). Left unset with no key, `dd.py start`
  runs it with `template`.
- `template`: the rules' own summary; calls no model and needs no key.

The model changes no finding: each format and each check is decided by the rules above either way.

## What it does not do

- It does not open or read any file, so it cannot see personal data, sensitive locations, licence
  terms or instructions inside one.
- It does not weigh the inventory's table fields, and its table of PRONOM identifiers covers only
  the formats in `formats.yaml`.
- It does not suggest conversions, check that files open, or version them.

The real archivist is TODO(#354).
