# advisor.documentation

**Mock, alpha** (`0.1.0a1`): a placeholder for a persona of the agent roster (docs/specs/agents.md), and the
stub drafter of a project's README and data dictionary (#200). It gives no real advice and is
likely to change shape.

The Documentation Editor drafts a README and a data dictionary for a dataset (Blueprint R5). It
serves two steps of the process flow:

| Step | What the mock does |
|---|---|
| `setup.documentation` | Drafts a README or a data dictionary from the project's file inventory and approved metadata record. |
| `preparation.documentation` | The same, for documentation drafted or reviewed while preparing the deposit. |

## Input and output

It accepts the core `DraftRequest` and returns the core `Document`, so its drafts become project
documents ([Projects](../../docs/specs/projects.md)) and the real editor can replace it
without its caller changing. A request names the `document_kind`:

- `readme`: a Markdown README with the sections of `readme.yaml`. Each section shows, in italics,
  what the researcher should write in it. The **Files** section lists the inventory's files with
  their formats and sizes. **Variables** lists each table's fields with their types. **Access and
  licence** lists the licences the chosen repository offers, if its requirements name any.

  When the request carries the project's approved metadata record (`metadata_record`, which the
  conductor fills in a project), the README takes from it, as given: the title, as the README's
  heading and in **General information** with the creators and funders; the abstract, as the
  **Description**; the licence, in **Access and licence**; and a citation by the creators, the
  publication year if there is one, and the title, in **How to cite**. These are `supplied`
  ([Drafting documents](../../docs/specs/drafting.md), invariant 2). The abstract says all the
  Description asks, so that section then has no gap; the others keep theirs for what the record
  does not say, such as a contact, the dates of collection or the DOI. The mock reads a record in
  DataCite's JSON form (`conforms_to` `http://datacite.org/schema/kernel-4`), as
  `advisor.metadata` drafts it, and skips any value left `null` or blank. It does not use a record
  in any other form, and says so in its statement.
- `data_dictionary`: a CSV with one row per field of each table in the inventory, keyed by `file`
  and `field`. Each of the values `type`, `format`, `description`, `unit` and `missing_values` is
  followed by a column saying where it came from (`type_source`, …), so that a person can check
  it:
  - `inferred`: read from the data by `dd-inventory`, which infers a field's type and format;
  - `supplied`: given by the researcher, either as a description in the inventory or as a value
    in the version being regenerated;
  - `unknown`: no one has said yet, and the cell is empty.

  The mock infers no units or missing value codes, so those are `unknown` until the researcher
  fills them in.

Every gap is asked ([Drafting documents](../../docs/specs/drafting.md)). The `Document` carries
one question in `document_questions` for each README section left for the researcher and each
`unknown` cell. In the README, each placeholder is followed by `<!-- dd:gap <question-id> -->`,
which the rendered README does not show. A question's identifier is derived from its gap, so the
same gap has the same identifier in every version. An answer in the request's `draft_answers` is
placed, as given, in the gap or cell it answers, marked `supplied` in a data dictionary, and that
gap is not asked again. The mock suggests no answers (#574).

The README's sections are the common core of the research data README templates compared in
#200: Cornell's Data README, Dryad's and the Borealis working group's minimum README.

It abstains with `insufficient_input` when the request has no inventory, or when a data
dictionary is asked for and no file in the inventory has fields. It abstains with
`outside_agent_scope` for any other kind. When the request gives a `current_version`, the mock
drafts afresh, names that version in `revises` and keeps its title. A regenerated data dictionary
keeps the researcher's values: a value in the current version that differs from what the inventory
gives, or fills a cell it leaves empty, is kept and marked `supplied`. Its rows are the inventory's
fields, so a field no longer in the inventory is dropped.

Its grounding mode is `none`: it cites only its input. The core `Document` has no `limitations`
slot, so the outcome's statement says what the mock does not do (docs/specs/agents.md).

## What it does not do

- It writes no prose of its own and invents nothing. What the approved metadata record does not
  give, and the methods, are left to the researcher.
- It does not open the files, so it says nothing about their contents beyond what the inventory
  records.
- It infers no variable definitions, units or missing value codes.
- It does not read an earlier README, or the reason a person gave for a decision on a version.
- It follows no data dictionary standard, such as CDIF's variable descriptions (#220).

The real editor, drafting with a model from the files and the project record, is TODO(#358).
What it will infer, ask and write is set out in
[Drafting documents](../../docs/specs/drafting.md).
