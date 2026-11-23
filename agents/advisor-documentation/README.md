# advisor.documentation

**Alpha** (`0.9.0a1`): the Documentation Editor persona of the agent roster
(docs/specs/agents.md), and the drafter of a project's README, data dictionary and Data Management
Plan ([Drafting documents](../../docs/specs/drafting.md)). It is likely to change shape.

The Documentation Editor drafts a README and a data dictionary for a dataset (Blueprint R5), from
the project's file inventory and approved metadata record, and a Data Management Plan from the
decisions made in the project and the researcher's answers. It serves three steps of the process
flow, `setup.documentation`, `preparation.documentation` and `setup.dmp-create` ([A Data
Management Plan](#a-data-management-plan)).

## Before the data are collected

At the Phase 1 step `setup.documentation` the project has no file inventory yet, as its data do not
exist (#1017). Asked for a README then, the editor plans the documentation instead of abstaining.
The README has the same sections, but those with a `plan_ask` in `readme.yaml` (Files, Methods and
Variables) ask what the researcher expects: the files and formats they will produce and how they
will name them, how they will collect and process the data and what to record as they go, and the
variables, units and missing-value codes they expect. The first draft asks first, with a note that
says it is a plan. A model writer is told only that the data are not collected yet
(`data_collected: false`) and is given no files, so it writes prose only from the approved metadata
record, if there is one.

The questions are the same ones the README asks later, so the answers are kept: once the inventory
is added, the README drafted at `preparation.documentation` places them, and the researcher may
revise any answer that changed during collection. A data dictionary is drafted from the inventory's
tables, so before collection the editor abstains on one.

## Ask first, then write

The first time a README is drafted for a project, with no answers recorded yet, the editor does
not return a README full of gaps. It returns a short note (`document_stage` `questions`) saying
what it needs from the researcher and what it already has, with one question for each gap. The
harness refuses to approve or reject such a version. On the app's card, the researcher answers
what they can and presses **Write the README**, which saves their answers and asks, in the
conversation, for the README to be drafted. That run, and every later one, writes the README
(`document_stage` `draft`) from the project's facts and the recorded answers; a gap still open
reads `_Still needed: …_`.

When a model is configured, it writes each section the researcher answered as a whole in its own
words, from their answer together with the project's decisions and the documents they attached,
keeping every value the answer gives. A paragraph that names a number, link, identifier or
code-formatted name that none of these gives is not used, and the answer is placed as given. On
the template path, answers are placed as given. Answers to the parts of General information (the
title, creators, dates, place and funding) are always placed as given.

## Input and output

It accepts the core `DraftRequest` and returns the core `Document`, so its drafts become project
documents ([Projects](../../docs/specs/projects.md)). A request names the `document_kind`:

- `readme`: a Markdown README with the sections of `readme.yaml`. Each gap shows, in italics,
  what is still needed in it. The **Files** section lists the inventory's files with
  their formats and sizes. **Variables** does not repeat the tables' fields: it asks the
  researcher to point to the data dictionary, which describes them, and to give any abbreviations
  or conventions shared across the tables; it lists the standards, vocabularies and formats people
  in the project chose (`standard` project facts, `drafted.py`, #1391), with what each is for, and
  is as before when none was chosen. **Access and licence** lists the licences the chosen
  repository offers, if its requirements name any.

  When the request carries the project's approved metadata record (`metadata_record`, which the
  conductor fills in a project), the README takes from it, as given: the title, as the README's
  heading and in **General information** with the creators, the dates of data collection (its
  `dates` of type `Collected`), the geographic location (`geoLocationPlace`) and the funders; the
  abstract, as the **Description**; the licence, in **Access and licence**; and a citation by the
  creators, the publication year if there is one, and the title, in **How to cite**. These are `supplied`
  ([Drafting documents](../../docs/specs/drafting.md), invariant 2). The abstract says all the
  Description asks, so that section then has no gap; the others keep theirs for what the record
  does not say, such as a part the record leaves empty or the DOI. The editor reads a record in
  DataCite's JSON form (`conforms_to` `http://datacite.org/schema/kernel-4`), as
  `advisor.metadata` drafts it, and skips any value left `null` or blank. It does not use a record
  in any other form, and says so in its statement. With no record, it drafts from the inventory
  alone and says so.

  When a model is configured, as it is by default (below), it also writes the README's prose: an
  overview under the title, and a short paragraph for each section that has facts to draft from,
  introducing them. It also suggests answers to the questions of the Files, Variables, Access and
  licence and Software requirements sections, beside the questions
  ([Suggested answers](#suggested-answers)).
- `data_dictionary`: a CSV with one row per field of each table in the inventory, keyed by `file`
  and `field`. Each of the values `type`, `format`, `description`, `unit`, `unit_code` and
  `missing_values` is followed by a column saying where it came from (`type_source`, …), so that
  a person can check it:
  - `inferred`: read from the data by `dd-inventory`, which infers a field's type and format and
    lists the values it found that are often used for missing data (`-99`, `NA`), or worked out
    by rule, as a unit code is;
  - `supplied`: given by the researcher, either as a description in the inventory or as a value
    in the version being regenerated;
  - `unknown`: no one has said yet, and the cell is empty.

  The editor infers no units, so those are `unknown` until the researcher fills them in. The
  `missing_values` cell lists the codes the inventory's summary found in the field, as
  `inferred`, which says only that they occur, not what they mean; with none found, it is
  `unknown` and asked. Once a field has a unit, its `unit_code` is worked out by rule as the unit's
  [UCUM](https://ucum.org) code, with [`dd-units`](../../units/README.md): "micrometres" becomes
  `um` and "mg per litre" `mg/L`, and a field with no unit gets `n/a`. The statement names the
  first few codes for the researcher to check. A unit code is not asked while its unit is
  unknown, and is asked only when the rule cannot read the unit given, such as "mg/kg, dry
  weight" or "pint" (US or British). A data dictionary is always drafted by rule: a model fills no cell. Where a
  model is configured, it may suggest a field's definition or unit, offered with that cell's
  question and never written into it ([Suggested answers](#suggested-answers)).

Every gap is asked ([Drafting documents](../../docs/specs/drafting.md)). The `Document` carries
one question in `document_questions` for each README section left for the researcher and each
`unknown` cell. A section that asks several separate things lists them as `parts` in
`readme.yaml`, and each part is its own gap and question (`gap_part`), placed as a
`- **<part>:**` line: **General information** asks the title, creators, dates of
collection, location and funding separately, and does not ask any of them when the record gives
it. It asks for the creators by name, and which of them answers questions about the data; their
ORCID iDs, affiliations and email addresses belong to the metadata record, not the README. In the
README, each placeholder is followed by `<!-- dd:gap <question-id> -->`, which the rendered
README does not show. A question's identifier is derived from its gap, so the
same gap has the same identifier in every version. An answer in the request's `draft_answers` is
placed, as given, in the gap or cell it answers, marked `supplied` in a data dictionary, and that
gap is not asked again. In a project, the researcher answers the questions on the draft's card in
the conversation; the harness records each answer and the conductor fills the recorded answers
into the next request, replacing any a caller sent, so only a person's answer is ever placed as
`supplied` (`tests/test_answers_in_a_project.py`).

The README's sections are the common core of the research data README templates compared in
#200: Cornell's Data README, Dryad's and the Borealis working group's minimum README.

It abstains with `insufficient_input` when a README or data dictionary is asked for and the request has no inventory, or when a data
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

## A Data Management Plan

A request for `document_kind` `dmp` drafts a plan in Markdown (`plan.py`). It needs no inventory,
since a plan is written before data are collected. Its sections are a first section of project
details (the title, the researchers and the funding, each asked part by part, and not asked when
the approved metadata record gives it), then the six core requirements of
[`dd-dmp-template`](../../dmp-template/README.md), after Science Europe's, each asking the
template's one-sentence summary, which also asks how long the data will be kept and how the plan
will be kept up to date. Each is drafted from the project's decided facts, as given
(`drafted.py`):

| Section | Drafted from |
|---|---|
| Project details | the decided funders |
| Data description and collection | the confirmed description of the project's data, in the researcher's words, and the inventory's files, if the data already exist; complete when the description says how the data are collected or which existing data are reused |
| Documentation and data quality | the standards, vocabularies and formats chosen |
| Legal and ethical requirements | the sensitive data identified, and how each is to be handled |
| Data sharing and long-term preservation | the chosen and required repositories, the decided licence, and the licences the repository offers |

It asks first, as a README does: with no answers recorded and no current version, the version is
a note (`document_stage` `questions`). Then each answer is placed as given, and every section left
is a gap, marked and asked. A decided funder, the record's title and creators, and a decided
licence are offered beside their questions as the researcher's own words (`shares`).

No model writes a plan's text: `document_derivation` is always `template`. Where a model is
configured and the researcher attached documents, such as a grant application or a protocol, it
may suggest answers to each core requirement's question from those documents and the decisions
alone (`suggest_dmp_prompt.md`), checked as a README's suggestions are, and offered beside the
question, never placed. Without attached documents it is not asked.

What it does not do: it follows one funder-neutral template, not a funder's own; it does not
export a machine-actionable plan (RDA DMP Common Standard, #701); and it does not update a
plan after publication (`post.dmp-update`), which no agent serves yet.

## Prose written by a model

A model writes only the README's prose (`prose.py`, prompted by `system_prompt.md`): the
connecting prose around the facts, and the sections the researcher answered as a whole. The gaps,
their questions, the tables and the values placed from the metadata record are drafted by rule
either way, so a model cannot close a gap or change a value, and a draft with prose has exactly
the gaps and questions of the template draft.

- **What it is given.** The sections it may write for, which are only those with facts to draft
  from or an answer from the researcher, and the facts: each file's path, format and size,
  each table's field names, types and formats (with the summary values the inventory wrote after
  disclosure control, such as a range, mean, categories and missing value codes), the counts of files and tables and the total size,
  the metadata record's title, creators, funders, abstract, licence and publication year, and the
  chosen repository's name and licences. Once a section has been answered, it is also given the
  answers by heading (`researcher_answers`), the project's decisions and the documents the
  researcher attached. It is never given the data, a field's description, an answer to a part of
  General information or an earlier version.
- **How it replies.** The model's reply is constrained to a schema (`ProseReply` in `prose.py`):
  an `overview` and a list of `sections`, each a heading and a paragraph, any of them null. The
  provider holds the model to it; a reply from an endpoint that does not, and that does not match
  once a Markdown fence around it is removed, is not used.
- **What is checked.** Each paragraph is used only if it is plain prose (no headings, lists,
  tables or HTML) of at most 1,200 characters, and every number, link, DOI, email address,
  ORCID iD and code-formatted name in it occurs in what it was given. A paragraph that fails is
  dropped and its section drafted as the template drafts it, with any answer placed as given; the statement says which and why.
  The check catches a made-up identifier or count, not a misleading sentence built from true
  facts, so a person still reads the prose before approving it.
- **How a version is marked.** `document_derivation` is `model` when the version has any prose a
  model wrote, and `template` when no model is configured, the model declined, its reply did not
  match its schema or none of its paragraphs was used (docs/specs/drafting.md, "Disclosure is per
  version"). The call is recorded with the run: the model, the tokens and the prompt by digest
  (docs/specs/disclosure.md).

## Revising a README as you ask

A researcher can ask for changes to the latest README draft in their own words, such as "shorten
the Files paragraph" or "say that sampling was monthly from 2019 to 2021", from the project's
documents page. The harness records the request with the version it names, and the editor is run
with `revise` set; the conductor gives it the current version with the request
(`revision_request`), never a caller's words (docs/specs/drafting.md, invariant 12).

- **What may change.** The current text is split at its blank lines (`revise.py`). Only a
  paragraph of plain prose that is not a value a person gave may change: headings, lists, tables,
  the gaps and their markers, the values placed from the approved metadata record and the answers
  placed as given are kept byte for byte. The model may change, remove or add paragraphs, so a
  revision never fills a gap; the version asks the same questions under the same identifiers.
- **What it is given.** The request, as its instruction (`revise_prompt.md`); the paragraphs it
  may change, by identifier; the sections it may add a paragraph to; and the README as it stands
  and the facts, as data.
- **What is checked.** Each paragraph passes the checks a draft's prose does, against the facts,
  the README as it stands and the request: a number or name the request gives counts as given by
  the person. A paragraph that fails keeps the current text, and the statement says why. If
  nothing usable changed, the editor abstains and drafts no version.
- **Limits.** It revises a README only, and only with a model: without one, or for another kind,
  it abstains and says to edit the document instead. A later redraft from the facts drafts the
  README afresh and does not keep a revision's wording (#1468).

## Suggested answers

Before any model, the editor offers the researcher's own words (#1284, docs/specs/drafting.md,
invariant 11). The parts of General information and the Description and Access and licence
sections that `readme.yaml` marks `shares` carry a `shared_field`, and the answer the researcher
recorded to the same field of the metadata record, or the funder or licence people decided, is
offered as the question's suggestion (`suggestion_derivation: answer`, `suggested_from`), never
written into the README (`dd_sdk.shared_answers`, `tests/test_readme_shared_answers.py`). The model
is not asked about a question that already offers one.

When a model is configured, it suggests answers to some of a draft's questions, replying against a
schema (`SuggestionReply` in `suggestions.py`). For a README, it suggests an answer to the question of
each section `readme.yaml` marks `suggest`: **Files** (how the files relate, from their paths,
formats and fields), **Variables** (a pointer to the data dictionary, and naming conventions plain
from the field names), **Software requirements** (what opens the formats) and **Access and
licence** (a licence from the record or the repository's list, as the researcher's choice), with
`suggest_readme_prompt.md`. It suggests an answer for **Methods** only when the
researcher has attached documents to the project, and only from them (`suggest: documents`). It
never suggests a part of **General information** or the citation: only the researcher can give
them. A README suggestion is checked as the prose is
(above), at most 600 characters, and is offered beside the question; the README's text is the
same with or without it. The README then makes two calls, one for the prose and one for the
suggestions, both recorded with the run and their tokens summed.

For a data dictionary, it suggests answers to the questions about a field's
definition (`description`) or `unit`, such as that `age_yrs` is the participant's age in years
(`suggestions.py`, `suggest`, prompted by `suggest_prompt.md`). A suggestion is a question's
`suggested_answer`, with `suggestion_derivation` `model`, and is never placed in the CSV: the
dictionary is drafted by rule before the model is asked, and its text is the template's, byte for
byte. In the app the researcher sees it beside the question, can copy it into the answer box and
change it, and it becomes `supplied` only when they save it as their answer and the dictionary is
drafted again (`tests/test_suggestions.py`; docs/specs/drafting.md, invariant 7).

- **What it is given.** The same facts as the prose (above), the documents the researcher
  attached (the latest first, up to a fixed length, given as data and never as instructions), and
  for each question its file, field and column. Also, as examples, the definitions and units the
  researcher already gave (`researcher_definitions`, up to 100 rows), so it can suggest the rest in
  their wording and follow the naming conventions they show, and the project's decisions
  (`project_decisions`), such as the standards and vocabularies chosen. Both reach a hosted model
  only as the profile's `hosted_models` allows (`tests/test_dictionary_context.py`).
- **What is offered.** Only a definition or unit, never a type, format or missing-value code. A
  suggestion is dropped if it is longer than 200 characters, is not one line of plain text, or
  names a link, DOI, email address or ORCID iD the facts do not give; the statement says how many
  were offered and which were dropped.
- **How it is asked.** The questions go in batches of at most 30, each its own call, so that a long
  dictionary's reply stays within what the model may write (`replies.py`, #1318). Every call is
  recorded with the run and their tokens are summed.
- **What a bad reply costs.** A reply that does not parse as a whole still gives each suggestion it
  holds complete and in the form asked for: one cut off at the model's length limit keeps those
  before the cut, and one malformed item is dropped alone (`tests/test_suggestion_batches.py`).
  The statement says, in plain words, how many questions got no suggestion and why: the reply was
  cut off, was not in the form asked for, or the model declined. If none got one, it says so and
  that the researcher can answer the questions or draft again.
- **How a version is marked.** `document_derivation` stays `template`, because no model wrote the
  dictionary's text.

## Configuration

`dd-advisor-documentation` reads its own variables (`factory.py`, `config/examples/agents.env`):

| Variable | Meaning |
|---|---|
| `DD_DOCUMENTATION_WRITER` | `model` (default): a model writes the prose and suggests answers; `template`: no prose, no suggestions and no key. `anthropic`, the older value, still works. Unset with no key, the agent stops at start-up and says to set `template`; `dd.py start` sets it for you. |
| `DD_MODEL_PROVIDER` | `anthropic` (default), `openai`, `gemini` or `openai-compatible` ([AI models](../../docs/guide/operations/ai-models.md#choose-a-provider)). |
| `DD_MODEL_ID` | The model the writer calls; Claude Sonnet 5.5 by default with Anthropic, required with any other provider. |
| `DD_MODEL_BASE_URL` | The endpoint, with `openai-compatible` only. |
| The provider's key, such as `ANTHROPIC_API_KEY` or `ANTHROPIC_API_KEY_FILE` | The writer's key, unless it calls through the model broker or a local endpoint that needs none. |
| `DD_MODEL_BROKER_URL` | The [model broker](../../docs/guide/operations/model-broker.md), if the writer calls through it in place of the provider. |
| `DD_MODEL_BROKER_CREDENTIAL` or `DD_MODEL_BROKER_CREDENTIAL_FILE` | The agent's own broker credential, with `DD_MODEL_BROKER_URL`. |

The model writer needs the package's `model` extra. Tests build the editor with
`agent.build()`, which is the template path, or with a `dd_sdk.testing.FakeModel`, so CI needs no
key. With a hosted model, the agent's card declares
it `hosted`, so in a project it runs only where the profile's `hosted_models` lists
`documentation` (docs/specs/projects.md, invariant 8): it is given the approved metadata record
and people's answers. The shipped profiles list it. The CI evaluation runs the template path
([The Documentation Editor evaluation](src/dd_agent_advisor_documentation/evals/README.md)).

## What it does not do

- It invents nothing. What the inventory and the approved metadata record do not give, the
  methods among it, is left to the researcher as a marked gap.
- It does not open the files, so it says nothing about their contents beyond what the inventory
  records.
- It infers no variable definitions or units, and no meaning for a missing value code: it lists
  only the codes the inventory found. A model's suggested definition, unit or README answer is
  only offered, and it suggests no missing value codes, people, dates, places or citation, and
  methods only from documents the researcher attached.
- It does not read an earlier README, or the reason a person gave for a decision on a version,
  except the version a person asked it to revise.
- It follows no data dictionary standard, such as CDIF's variable descriptions (#220).

## Run it

```sh
uv run dd-advisor-documentation serve --port 8114
uv run workbench invoke --agent advisor.documentation --input workbench/samples/soil-survey.readme-with-record.draft.json
uv run pytest agents/advisor-documentation
```

With no model key, set `DD_DOCUMENTATION_WRITER=template` first.
