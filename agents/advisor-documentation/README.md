# advisor.documentation

**Alpha** (`0.2.0a1`): the Documentation Editor persona of the agent roster
(docs/specs/agents.md), and the drafter of a project's README and data dictionary
([Drafting documents](../../docs/specs/drafting.md)). It is likely to change shape.

The Documentation Editor drafts a README and a data dictionary for a dataset (Blueprint R5). It
serves two steps of the process flow:

| Step | What it does |
|---|---|
| `setup.documentation` | Drafts a README or a data dictionary from the project's file inventory and approved metadata record. |
| `preparation.documentation` | The same, for documentation drafted or reviewed while preparing the deposit. |

## Input and output

It accepts the core `DraftRequest` and returns the core `Document`, so its drafts become project
documents ([Projects](../../docs/specs/projects.md)). A request names the `document_kind`:

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
  does not say, such as a contact, the dates of collection or the DOI. The editor reads a record
  in DataCite's JSON form (`conforms_to` `http://datacite.org/schema/kernel-4`), as
  `advisor.metadata` drafts it, and skips any value left `null` or blank. It does not use a record
  in any other form, and says so in its statement. With no record, it drafts from the inventory
  alone and says so.

  When a model is configured (below), it also writes the README's prose: an overview under the
  title, and a short paragraph for each section that has facts to draft from, introducing them.
