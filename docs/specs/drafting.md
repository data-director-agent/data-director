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
from a `DraftRequest`. Today it is a mock that writes no prose and asks nothing
([`agents/advisor-documentation/README.md`](../../agents/advisor-documentation/README.md)). Making
it what this spec describes is TODO(#358). A metadata record drafter follows the same rules when
it is built.

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
   `unknown` cell is empty. A model never writes a cell's value
   (`agents/advisor-documentation/tests/test_documentation_agent.py`). The evaluation checks it
   for a model-backed drafter too (TODO(#576)).
4. **A model writes README prose only from the drafter's input.** That input is the inventory, the
   metadata record and the repository's requirements. What they do not support is a gap and is
   left unwritten: methods, study design, data collection, variable definitions, units, missing
   value codes, and any claim about the data's contents (TODO(#573)).
5. **Every gap is marked and asked.** A README gap is an italic placeholder saying what is needed,
   followed by the HTML comment `<!-- dd:gap <question-id> -->`, which the rendered README does not
   show. A data dictionary gap is an `unknown` cell. Each gap has exactly one question in the
   version's `document_questions` whose target names it
   (`agents/advisor-documentation/tests/test_documentation_agent.py`).
6. **An answer is supplied only when a person recorded it.** A person answers a version's questions
   in the app. Each answer is a project log event that names the person it acted for, as any other
   event does ([Projects](projects.md)). When the document is regenerated, the conductor puts the
   recorded answers into the `DraftRequest`'s `draft_answers`, as it puts in the inventory. The
   drafter places each answer, as given, in its gap or cell and marks it `supplied`, and asks that
   gap no more. A model does not rephrase an answer. An orchestrator may put a question to the
   researcher, but it cannot answer one. The Documentation Editor places answers today. Recording
   them and filling them in are not built yet, TODO(#575, #394); until they are, the conductor
   removes any `draft_answers` a caller sends in a project (`harness/tests/test_project_runs.py`).
7. **A model's suggestion is only ever offered.** A drafter may suggest an answer, for example that
   `age_yrs` is the participant's age in years. The suggestion appears in the question, never in
   the document's text. It becomes `supplied` only when a person confirms or corrects it, by
   recording an answer (TODO(#574)).
8. **A drafter rests on its input alone.** The Documentation Editor's grounding mode is
   `input_only` once it calls a model, whichever way a particular version was drafted. The mock's
   is `none`. The metadata record and the answers reach it in its input, never by retrieval, so it
   cites only its input. `document_derivation` records how each version came about: `model`, or
   `template` when no model is configured or the model's draft was not used. The manifest names it
   as the recorder of `document_text` (`recorded_in`, [Agents](agents.md)).

## Boundaries and contracts

**Questions belong to the version.** A `Document` carries an optional list of questions
(`document_questions`), and the project log keeps them with the version they were asked of
(`harness/docs/projects.md`). A question (`DocumentQuestion`) has an identifier, `q-` and 16
hexadecimal digits, that is stable within the document across regenerations, so it is derived
from what the question fills and never from its position; the Documentation Editor takes the
digits from the SHA-256 of its target. It also has the text put to the person and its target: a
README section (`gap_section`), or a data dictionary cell named by `gap_file`, `gap_field` and
`gap_column`. An answer (`DraftAnswer`) names the question it answers and gives the text. The
classes are in the core contract because the conductor, the app and an orchestrator all read them
without knowing the drafter. A question may later carry a suggested answer, with how it was
derived, and a set of choices, as the orchestrator's own `ChoiceQuestion` does (#529). Those
slots are added with the first drafter that sets them, TODO(#574).

**Who does what.** The drafter writes the gaps and the questions. An orchestrator decides when to
put questions to the researcher, a few at a time, and says that the draft came from a mock when it
did. The app renders a question as form controls (#529). The harness records each answer and fills
the answers into the next `DraftRequest`. No agent writes an answer.

**Model access.** A metadata record and a person's answers are `documentation`-class project
content, so they go to a drafter with a hosted model only where the institutional profile allows
it ([Projects](projects.md), invariant 8, TODO(#394, #40)). A drafter places answers by rule, so it
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
over-discloses and never under-discloses.

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

- Whether a drafter with a hosted model drafts from the inventory alone, or abstains, when the
  profile withholds the metadata record: TODO(#573).
- Whether a data dictionary should follow CDIF's variable descriptions, and be exported as DDI-CDI:
  TODO(#220).
- Whether the README itself should state how generative AI was used to draft it: TODO(#478).
