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
`setup.documentation` and `preparation.documentation` and drafts a README or a data dictionary
from a `DraftRequest`. Where a model is configured, a model writes the README's prose
([`agents/advisor-documentation/README.md`](../../agents/advisor-documentation/README.md)). The
researcher answers its questions in the conversation, and the next draft places their answers.
Where a model is configured, it also suggests a data dictionary's definitions and units, offered
with the questions. A metadata record drafter follows the same rules when it is built.

## Invariants

1. **Inferred means read from the project's facts.** A drafter infers only what the file inventory
   and the chosen repository's requirements record: the files, their formats and sizes, the
   tables, and each field's name, type and format. It opens no file. Per-field summary values,
   such as ranges, counts or categories, are not inferred, because the inventory does not carry
   them until there is statistical disclosure control (#571).
2. **Supplied means given by a person.** A value is supplied when it comes from a field
   description in the inventory, from the project's approved metadata record (the version a
   person approved last, [Projects](projects.md), invariant 6), from a person's edit of an earlier
   version, or from an answer a person recorded (invariant 6). A drafter places a value from the
   record as the record gives it, and leaves a gap where the record holds only a placeholder.
3. **A data dictionary marks every value's source, and a model fills no cell.** Each value is
   followed by its source: `inferred`, `supplied` or `unknown`, and there is no other value. An
   `unknown` cell is empty. A model never writes a cell's value: the dictionary is drafted by rule
   before a model is asked anything, and a model-backed draft's text is the template's, byte for
   byte (`agents/advisor-documentation/tests/test_documentation_agent.py`,
   `agents/advisor-documentation/tests/test_suggestions.py`). The evaluation checks it for a
   model-backed drafter too (TODO(#576)).
4. **A model writes README prose only from the drafter's input.** That input is the inventory, the
   metadata record and the repository's requirements; the model is never given an answer or an
   earlier version. What they do not support is a gap and is left unwritten: methods, study
   design, data collection, variable definitions, units, missing value codes, and any claim about
   the data's contents. The gaps are decided by rule, not by the model: a model writes prose only
   around the facts a section is drafted from, never in a section with none, and a draft with
   prose has the same gaps and questions as the template's. The drafter uses a paragraph only if
   every number, link, identifier and code-formatted name in it is in its input
   (`agents/advisor-documentation/tests/test_prose.py`). That check catches an invented value,
   not a misleading sentence, so the person approving the version still reads the prose.
5. **Every gap is marked and asked.** A README gap is an italic placeholder saying what is needed,
   followed by the HTML comment `<!-- dd:gap <question-id> -->`, which the rendered README does not
   show. A README section that asks several separate things, such as General information's title,
   creators, dates and funding, is asked part by part: each part the facts do not
   give is its own gap, on a `- **<part>:**` line, with its own question. A data dictionary gap is
   an `unknown` cell. Each gap has exactly one question in the
   version's `document_questions` whose target names it
   (`agents/advisor-documentation/tests/test_documentation_agent.py`).
6. **An answer is supplied only when a person recorded it.** A person answers the latest version's
   questions in the app, on the draft's card in the conversation. Each answer is a
   `document_question_answered` event that names the person it acted for, as any other event does
   ([Projects](projects.md), `harness/docs/projects.md`); an answer to another version, or to a
   question that version does not ask, is refused. When a document of that kind is drafted
   again, the conductor puts into the `DraftRequest`'s `draft_answers` the latest answer recorded
   to each question of the project's documents of that kind, replacing any a caller sent, as it
   puts in the inventory (`harness/tests/test_project_runs.py`). The answers stand until the
   person answers again, because a question's identifier is the same in every draft. The drafter
   places each answer, as given, in its gap or cell and marks it `supplied`, and asks that gap no
   more (`agents/advisor-documentation/tests/test_answers_in_a_project.py`). A model does not
   rephrase an answer. An orchestrator may put a question to the researcher, but it cannot answer
   one.
7. **A model's suggestion is only ever offered.** A drafter may suggest an answer, for example that
   `age_yrs` is the participant's age in years. The suggestion appears in the question
   (`suggested_answer`, with `suggestion_derivation`), never in the document's text, and a version
   with suggestions keeps the derivation of its text. It becomes `supplied` only when a person
   confirms or corrects it, by recording an answer
   (`agents/advisor-documentation/tests/test_suggestions.py`). The Documentation Editor suggests
   only a data dictionary field's definition and unit, never its type, format or missing-value
   codes, nor a README section. Its model is given the same input as the README's prose
   (invariant 4), never an answer, a field's description or an earlier version, and a suggestion
   is offered only if it is one short line of plain text that names no link, email address or
   identifier its input does not give.
8. **A drafter rests on its input alone.** The Documentation Editor's grounding mode is
   `input_only`, whichever way a particular version was drafted. The metadata record and the answers reach it in its input, never by retrieval, so it
   cites only its input. `document_derivation` records how each version came about: `model`, or
   `template` when no model is configured or none of the model's draft was used. The manifest names it
   as the recorder of `document_text` (`recorded_in`, [Agents](agents.md)).

## Boundaries and contracts

**Questions belong to the version.** A `Document` carries an optional list of questions
(`document_questions`), and the project log keeps them with the version they were asked of
(`harness/docs/projects.md`). A question (`DocumentQuestion`) has an identifier, `q-` and 16
hexadecimal digits, that is stable within the document across regenerations, so it is derived
from what the question fills and never from its position; the Documentation Editor takes the
digits from the SHA-256 of its target. It also has the text put to the person and its target: a
README section (`gap_section`), with the part of it (`gap_part`) when the section is asked part by
part, or a data dictionary cell named by `gap_file`, `gap_field` and `gap_column`. An answer (`DraftAnswer`) names the question it answers and gives the text. The
classes are in the core contract because the conductor, the app and an orchestrator all read them
without knowing the drafter. A question may carry a suggested answer (`suggested_answer`) with
how it was derived (`suggestion_derivation`); the one is present exactly when the other is. A set
of choices, as the orchestrator's own `ChoiceQuestion` has, is added with the first drafter that
sets one, TODO(#529).

**Who does what.** The drafter writes the gaps and the questions. An orchestrator tells the
researcher that a draft has questions and where to answer them, offers to redraft once they have,
and says that the draft came from a mock when it did; it never accepts a suggestion for the
researcher. The app shows the latest version's open questions on the draft's card in the
conversation, three at a time, or more to keep one section's parts together, each as a text box
labelled by the question and described by what it fills and by any suggestion, which the researcher may copy into the box but which never fills
it by itself, and lists every question with its answer, or its suggestion while unanswered, on
the project's documents page ([The app](app.md)). It sends the answers to
`POST /api/projects/{id}/documents/{document_id}/answers`, which records them for the person
signed in and never takes a name from the body. The harness records each answer and fills the
answers into the next `DraftRequest`. No agent writes an answer.

**An answer outlives its version.** The conductor gives a drafter the latest version of the
document it redrafts, so a redraft is that document's next version. A drafter is given the answers
recorded for every document of the kind it drafts, not only the latest version's: a project drafted
before redrafts kept their document may hold two of one kind, and a question's identifier,
derived from its target, finds its answer in whichever draft asked it.

**Model access.** A metadata record and a person's answers are `documentation`-class project
content, so they go to a drafter with a hosted model only where the institutional profile allows
it in its `hosted_models` ([Projects](projects.md), invariant 8). A drafter places answers by rule, so it
can use them without a model.

**Limitations go in the statement.** The core `Document` has no `limitations` slot, so a drafter
says in the outcome's statement what its draft does not do: that it drafted on the template path,
how many gaps it left and how many questions it asked, and, for a mock, that it is one
([Agents](agents.md)).

**The template path stays.** A drafter that calls a model keeps a deterministic path, used when no
model is configured and run by the CI evaluation (TODO(#576)). A version drafted on that path
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
- **A question, not a value.** A model can often guess a field's meaning from its name, but a guess
  is not something the data show. Offered as a question, it saves the researcher typing. Written as
  a value, it would be published unchecked. In the workshop, participants filled 36 empty
  dictionary rows by hand (#445). Questions take that work into the conversation without letting a
  model fill the rows.
- **Answers recorded by the harness.** Only an answer the harness recorded, against the person it
  acted for, can honestly be called `supplied`. A model's reading of a chat reply cannot.
- **Gap identifiers, not headings.** A person may rename or reorder a README's sections. A gap that
  carries its question's identifier still matches its answer, and the app and the evaluation can
  count gaps without parsing prose.

## Rejected alternatives

- **The model deciding which gaps remain.** A model that judged a section fully written could close
  a gap with a guess. The gaps are a rule of the template, and the model writes around them.
- **Abstaining when the metadata record is withheld.** Where the profile does not let the record
  go to a hosted model, the request reaches the drafter without it, and the drafter drafts from
  the inventory alone, as it does for a project with no approved record, and says so. The record's
  sections are then gaps, which is what they would be with no record.

- **A fourth source value, `suggested`.** It would put a model's guess in a data dictionary that is
  published as the researcher's, marked only by a column a reader may never look at.
- **The orchestrator passing answers to the drafter.** A `DraftRequest` slot filled by the
  orchestrator would be simpler and would work with plain chat. But a model's interpretation of the
  researcher's words would then become `supplied`, with only the approval to catch a mistake.
- **Answers only by editing the draft.** Editing still works, and its values become `supplied` on
  regeneration. As the only way, it leaves the researcher to find each gap themselves.
- **A source marker on every README section.** It is more precise than marking only the gaps, but a
  person's edit easily leaves a marker that no longer describes the text under it.
- **Questions in an agent-owned subclass of `Document`.** The conductor records a version only from
  a payload of the core `Document` class, so a subclass would never become a project document.
- **Questions on the `Outcome`.** The outcome is the agent's decision about the run, and a question
  is about the version. The version is where the app and the next regeneration look for it.

## Non-functional requirements

- **Privacy.** A drafter sees the inventory, never the data, and the inventory carries no summary
  values until there is statistical disclosure control (#571). Project content other than the
  inventory reaches a hosted model only as the profile allows.
- **Accessibility.** Questions are answered through the app's form controls, whose accessibility
  is set out in #529.

## Open questions

- Whether a data dictionary should follow CDIF's variable descriptions, and be exported as DDI-CDI:
  TODO(#220).
- Whether the README itself should state how generative AI was used to draft it: TODO(#478).
