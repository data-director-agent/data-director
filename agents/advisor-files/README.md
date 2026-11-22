# advisor.files

**Alpha** (`0.3.0a1`), a model-backed alpha ([Agents](../../docs/specs/agents.md), invariant 14):
it does not yet do the File Archivist's real work, and its model only writes a summary beside the
rules' findings.

The File Archivist is one of the personas of the agent roster ([Agents](../../docs/specs/agents.md)). It serves one step of the
Blueprint's process flow:

| Step | What it does |
|---|---|
| `preparation.files` (clean and version the data files) | Lists each file of the project's inventory with its format, described from the PRONOM record of its identification or else suggested by its media type or extension, whether the format is open, and the files a person should look at before deposit. |

## Input and output

The input is the core contract's `FileInventory`: what `dd-inventory` wrote for the dataset's
folder ([`inventory/`](../../inventory/README.md), [Projects](../../docs/specs/projects.md)), with each file's path, size, digest,
media type, PRONOM identifiers and, for a table, its fields. The files themselves are never sent.

`FormatAssessment` holds one `FileAssessment` per file, in the inventory's order, with its `path`,
`extension`, `format_name`, `media_type`, `open_format`, what the judgement rests on
(`judged_by`), the PRONOM identifier of the record it used (`pronom_id`) and, for a format described
from PRONOM, a reference to that record (`grounded_on`); a `checks` list of the files a person should look at before deposit (a
`FileCheck` each, with its `path`, `kind`, the word or name that `matched`, the `question` for a
person and, for a copy, its `related_paths`); a `summary` (below); and a `limitations` list stating what it does
not do. A file with no PRONOM identifier
whose media type and extension are both missing from the table gives the format `unknown` and no
`open_format`. A file the inventory identified by PRONOM, but only with identifiers the pinned
release has no record of, is `judged_by` `pronom_unlisted`: also `unknown`, with `pronom_id`
giving the first identifier, so that it is not mistaken for a file nothing is known about. An inventory with no files abstains with `INSUFFICIENT_INPUT`.

## How it decides

It looks up the PRONOM identifiers (PUIDs such as `x-fmt/18`) the inventory gives, which
`dd-inventory` read from the file's content with fido, in a pinned PRONOM release
([`dd-formats`](../../formats/README.md)): the first identifier the release has a record of
decides, and a deprecated one is read as the identifier that replaces it. The format's name,
version and media type come from that record, and the assessment cites it, so its grounding mode
is `retrieval` (#955). Each record cited is in the envelope's evidence under the snapshot label
`pronom:v125`, which a deployment's source check resolves against its own pinned copy
(`app/config/sources.yaml`).

Whether a format is open (publicly specified and readable without proprietary software) is the
agent's own judgement, not PRONOM's, which does not say: the `open` table of `formats.yaml` gives
it for each PUID it lists. A format PRONOM describes but the table does not list has no
`open_format`, rather than a guess.

A file with no PRONOM identifier is identified by extension only, as before: the `extensions`
table of `formats.yaml` is looked up by the media type the inventory gives, then by the file
name's last extension, case ignored. Such a file cites no record. It reads no file and sends
nothing anywhere: the records are read from the pinned copy, and a live lookup with that copy as
fallback is TODO(#1475).

### Files for a person to look at

The inventory never holds contents, so the problems a dataset most often hides (personal data in
field notes, the coordinates of a sensitive site, a file under someone else's licence) cannot be
found from it (#449). It lists instead the files whose names, size or digest call for a
person to look, by the rules in `dd_sdk.inventory_hints`, which the harness's deposit check reads too:

| Kind | Called for by |
|---|---|
| `free_text` | A folder or file name such as `notes`, `fieldnotes`, `diary`, `interview`, `transcript` or `consent` |
| `coordinates` | A table field such as `lat`, `lon`, `easting`, `northing`, `gridref` or `location` |
| `third_party` | A folder such as `reference`, `external`, `vendor` or `downloaded` |
| `governance` | A folder or file name such as `agreement`, `licence`, `permission`, `contract` or `governance` |
| `system_file` | `Thumbs.db`, `desktop.ini`, `.DS_Store`, or a name beginning `~$` or `._` |
| `credentials` | A name such as `.env`, `.netrc` or `id_rsa`; an extension such as `.ini`, `.cfg`, `.conf`, `.pem` or `.key`; or a file name with a word such as `config`, `secret`, `credentials`, `password` or `token` |
| `empty` | A size of zero |
| `duplicate` | The same digest as another file that is not empty |
| `extension_mismatch` | A PRONOM identification whose record does not list the file name's extension, one the table knows (`matched` is the extension) |

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
- It does not weigh the inventory's table fields, and it judges whether a format is open only for
  the PRONOM identifiers in `formats.yaml`.
- It does not yet add the Library of Congress's sustainability notes on a format, which #952
  adopted for later, as links only.
- It does not suggest conversions, check that files open, or version them.

The real archivist is TODO(#354).

## Sources and licences

- **PRONOM**, The National Archives' technical registry, release v125, through
  [`dd-formats`](../../formats/README.md): contains public sector information licensed under the
  [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
  Source: The National Archives, PRONOM.
- `formats.yaml` is this agent's own, under the MIT licence with the code.

## Run it

```sh
uv run dd-advisor-files serve --port 8110
uv run workbench invoke --agent advisor.files --input workbench/samples/soil-survey.inventory.json
uv run pytest agents/advisor-files
```

With no model key, set `DD_FILES_SUMMARISER=template` first.
