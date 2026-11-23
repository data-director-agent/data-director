# Drafting documents

## Intent and scope

A drafter is an agent that turns a project's facts into a proposed version of a project document:
a README, a data dictionary or a metadata record (R5, R2). A person approves or rejects each
version ([Projects](projects.md)), and a published document goes out under the researcher's name.
So the person deciding must be able to tell which parts were read from the data, which were given
by a person, and which the agent could not know.

This spec says what a drafter may infer, what it must ask the researcher instead, what a language
model may write, and how a draft keeps these apart. It does not cover how documents, versions and
decisions are recorded ([Projects](projects.md)), what a drafter may cite
([Evidence and grounding](grounding.md)), or how a model's part in an approved document is
disclosed ([Disclosure](disclosure.md)).

The Documentation Editor (`advisor.documentation`) is the first drafter. It serves
`preparation.documentation` and drafts a README or a data dictionary from a `DraftRequest`. It
also serves `setup.documentation`, planning the documentation before data are collected (#1017).
A drafter infers only from a file inventory (invariant 1), which a project has only once its data
exist, so before then it infers nothing: a README is drafted from the approved metadata record and
the decisions, if any, with the sections that plan what to record (`plan_ask`) asking what the
researcher expects to produce, under the same questions as the README drafted later, which places
their answers. A data dictionary needs the inventory's tables, and the drafter abstains without
them. Where a model is configured, as it is by
default, a model writes the README's prose
([`agents/advisor-documentation/README.md`](../../agents/advisor-documentation/README.md)). The
researcher answers its questions in the conversation, and the next draft places their answers.
A README asks first: the first time one is drafted for a project, if the facts leave anything for
the researcher to say, the editor returns a note that asks for it (a version at the `questions`
stage) instead of a README full of gaps, and writes the README on the next run, from whatever
answers are recorded by then.
Where a model is configured, it also suggests a data dictionary's definitions and units, and
answers to some of a README's questions, offered with the questions, and revises a README's prose
as the researcher asks in their own words, such as "shorten the Files paragraph" (invariant 12).

The Metadata Librarian (`advisor.metadata`) drafts the metadata record by the same rules. It
serves `preparation.metadata` and drafts the record from a `DraftRequest` with the chosen
repository's requirements, asks about every value it leaves null, and places the answers recorded to
them. It drafts in the standard those requirements follow ([Metadata standards](metadata-standards.md));
today that is DataCite in its JSON form alone, TODO(#1359). Its model, on unless the operator turns it off,
suggests some of those values beside their questions
([`agents/advisor-metadata/README.md`](../../agents/advisor-metadata/README.md)).

The Documentation Editor also drafts a Data Management Plan (`dmp`), an alpha that serves
`setup.dmp-create`. Its sections are the core requirements of
[`dd-dmp-template`](../../dmp-template/README.md), after Science Europe's, under a section of
project details. A plan is drafted before data exist, so it needs no inventory: it infers nothing,
and places only what is supplied (invariant 2): the funders, the required repository, the licence,
the sensitive data and their handling, the standards, the description of the data, and what the
project is for, its field and period (placed in Project details), that people in the project
decided, as project facts give them, the inventory's files if the data already exist, and
the researcher's answers. A confirmed data description (`data_description`) fills the plan's data
section, in the researcher's words, and completes it when it says how the data are collected or
which existing data are reused; one that says only what is collected is placed and the section is
still asked. It asks first, as a README does, and every other gap is asked. Its sharing and
preservation question asks for what is intended, since the repository and the licence are chosen
later (Phases 3 and 5) and the plan is updated once they are (`setup.dmp-review`,
`post.dmp-update`). In Phase 1 the plan is written after the requirements are found out
(`setup.requirements`) and before the documentation, storage and formats steps, so it asks those
sections itself; sharing an answer given in one place with the other is TODO(#1537). No model writes a plan's text, so
`document_derivation` is always `template`; where a model is configured, it suggests answers only
from the documents the researcher attached and the project's decisions, beside the questions
(invariant 7). The Data Management Planner (`advisor.dmp`) reviews a plan against the same
requirements (`setup.dmp-review`): an attached plan, or, once a version is approved, the plan
written here, which reopens the review after a "No" to having a plan ([Projects](projects.md),
rule 20 and invariant 32).

## Invariants

1. **Inferred means read from the project's facts.** A drafter infers only what the file inventory
   and the chosen repository's requirements record: the files, their formats and sizes, the
   tables, and each field's name, type and format, and the summary values the command wrote
   after disclosure control (a range that leaves out the extremes, a mean, categories and
   missing-value codes with rounded counts). It opens no file. A data dictionary's missing-value
   codes are inferred from them; a writer may describe a field with them but never says what a
   code means, nor calls a range's bounds the minimum and maximum
   ([Personal data and disclosure control](personal-data.md), #571, #611). A data dictionary's
   `unit_code` is also inferred: it is worked out by rule (`dd-units`) from the unit the field
   is given, whoever gave it, as its [UCUM](https://ucum.org) code, or `n/a` for a field given
   no unit. The rule reads only that unit, accepts a UCUM name, print symbol or code as a person
   writes it ("micrometres", "°C", "mg/L"), never guesses between two units that share a name,
   and leaves the cell `unknown` when it cannot tell. The researcher checks the code when they
   review the version, and the outcome's statement names the first few codes for them to check.
2. **Supplied means given by a person.** A value is supplied when it comes from a field
   description in the inventory, from the project's approved metadata record (the version a
   person approved last, [Projects](projects.md), invariant 6), from a person's edit of an earlier
   version, or from an answer a person recorded (invariant 6). A drafter places a value from the
   record as the record gives it, and leaves a gap where the record holds only a placeholder.
3. **A data dictionary marks every value's source, and a model fills no cell.** Each value is
   followed by its source: `inferred`, `supplied` or `unknown`, and there is no other value. An
   `unknown` cell is empty. A model never writes a cell's value, a unit code included: the
   dictionary is drafted by rule before a model is asked anything, and a model-backed draft's
   text is the template's, byte for byte (`agents/advisor-documentation/tests/test_documentation_agent.py`,
   `agents/advisor-documentation/tests/test_suggestions.py`). The evaluation scores it for every
   case (`no_model_value_in_cell`), and its tests run it with a fake model too
   (`agents/advisor-documentation/tests/test_documentation_evals.py`).
4. **A model writes README prose only from the drafter's input and the researcher's answers.**
   That input is the inventory, the metadata record and the repository's requirements. Once the
   researcher has answered a README section as a whole, the model is also given their answers by
   section, the project's decisions and the documents they attached, and may write that section
   from them; it is never given an earlier version, except the one a person asked it to revise
   (invariant 12), nor an answer to a part of General information, which is placed as given. What none of these supports is a gap and is left
   unwritten: methods, study design, data collection, variable definitions, units, missing value
   codes, and any claim about the data's contents that no answer makes. The gaps are decided by
   rule, not by the model: a model writes prose only around the facts a section is drafted from or
   the answer the researcher gave it, never in a section with neither, and a draft with prose has
   the same gaps and questions as the template's. The drafter uses a paragraph only if every
   number, link, identifier and code-formatted name in it is in what the model was given
   (`agents/advisor-documentation/tests/test_prose.py`). Counts are worked out by rule: the input
   gives the number of files, tables and folders, of files at the top level and of files in each
   folder, and a paragraph that states another count of files, folders or tables, in digits or
   in words, or another number of files at the top level, is not used. That check catches an
   invented value, not a misleading sentence or a dropped one, so the person approving the
   version still reads the prose.
5. **Every gap is marked and asked.** A README gap is an italic placeholder saying what is needed,
   followed by the HTML comment `<!-- dd:gap <question-id> -->`, which the rendered README does not
   show; it reads `_Still needed: …_`, saying what is needed. A README section that asks several
   separate things, such as General information's title,
   creators, dates and funding, is asked part by part: each part the facts do not
   give is its own gap, on a `- **<part>:**` line, with its own question. A data dictionary gap is
   an `unknown` cell, except that the `unknown` cells of a column several files share are one
   gap: a column is shared when files hold a field of the same name, type and format, as a study
   whose runs each write the same table does, and a field of the same name with another type or
   format is a column of its own. The dictionary still has a row for each field of each file. Each
   gap has exactly one question in the version's `document_questions` whose target names it, so a
   study of many runs is asked as many questions as one of two
   (`agents/advisor-documentation/tests/test_documentation_agent.py`,
   `agents/advisor-documentation/tests/test_shared_columns.py`, #1317). A `unit_code` follows its
   file's unit, so files share its gap only if they give the same unit, and one whose `unit` is still `unknown` is
   not asked, because it is worked out once the unit is given (invariant 1). Its question appears only if the rule cannot read the
   unit given (`agents/advisor-documentation/tests/test_unit_codes.py`).
6. **An answer is supplied only when a person recorded it.** A person answers the latest version's
   questions in the app, on the draft's card in the conversation or on the project's documents
   page. Each answer is a `document_question_answered` event that names the person it acted for,
   as any other event does ([Projects](projects.md), `harness/docs/projects.md`); an answer to another version, or to a
   question that version does not ask, is refused. When a document of that kind is drafted
   again, the conductor puts into the `DraftRequest`'s `draft_answers` the latest answer recorded
   to each question of the project's documents of that kind, replacing any a caller sent, as it
   puts in the inventory (`harness/tests/test_project_runs.py`). The answers stand until the
   person answers again, because a question's identifier is the same in every draft. The drafter
   places each answer, as given, in its gap or cell and marks it `supplied`, and asks that gap no
   more (`agents/advisor-documentation/tests/test_answers_in_a_project.py`). An answer to a shared
   column's question goes in that column's cell in each file that shares it. A person who wants one
   file's cell to say something else edits that file's row: a value given for one file, by an edit
   or by an answer to that file's own cell, stands for that file over the shared answer
   (`agents/advisor-documentation/tests/test_shared_columns.py`). In a README, a model
   may write a section the researcher answered as a whole in its own words, keeping every value
   the answer gives (invariant 4); where it does not, or its paragraph fails the checks, the
   answer is placed as given. The recorded answer is what is `supplied`, and it stays on the
   project log beside the version. An orchestrator may put a question to the researcher, but it
   cannot answer one.
7. **A model's suggestion is only ever offered.** A drafter may suggest an answer, for example that
   `age_yrs` is the participant's age in years. The suggestion appears in the question
   (`suggested_answer`, with `suggestion_derivation`), never in the document's text, and a version
   with suggestions keeps the derivation of its text. The app puts it in the question's box, marked
   as a model's, for the person to check. It becomes `supplied` only when a person confirms or
   corrects it, by accepting or saving it as an answer
   (`agents/advisor-documentation/tests/test_suggestions.py`). The Documentation Editor suggests
   only a data dictionary field's definition and unit, never its type, format or missing-value
   codes; and an answer for the README sections its template marks `suggest` (Files, Variables,
   Access and licence, Software requirements), never a part of General information or the
   citation, which only the researcher can give. Methods is marked `suggest: documents`: it is
   asked about only when the draft carries documents the researcher attached, and its suggestion
   says only what those documents state, never a method inferred from the files. Its model is
   given the same input as the README's prose (invariant 4) and the documents the researcher
   attached to the project (`project_documents`), the latest first and cut to a stated length, as
   data and never as instructions, so that what their field notes or codebook say can be offered
   for them to confirm. For a README it is never given an answer or an earlier version. For a data
   dictionary it is also given, as examples, the definitions and units the researcher already
   gave (`supplied` in the drafted dictionary, at most a stated number of rows), so that it can
   suggest the rest in their wording and with the naming conventions they show; and the
   project's decisions (`project_decisions`, such as the standards and vocabularies chosen),
   which are structured values. These are content of the `documentation` and `decisions` classes
   and reach a hosted model only as the profile's `hosted_models` allows
   ([Projects](projects.md), invariant 8). The model still never writes a cell
   (`agents/advisor-documentation/tests/test_dictionary_context.py`). The outcome's
   statement names the documents it was given and any cut short
   (`agents/advisor-documentation/tests/test_attached_documents.py`). A
   dictionary suggestion is offered only if it is one short line of plain text that names no
   link, email address or identifier its input does not give; a README suggestion only if it
   passes the checks the prose does. The questions are asked in batches, and a reply that does not parse
   as a whole costs only the suggestions it does not hold complete and well formed: a reply cut
   off at the model's length limit, or one malformed item, never discards the rest. The outcome's
   statement says how many questions got no suggestion and why, in plain words
   (`agents/advisor-documentation/tests/test_suggestion_batches.py`, #1318). The Metadata Librarian suggests only the values its rule
   table marks `suggest` (`agents/advisor-metadata/src/dd_agent_advisor_metadata/datacite.yaml`):
   a title, a description, a free keyword and a language; never a creator, contributor, date,
   rights statement, funder, related identifier or place, which only the researcher can give.
   An entry the repository asks for from a named subject classification, such as ORDA's
   categories from the ANZSRC Fields of Research, is suggested only from that classification's
   fields, retrieved through the tool gateway before the model is called: the model gives the
   code of one of them, a code the set does not hold is dropped, and the suggestion offered is
   the label of the field's own record, which the payload cites
   (`agents/advisor-metadata/tests/test_metadata_categories.py`, #703). With no tools grant, it
   suggests no such entry and says so. Keywords from other vocabularies wait for the choice of
   terminology services, TODO(#956). Its model is
   given the repository's requirements and the inventory's structure, never an answer, a
   description a person wrote, the researchers' records or an earlier version, and a suggestion
   is offered only if it is one line of plain text that names no link, DOI, email address or
   ORCID iD its input does not give (`agents/advisor-metadata/tests/test_suggestions.py`).
   A suggestion may instead copy the person's own words: see invariant 11.
8. **A drafter rests on its input.** The grounding mode of the Documentation Editor is
   `input_only`, whichever way a particular version was drafted: the document and the answers
   reach it in its input, never by retrieval, so it cites only its input. The Metadata
   Librarian's is `retrieval`, because a category it suggests rests on a classification's record
   it retrieved through the tool gateway (invariant 7). It records reading its input as its first
   retrieval and cites its input, and each such record beside it; the record and the answers
   still reach it only in its input. `document_derivation` records how each version came about: `model`, or
   `template` when no model is configured or none of the model's draft was used. The manifest names it
   as the recorder of `document_text` (`recorded_in`, [Agents](agents.md)).

9. **A decided fact is supplied; a proposed one is not.** In a project, a `DraftRequest`'s
   `project_decisions` are the facts a person decided about it ([Projects](projects.md),
   invariant 28): which files go in, whether sensitive fields or files may be published and how,
   its funders, the repositories required and its licence. A drafter treats each as supplied.
   What a check agent only proposed never reaches a drafter. The Metadata Librarian asks whether
   a location may be published, and at what precision, before it asks for the place, and takes
   the project's `sensitivity` decisions about locations as that answer: it asks for the place
   at the coarsest precision decided, or leaves it empty and asks no more when every location is
   withheld, saying so in its statement (`agents/advisor-metadata/tests/test_metadata_location.py`).
   How each drafter leaves an excluded file out of the README's Files table, the data dictionary
   and the metadata record's formats and sizes, listing it with its reason, is TODO(#1072).
10. **A README asks before it writes.** When a README is drafted with no current version and no
    answer recorded to any of its questions, and the facts leave a gap, the Documentation Editor
    returns a `Document` whose `document_stage` is `questions`: its text is a short note saying what
    it asks and what the README will be written from, with no gaps of its own, and its questions
    are every gap's. The harness records it as a version but refuses any decision on it
    (`version-not-a-draft`, `harness/tests/test_project_documents.py`), and the app shows its
    questions on its card with a button that asks for the README to be written. The next run, with
    or without answers, writes the README (`document_stage` `draft`), and asks the same questions
    of the gaps still open, under the same identifiers
    (`agents/advisor-documentation/tests/test_documentation_agent.py`). A data dictionary and a
    metadata record are drafted at once, as before.
11. **A person's answer is offered wherever it is asked again, never placed there.** Some values
    every kind of document gives the same way: the dataset's title, its creators, its abstract,
    when and where the data were collected, its funder and its licence (`SharedField`, #1284). A
    drafter names the one a question asks for in its `shared_field`, from its own template: the
    Metadata Librarian's rule table marks the first entry of `titles`, `creators`,
    `descriptions` (Abstract), `dates` (Collected), `geoLocations`, `fundingReferences` and
    `rightsList` with `shares`
    (`agents/advisor-metadata/src/dd_agent_advisor_metadata/datacite.yaml`), and the Documentation
    Editor's README template marks the parts of General information and the Description and
    Access and licence sections (`readme.yaml`). In a project the conductor gives a drafter
    `shared_answers`: for each shared field, the latest answer a person recorded to a question on
    it of a document of another kind, with the question and the kind it was answered for
    (`harness/tests/test_shared_answers_in_a_project.py`). The drafter offers it as the open
    question's `suggested_answer`, with `suggestion_derivation` `answer` and `suggested_from`
    naming the kind; where nobody answered, it offers a decided funder or licence
    (`project_decisions`, invariant 9) with `suggested_from` `decision`; and for the creators,
    the project's people who kept a name in their ORCID record (`researchers`), one per line,
    with `suggested_from` `researchers` (`dd_sdk.shared_answers`). Who answers questions about the
    data is not known, so the person says it. Such a suggestion copies the person's own words, so it may fill a
    field no model may suggest, a creator, date, place, funder or licence; but it is still only
    offered, kept out of the document's text, and recorded for that document only when the person
    accepts or saves it there, as any suggestion is (invariant 7). A person's words come before a
    model's: a drafter asks its model only about the questions left without a suggestion. The app
    says where a copied suggestion came from, never that a model made it
    (`agents/advisor-metadata/tests/test_metadata_shared.py`,
    `agents/advisor-documentation/tests/test_readme_shared_answers.py`).

12. **A revision changes prose as a person asked, and nothing a person gave.** A person may ask
    for changes to the latest version of a README, when it is a draft, in their own words. The
    request is a `document_revision_requested` event naming the version, the digest of the text
    they saw and their words, and is refused like an edit if either is not the latest
    ([Projects](projects.md), invariant 12). A drafter asked to revise (`DraftRequest.revise`) is
    given that version with the request (`CurrentVersion.revision_request`), which only the
    conductor fills, from the log, so the words a drafter follows are always a person's; a request
    to revise that names no recorded request is refused. The Documentation Editor splits the
    version at its blank lines and lets its model change, remove or add only paragraphs of plain
    prose: headings, lists, tables, every gap with its marker, and every paragraph that is an
    answer as given or a value placed by rule from the facts are kept byte for byte, so a revision
    never closes a gap and asks the same questions under the same identifiers
    (`agents/advisor-documentation/tests/test_revise.py`). The request is the model's instruction;
    the version and the facts are data. A paragraph is used only if it passes the checks of
    invariant 4 against the facts, the version and the request: a number or name the request
    gives counts as given by the person, as an answer does, and anything else the check finds is
    dropped, the paragraph keeping its text, with the reason in the statement. A revision is
    `model`. If no model is configured, the document is not a README, or nothing usable changed,
    the editor abstains and drafts no version, saying why. A later redraft from the facts drafts
    the README afresh and does not keep a revision's wording, TODO(#1468).
13. **A person asks for the next draft when they choose.** Nothing redrafts a document on its own
    when answers are saved. A person may ask the agent that drafted a document to draft it again
    from the project's recorded answers at any time: at either stage, and whether or not any
    question is left open. The request names the latest version the person was shown and nothing
    else; the app answers `409` and runs nothing if it is no longer the latest, or if no agent
    drafted the document. The drafter is given `redraft_document` and not `revise`, so the
    conductor fills `current_version`, `draft_answers` and `shared_answers` as for any redraft in a
    project, and the drafter writes the document afresh, placing every answer recorded and asking
    the gaps still open (invariants 6 and 10). The run is the request: no other event is recorded
    (`app/tests/test_document_drafts.py`).

## Boundaries and contracts

**Questions belong to the version.** A `Document` carries an optional list of questions
(`document_questions`), and the project log keeps them with the version they were asked of
(`harness/docs/projects.md`). A question (`DocumentQuestion`) has an identifier, `q-` and 16
hexadecimal digits, that is stable within the document across regenerations, so it is derived
from what the question fills and never from its position; the Documentation Editor takes the
digits from the SHA-256 of its target. A shared column's target is the field's name, type and
format and the dictionary column, never the files, so leaving a file out or adding one keeps the
question and its answer. It also has the text put to the person and its target: a
README section (`gap_section`), with the part of it (`gap_part`) when the section is asked part by
part, a data dictionary cell named by `gap_file`, `gap_field` and `gap_column`, with every file
whose cell the answer fills in `gap_files` when the column is shared (invariant 5), or a metadata
record value named by its path in the record's JSON form (`gap_property`, such as
`titles[0].title`). A metadata record marks a gap by leaving its value `null`, since JSON has no
comments. An answer (`DraftAnswer`) names the question it answers and gives the text. The
classes are in the core contract because the conductor, the app and an orchestrator all read them
without knowing the drafter. A question may carry a suggested answer (`suggested_answer`) with
how it was derived (`suggestion_derivation`); the one is present exactly when the other is. A
question may name the shared value it asks for (`shared_field`), and a suggestion derived as
`answer` names where it came from (`suggested_from`, invariant 11). A suggestion a drafter composed
by rule from what the deployment's profile vouches for is derived as `template` with
`suggested_from` `institution`: the Documentation Editor offers the institution's storage
services (`institution_storage`, which the conductor fills into every `DraftRequest`) to a Data
Management Plan's question on storage and backup. They say what is available, not what the
project will use, so they are only offered, as any suggestion is (invariant 7), and the app says
they come from the institution's own list, not a model
(`agents/advisor-documentation/tests/test_dmp_storage.py`). A set
of choices, as a reply's choice `Question` has, is added with the first drafter that
sets one, TODO(#529).

**Who does what.** The drafter writes the gaps and the questions. An orchestrator tells the
researcher that a draft has questions and where to answer them, offers to redraft once they have,
and says that the draft came from a mock when it did; it never accepts a suggestion for the
researcher. The app shows the latest version's open questions on the draft's card in the
conversation and in the Questions tab of the project's documents page, each as a text box
labelled by the question and described by what it fills. Those a model suggested an answer for come
first, all at once, each box starting with the suggestion and saying where it came from, a model
or the researcher's own answer for another document or a decision (invariant 11); the
researcher checks them, changes or clears any, and records them with one "Accept" button. Those
with no suggestion follow three at a time, or more to keep one section's parts together, in blank
boxes. Each question links to a new conversation to talk it through, but its answer is recorded
only on the draft. The card and the documents page list the answered questions beneath the form
(folded on the documents page), each with its saved answer and a way to change it, which records a
new answer; the documents page lists an earlier version's questions read-only ([The app](app.md)). It sends the answers to
`POST /api/projects/{id}/documents/{document_id}/answers`, which records them for the person
signed in and never takes a name from the body. The harness records each answer and fills the
answers into the next `DraftRequest`. No agent writes an answer.

**A request for changes goes to the drafter.** The project's documents page offers a form beneath
a README's latest draft to ask for changes ([The app](app.md)). It sends the person's words with
the version and the digest of its text to
`POST /api/projects/{id}/documents/{document_id}/revisions`, which records the request for the
person signed in, then runs the agent that drafted the document with a `DraftRequest` that sets
`revise` and names the document, in the project and no conversation ([Projects](projects.md),
invariant 7). The app names no agent: it runs the one whose run drafted the document's latest
drafted version. It answers with the documents and the run's outcome, whether or not the run
drafted a version. A request from a conversation, relayed by an orchestrator, is TODO(#1470).

**An answer outlives its version.** The conductor gives a drafter the latest version of the
document it redrafts, so a redraft is that document's next version. A drafter is given the answers
recorded for every document of the kind it drafts, not only the latest version's: a project drafted
before redrafts kept their document may hold two of one kind, and a question's identifier,
derived from its target, finds its answer in whichever draft asked it. Answers recorded for
documents of other kinds reach it only as `shared_answers`, to offer, never to place (invariant
11).

**Model access.** A metadata record and a person's answers are `documentation`-class project
content, so they go to a drafter with a hosted model only where the institutional profile allows
it in its `hosted_models` ([Projects](projects.md), invariant 8). A drafter places answers by rule, so it
can use them without a model.

**Limitations go in the statement.** The core `Document` has no `limitations` slot, so a drafter
says in the outcome's statement what its draft does not do: that it drafted on the template path,
how many gaps it left and how many questions it asked, and, for a mock, that it is one
([Agents](agents.md)).

**The template path stays.** A drafter that calls a model keeps a deterministic path, used when no
model is configured and run by the CI evaluation
(`agents/advisor-documentation/src/dd_agent_advisor_documentation/evals/`). A version drafted on that path
records `template`.

**Disclosure is per version.** A version drafted with a model is disclosed as `model`, even where
some of its text was placed from a person's answers ([Disclosure](disclosure.md)). That
over-discloses and never under-discloses. A data dictionary whose questions carry a model's
suggestions is `template`, because no model wrote its text; the run that suggested them records
its model calls as any other does. A value a person took from a suggestion is theirs, `supplied`,
as any other answer is.

## Rationale

- **Provenance is what a reviewer approves.** A person deciding on a version is vouching for a
  research output. They can do that only if they can see what a model wrote and what a person gave
  (C13, C15).
- **Ask first, then write.** A first README that is mostly placeholders reads as a form, not a
  document, and invites approving it half-written. Asking before writing puts the researcher's
  knowledge in first, so that the first README they review is one written from it.
- **A question, not a value.** A model can often guess a field's meaning from its name, but a guess
  is not something the data show. Offered as a question, it saves the researcher typing. Written as
  a value, it would be published unchecked. In the workshop, participants filled 36 empty
  dictionary rows by hand (#445). Questions take that work into the conversation without letting a
  model fill the rows.
- **Answers recorded by the harness.** Only an answer the harness recorded, against the person it
  acted for, can honestly be called `supplied`. A model's reading of a chat reply cannot.
- **A unit code worked out, not asked.** A UCUM code is a fact about the unit the researcher
  already gave, not new knowledge, and few researchers know UCUM's spelling of their unit
  (`um`, `Cel`, `[ppm]`). Asking for it would add a question for every measured field (#891).
  Worked out by a rule that refuses what it cannot tell, and marked `inferred`, it is checked as
  the type and format are: by the person reviewing the version, who can edit it, after which
  it is theirs, `supplied`. An earlier code the rule worked out from an earlier unit is not
  taken as an edit, so a changed unit gets a fresh code.
- **Gap identifiers, not headings.** A person may rename or reorder a README's sections. A gap that
  carries its question's identifier still matches its answer, and the app and the evaluation can
  count gaps without parsing prose.

- **A revision in a person's words, checked as a draft is.** Editing by hand is precise but slow
  for a change of tone or length; asking in words is quick, and a person still reviews the result
  as a new version, with its differences shown. Keeping every gap, table and value as it was by
  rule, not by the model's restraint, means a revision can make prose worse but cannot lose what a
  person gave or hide what is still missing.

## Rejected alternatives

- **The orchestrator gathering the README's answers in the chat before drafting.** It would need
  the orchestrator to pass answers to the drafter, which is rejected below. The `questions` version
  keeps the questions on a version, where the harness records each answer for a person.

- **The model deciding which gaps remain.** A model that judged a section fully written could close
  a gap with a guess. The gaps are a rule of the template, and the model writes around them.
- **Abstaining when the metadata record is withheld.** Where the profile does not let the record
  go to a hosted model, the request reaches the drafter without it, and the drafter drafts from
  the inventory alone, as it does for a project with no approved record, and says so. The record's
  sections are then gaps, which is what they would be with no record.

- **Asking for every unit code, with the rule's code as a suggestion.** It keeps every code a
  person's answer, but doubles the unit questions for codes most researchers would accept
  unread. The rule's code is shown in the version they approve instead.
- **A fourth source value, `suggested`.** It would put a model's guess in a data dictionary that is
  published as the researcher's, marked only by a column a reader may never look at.
- **The orchestrator passing answers to the drafter.** A `DraftRequest` slot filled by the
  orchestrator would be simpler and would work with plain chat. But a model's interpretation of the
  researcher's words would then become `supplied`, with only the approval to catch a mistake. What
  the researcher says of their data in a conversation reaches a drafter instead as a
  `data_description` fact the orchestrator proposes and a person confirms
  ([Projects](projects.md), invariant 28): a person decides it before any drafter is given it.
- **Answers only by editing the draft.** Editing still works, and its values become `supplied` on
  regeneration. As the only way, it leaves the researcher to find each gap themselves.
- **A source marker on every README section.** It is more precise than marking only the gaps, but a
  person's edit easily leaves a marker that no longer describes the text under it.
- **Questions in an agent-owned subclass of `Document`.** The conductor records a version only from
  a payload of the core `Document` class, so a subclass would never become a project document.
- **Questions on the `Outcome`.** The outcome is the agent's decision about the run, and a question
  is about the version. The version is where the app and the next regeneration look for it.

- **The orchestrator paraphrasing the request into the drafter's input.** It would put a model's
  words where the person's belong, and let a turn ask a drafter for changes nobody recorded. The
  conductor fills `revision_request` from the log alone, as it fills answers.
- **Revising by drafting afresh with the request as one more fact.** A redraft rebuilds the README
  from the facts and drops any wording a person or an earlier revision gave it, so "shorten this"
  would undo everything else. A revision changes the version the person read.
- **Running a revision as a turn in the conversation that drafted the document.** It would add a
  turn the person did not send to that conversation, and a turn the conversation's open page would
  not follow. A revision is a run in the project and no conversation instead.

## Non-functional requirements

- **Privacy.** A drafter sees the inventory, never the data, and the inventory carries only the
  summary values that passed disclosure control on the researcher's computer
  ([Personal data and disclosure control](personal-data.md), #571, #611). Project content other than the
  inventory reaches a hosted model only as the profile allows.
- **Accessibility.** Questions are answered through the app's form controls, whose accessibility
  is set out in #529.

## Open questions

- Whether a data dictionary should follow CDIF's variable descriptions, and be exported as DDI-CDI:
  TODO(#220).
- Whether the README itself should state how generative AI was used to draft it: TODO(#478).
- How a Data Management Plan is revised as a person asks: TODO(#1469).
