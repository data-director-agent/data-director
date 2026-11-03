# advisor.documentation

**Mock, alpha** (`0.1.0a1`): a placeholder for a persona of the agent roster (ADR-0033), and the
stub drafter of a project's README and data dictionary (#200). It gives no real advice and is
likely to change shape.

The Documentation Editor drafts a README and a data dictionary for a dataset (Blueprint R5). It
serves two steps of the process flow:

| Step | What the mock does |
|---|---|
| `setup.documentation` | Drafts a README or a data dictionary from the project's file inventory. |
| `preparation.documentation` | The same, for documentation drafted or reviewed while preparing the deposit. |

## Input and output

It accepts the core `DraftRequest` and returns the core `Document`, so its drafts become project
documents ([ADR-0035](../../docs/adr/0035-project-documents.md)) and the real editor can replace it
without its caller changing. A request names the `document_kind`:

- `readme`: a Markdown README with the sections of `readme.yaml`. Each section shows, in italics,
  what the researcher should write in it. The **Files** section lists the inventory's files with
  their formats and sizes. **Variables** lists each table's fields with their types. **Access and
  licence** lists the licences the chosen repository offers, if its requirements name any.
- `data_dictionary`: a CSV with one row per field of each table in the inventory. The columns are
  `file`, `field`, `type`, `format`, `description`, `unit` and `missing_values`. The file, field,
  type and format are copied from the inventory, and so is a description where the inventory has
  one. The unit and missing value codes are always left empty.

The README's sections are the common core of the research data README templates compared in
#200: Cornell's Data README, Dryad's and the Borealis working group's minimum README.

It abstains with `insufficient_input` when the request has no inventory, or when a data
dictionary is asked for and no file in the inventory has fields. It abstains with
`outside_agent_scope` for any other kind. When the request gives a `current_version`, the mock
drafts afresh, names that version in `revises` and keeps its title.

Its grounding mode is `none`: it cites only its input. The core `Document` has no `limitations`
slot, so the outcome's statement says what the mock does not do (ADR-0033 decision 5).

## What it does not do

- It writes no prose of its own and invents nothing. The title, description, methods, licence and
  citation are left to the researcher.
- It does not open the files, so it says nothing about their contents beyond what the inventory
  records.
- It infers no variable definitions, units or missing value codes.
- It does not read an earlier version, or the reason a person gave for a decision on it.
- It follows no data dictionary standard, such as CDIF's variable descriptions (#220).

The real editor, drafting with a model from the files and the project record, is TODO(#358).