- `data_dictionary`: a CSV with one row per field of each table in the inventory, keyed by `file`
  and `field`. Each of the values `type`, `format`, `description`, `unit` and `missing_values` is
  followed by a column saying where it came from (`type_source`, …), so that a person can check
  it:
  - `inferred`: read from the data by `dd-inventory`, which infers a field's type and format;
  - `supplied`: given by the researcher, either as a description in the inventory or as a value
    in the version being regenerated;
  - `unknown`: no one has said yet, and the cell is empty.

  The editor infers no units or missing value codes, so those are `unknown` until the researcher
  fills them in. A data dictionary is always drafted by rule: a model fills no cell. Where a
  model is configured, it may suggest a field's definition or unit, offered with that cell's
  question and never written into it ([Suggested answers](#suggested-answers)).

Every gap is asked ([Drafting documents](../../docs/specs/drafting.md)). The `Document` carries
one question in `document_questions` for each README section left for the researcher and each
`unknown` cell. In the README, each placeholder is followed by `<!-- dd:gap <question-id> -->`,
which the rendered README does not show. A question's identifier is derived from its gap, so the
same gap has the same identifier in every version. An answer in the request's `draft_answers` is
placed, as given, in the gap or cell it answers, marked `supplied` in a data dictionary, and that
gap is not asked again. In a project, the researcher answers the questions on the draft's card in
the conversation; the harness records each answer and the conductor fills the recorded answers
into the next request, replacing any a caller sent, so only a person's answer is ever placed as
`supplied` (`tests/test_answers_in_a_project.py`).

The README's sections are the common core of the research data README templates compared in
#200: Cornell's Data README, Dryad's and the Borealis working group's minimum README.

It abstains with `insufficient_input` when the request has no inventory, or when a data
dictionary is asked for and no file in the inventory has fields. It abstains with
`outside_agent_scope` for any other kind. When the request gives a `current_version`, the editor
drafts afresh, names that version in `revises` and keeps its title. A regenerated data dictionary
keeps the researcher's values: a value in the current version that differs from what the inventory
gives, or fills a cell it leaves empty, is kept and marked `supplied`. Its rows are the inventory's
fields, so a field no longer in the inventory is dropped.

Its grounding mode is `input_only`, whether or not a model is configured: it cites only its input
(docs/specs/drafting.md, invariant 8). The core `Document` has no `limitations` slot, so the
outcome's statement says how the version was drafted, how many gaps it left and what the editor
does not do.

## Prose written by a model

A model writes only the README's connecting prose (`prose.py`, prompted by `system_prompt.md`).
The gaps, their questions, the tables, the values placed from the metadata record and the
researcher's answers are drafted by rule either way, so a model cannot close a gap, change a value
or rephrase an answer, and a draft with prose has exactly the gaps and questions of the template
draft.

- **What it is given.** The sections it may write for, which are only those with facts to draft
  from (not Methods or Software requirements), and the facts: each file's path, format and size,
  each table's field names, types and formats, the counts of files and tables and the total size,
  the metadata record's title, creators, funders, abstract, licence and publication year, and the
  chosen repository's name and licences. It is never given the data, a field's description, the
  researcher's answers or an earlier version.
- **What is checked.** Each paragraph is used only if it is plain prose (no headings, lists,
  tables or HTML) of at most 1,200 characters, and every number, link, DOI, email address,
  ORCID iD and code-formatted name in it occurs in the facts as given. A paragraph that fails is
  dropped and its section drafted as the template drafts it; the statement says which and why.
  The check catches a made-up identifier or count, not a misleading sentence built from true
  facts, so a person still reads the prose before approving it.
- **How a version is marked.** `document_derivation` is `model` when the version has any prose a
  model wrote, and `template` when no model is configured, the model declined, its reply was not
  JSON or none of its paragraphs was used (docs/specs/drafting.md, "Disclosure is per version").
  The call is recorded with the run: the model, the tokens and the prompt by digest
  (docs/specs/disclosure.md).

## Suggested answers

When a model is configured, it suggests answers to a data dictionary's questions about a field's
definition (`description`) or `unit`, such as that `age_yrs` is the participant's age in years
(`prose.py`, `suggest`, prompted by `suggest_prompt.md`). A suggestion is a question's
`suggested_answer`, with `suggestion_derivation` `model`, and is never placed in the CSV: the
dictionary is drafted by rule before the model is asked, and its text is the template's, byte for
byte. In the app the researcher sees it beside the question, can copy it into the answer box and
change it, and it becomes `supplied` only when they save it as their answer and the dictionary is
drafted again (`tests/test_suggestions.py`; docs/specs/drafting.md, invariant 7).

- **What it is given.** The same facts as the prose (above), and for each question its file, field
  and column. Never a field's description, the researcher's answers or an earlier version.
- **What is offered.** Only a definition or unit, never a type, format or missing-value code. A
  suggestion is dropped if it is longer than 200 characters, is not one line of plain text, or
  names a link, DOI, email address or ORCID iD the facts do not give; the statement says how many
  were offered and which were dropped.
- **How a version is marked.** `document_derivation` stays `template`, because no model wrote the
  dictionary's text. The call is recorded with the run, as for the prose.

## Configuration

`dd-advisor-documentation` reads its own variables (`factory.py`, `config/examples/agents.env`):

| Variable | Meaning |
|---|---|
| `DD_DOCUMENTATION_WRITER` | `template` (default): no prose, no suggestions and no key; `anthropic`: Claude writes the prose and suggests definitions and units. |
| `DD_MODEL_ID` | The model the Anthropic writer calls. |
| `ANTHROPIC_API_KEY` or `ANTHROPIC_API_KEY_FILE` | The Anthropic writer's key. |

The Anthropic writer needs the package's `anthropic` extra. With it, the agent's card declares a
`hosted` model, so the profile's rules on what project content may go to a hosted model apply
(docs/specs/projects.md, invariant 8, TODO(#394, #40)). The CI evaluation runs the template path
(TODO(#576)).

## What it does not do

- It invents nothing. What the inventory and the approved metadata record do not give, the
  methods among it, is left to the researcher as a marked gap.
- It does not open the files, so it says nothing about their contents beyond what the inventory
  records.
- It infers no variable definitions, units or missing value codes. A model's suggested definition
  or unit is only offered, and it suggests no missing value codes or README sections.
- It does not read an earlier README, or the reason a person gave for a decision on a version.
- It follows no data dictionary standard, such as CDIF's variable descriptions (#220).
