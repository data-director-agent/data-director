"""advisor.documentation: the Documentation Editor persona (docs/specs/agents.md), the drafter
of the project's README and data dictionary (docs/specs/drafting.md).

Serves `preparation.documentation` (R5), not `setup.documentation` (no inventory yet, #1017).
Given a `DraftRequest` for a `readme` or a `data_dictionary`, it drafts a project document
(docs/specs/projects.md) from the project's inventory: the files and the tables' fields are
drafted, and what only the researcher knows, such as the methods and each field's definition,
unit and missing value codes, is marked for them. Each value in the data dictionary is marked
with where it came from: inferred from the inventory or worked out by rule (a unit's UCUM code,
`dictionary.py`), supplied by the researcher, or unknown.

When a model is configured, which it is by default (`factory.py`), it may suggest an answer to a
data dictionary's questions about a field's definition or unit, and to the questions of the README
sections `readme.yaml` marks `suggest` (`suggestions.py`, `suggest`). The suggestion is offered
with the question (`suggested_answer`) and never placed in the document: the draft is made by rule
before the model is asked, and a suggestion becomes `supplied` only when the researcher records
it, or a correction of it, as their answer (docs/specs/drafting.md, invariant 7). Only for
suggestions is the model also given the documents the researcher attached (`project_documents`,
`with_documents`), and only then is it asked about the README's Methods (`suggest: documents`,
`sections.py`).

A README also takes, as given, the title, creators, dates of data collection, geographic
location, funding, abstract and licence of the project's approved metadata record, when the
request carries one in DataCite's JSON form, and cites the dataset by its creators and title.
These are supplied content: a person approved them (docs/specs/drafting.md, invariant 2).

The README's sections are those of `readme.yaml`. When a model is configured (`factory.py`), a
writer (`prose.py`) adds a short paragraph of prose to the sections that have facts to draft from,
and an overview under the title, written only from those facts; what it writes is checked, and a
paragraph that names what the facts do not give is not used. The gaps, the tables and the values
from the metadata record are drafted by rule either way, so a model never closes a gap, fills a
data dictionary cell or rephrases an answer. The editor reads no file and consults no source, so
its grounding mode is `input_only` and it cites only its input. `document_derivation` records
`model` when the version has prose a model wrote, and `template` otherwise.

Regenerating a document drafts it afresh from the project's facts, and names the version it
replaces in `revises`; a regenerated data dictionary keeps the values the researcher gave in that
version.

Asked to revise (`DraftRequest.revise`), it changes a README's prose as a person asked, in their
words (`revise.py`): the one time a writer is given an earlier version. Headings, tables, gaps and
the values a person gave are kept byte for byte, and without a model it revises nothing.

Every gap is asked (docs/specs/drafting.md): the version carries one `DocumentQuestion` for each
README section, or part of one asked part by part, left for the researcher, and each `unknown` data
dictionary cell, or each column several files share by name, type and format (`dictionary.py`).
A README gap is an italic placeholder followed by `<!-- dd:gap <question-id> -->`.
A question's identifier is derived from its gap, so the same gap is asked under the same identifier
in every version. An answer in the request's `draft_answers` goes, as given, in its gap, `supplied`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal, NamedTuple

from dd_agent_advisor_documentation.checks import count, listed, summed
from dd_agent_advisor_documentation.dictionary import (
    Source,
    _answers,
    draft_dictionary,
    unit_codes_statement,
)
from dd_agent_advisor_documentation.drafted import drafted
from dd_agent_advisor_documentation.notes import how_written, questions_note
from dd_agent_advisor_documentation.outline import Outlined, outlined
from dd_agent_advisor_documentation.plan import LIMITATIONS as PLAN_LIMITATIONS
from dd_agent_advisor_documentation.plan import draft_plan, load_plan_sections
from dd_agent_advisor_documentation.prose import Prose, TemplateWriter, Writer
from dd_agent_advisor_documentation.readme_facts import RESEARCHER_ANSWERS as RESEARCHER_ANSWERS
from dd_agent_advisor_documentation.readme_facts import _facts, _prose_facts
from dd_agent_advisor_documentation.record import (
    _record,
    _title,
)
from dd_agent_advisor_documentation.revise import gaps
from dd_agent_advisor_documentation.revised import (
    REVISION_LIMITATIONS,
    given_values,
    revisable,
    revised_statement,
    unrevised,
)
from dd_agent_advisor_documentation.sections import Section, load_sections
from dd_agent_advisor_documentation.suggestions import (
    Ask,
    Suggestions,
    how_suggested,
    section_asks,
    with_decisions,
    with_definitions,
    with_documents,
)
from dd_sdk import shared_answers
from dd_sdk.agent import (
    AgentResult,
    AgentSpec,
    Derived,
    RunContext,
    abstain,
    input_evidence,
    input_ref,
)
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
    Derivation,
    Document,
    DocumentKind,
    DocumentQuestion,
    DraftRequest,
    GroundingMode,
    InvocationRequest,
    Outcome,
    OutcomeStatus,
    ReasonCode,
)

# How far a version has got (`document_stage`): a note that asks first, or the document itself.
type Stage = Literal["questions", "draft"]


class Drafted(NamedTuple):
    """A version as drafted, before it becomes the editor's result."""

    text: str
    questions: list[DocumentQuestion]
    statement: str
    stage: Stage
    prose: Prose
    suggested: Suggestions


TITLES = {
    DocumentKind.README: "README",
    DocumentKind.DATA_DICTIONARY: "Data dictionary",
    DocumentKind.DMP: "Data Management Plan",
}
MEDIA_TYPES = {
    DocumentKind.README: "text/markdown",
    DocumentKind.DATA_DICTIONARY: "text/csv",
    DocumentKind.DMP: "text/markdown",
}

# What the editor does not do, said in every outcome: its payload is the core Document, which has
# no room for a list of limitations (docs/specs/drafting.md).
LIMITATIONS = (
    "It does not open the files, so it says nothing about their contents beyond what the "
    "inventory records. It infers no definitions, units or missing value codes, and does not "
    "read an earlier README or the reason given for a decision on an earlier version. A UCUM "
    "unit code is worked out by rule only from a unit you gave."
)


class DocumentationEditor:
    spec = AgentSpec(
        agent_id="advisor.documentation",
        version="0.9.0a1",
        title="Documentation Editor",
        icon="✍️",
        description=(
            "Drafts a project's README or data dictionary from its file inventory and its approved "
            "metadata record, and, in alpha, a Data Management Plan to Science Europe's core "
            "requirements from what people in the project decided: what the facts give is drafted, "
            "with README prose written by a model where one is configured, and what only the "
            "researcher knows is marked and asked of them, with a model's suggested answer offered "
            "beside a question, never written into the document. With a model, it also revises a "
            "README's prose as you ask, keeping every gap and every value you gave."
        ),
        action_class="advise",
        accepts=(ClassSchema.of(DraftRequest),),
        grounding_mode=GroundingMode.INPUT_ONLY,
        payload=ClassSchema.of(Document),
        derivations={
            "document_title": Derived(Derivation.TEMPLATE),
            "document_text": Derived(Derivation.MODEL, recorded_in="document_derivation"),
            "document_questions": Derived(Derivation.TEMPLATE),
            "document_questions.suggested_answer": Derived(
                Derivation.MODEL, recorded_in="suggestion_derivation"
            ),
        },
        serves=("preparation.documentation", "setup.dmp-create"),
        reads_attached=(
            "to suggest answers to a draft's or a Data Management Plan's questions, for you to "
            "confirm or correct"
        ),
    )

    def __init__(self, sections: list[Section] | None = None, writer: Writer | None = None) -> None:
        self.sections = sections if sections is not None else load_sections()
        self.writer: Writer = writer if writer is not None else TemplateWriter()
        self.plan_sections = load_plan_sections()

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        asked = request.input
        assert isinstance(asked, DraftRequest)  # the conductor checked spec.accepts
        kind = asked.document_kind
        if kind not in TITLES:
            return abstain(
                ReasonCode.OUTSIDE_AGENT_SCOPE,
                "The Documentation Editor drafts a README, a data dictionary or a Data "
                f"Management Plan, not a {kind.value}.",
            )
        inventory = asked.inventory
        if asked.revise:
            return self._revise(asked, ctx)
        if kind == DocumentKind.DMP:
            return self._result(asked, self._plan(asked, ctx), ctx)
        if inventory is None or not inventory.inventory_files:
            return abstain(
                ReasonCode.INSUFFICIENT_INPUT,
                "Add the project's file inventory first: the draft is made from it.",
            )

        prose = Prose()
        stage: Stage = "draft"
        suggested = Suggestions()
        if kind == DocumentKind.README:
            record, unread = _record(asked.metadata_record)
            text, questions, statement, prose, stage = self._readme(asked, record, ctx)
            # The README is drafted first, so nothing the model suggests can reach its text.
            questions, suggested, offered = self._offer(asked, record, questions, ctx)
            statement += offered
            if asked.metadata_record is None:
                statement += (
                    " It was given no approved metadata record, so it drafts from the inventory "
                    "alone."
                )
            else:
                version = asked.metadata_record.version_ref.version
                statement += (
                    f" {unread}"
                    if unread
                    else f" It takes what it can from version {version} of the approved metadata "
                    "record."
                )
        else:
            fields = sum(len(f.file_fields) for f in inventory.inventory_files)
            if not fields:
                return abstain(
                    ReasonCode.INSUFFICIENT_INPUT,
                    "The inventory lists no table with fields, so there is no data dictionary to "
                    "draft.",
                )
            # The dictionary is drafted by rule first, so nothing the model says can reach a cell.
            drafted = draft_dictionary(
                inventory, asked.current_version, _answers(asked.draft_answers)
            )
            text, questions, counts = drafted.text, drafted.questions, drafted.counts
            record, _ = _record(asked.metadata_record)
            questions, suggested = self._suggest(
                with_definitions(
                    with_decisions(with_documents(_facts(inventory, None, record), asked), asked),
                    text,
                ),
                [
                    Ask(q.question_id, q.gap_file, q.gap_field, q.gap_column)
                    for q in questions
                    if q.gap_file is not None
                    and q.gap_field is not None
                    and q.gap_column is not None
                ],
                questions,
                ctx,
            )
            statement = (
                f"A data dictionary of {fields} fields, drafted by rule (a model fills no cell), "
                f"each value marked with where it came from: {counts[Source.INFERRED]} inferred "
                f"from the inventory or worked out by rule, {counts[Source.SUPPLIED]} supplied by "
                f"you and {counts[Source.UNKNOWN]} unknown. It asks "
                f"{count(len(questions), 'question')}, one for each unknown value it can ask "
                "about yet, or for each column several files share. "
                f"{unit_codes_statement(drafted.unit_codes)} "
                f"{how_suggested(suggested, TITLES[kind])}"
            )

        made = Drafted(text, questions, statement, stage, prose, suggested)
        return self._result(asked, made, ctx)

    def _result(self, asked: DraftRequest, drafted: Drafted, ctx: RunContext) -> AgentResult:
        """The version drafted, as the editor's result."""
        kind, current, prose, suggested = (
            asked.document_kind,
            asked.current_version,
            drafted.prose,
            drafted.suggested,
        )
        statement = drafted.statement
        if current is not None:
            statement += f" It replaces version {current.version_ref.version} of the document."
        limitations = (
            PLAN_LIMITATIONS
            if kind == DocumentKind.DMP
            else REVISION_LIMITATIONS
            if asked.revise
            else LIMITATIONS
        )
        # A README's model may write prose and suggest answers: two calls, recorded together.
        logs = [log for log in (prose.calls, suggested.calls) if log is not None]
        usage = summed(prose.usage, suggested.usage)
        return AgentResult(
            outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement=f"{statement} {limitations}"),
            payload=Document(
                document_kind=kind,
                document_title=(current.document_title if current else None) or TITLES[kind],
                media_type=MEDIA_TYPES[kind],
                document_text=drafted.text,
                document_derivation=Derivation.MODEL if prose.written else Derivation.TEMPLATE,
                document_stage=drafted.stage,
                revises=current.version_ref if current else None,
                document_questions=drafted.questions,
                grounded_on=[input_ref(ctx)],
            ),
            evidence=[input_evidence(ctx)],
            model_id=prose.model_id or suggested.model_id,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            model_calls=tuple(c for log in logs for c in log.calls),
            prompts={k: v for log in logs for k, v in log.prompts.items()},
        )

    def _plan(self, asked: DraftRequest, ctx: RunContext) -> Drafted:
        """A Data Management Plan, or the note that asks first (`plan.py`)."""
        record, _ = _record(asked.metadata_record)
        text, questions, statement, suggested, asks_first = draft_plan(
            self.plan_sections,
            asked,
            record,
            lambda facts, asks, questions: self._suggest(facts, asks, questions, ctx),
        )
        stage: Stage = "questions" if asks_first else "draft"
        return Drafted(text, questions, statement, stage, Prose(), suggested)

    def _suggest(
        self,
        facts: Mapping[str, Any],
        asks: Sequence[Ask],
        questions: list[DocumentQuestion],
        ctx: RunContext,
    ) -> tuple[list[DocumentQuestion], Suggestions]:
        """The questions, each with the writer's suggested answer where it made one. The writer is
        given the facts the draft is made from and the documents the researcher attached, never
        the answers, a field's description or an earlier version (docs/specs/drafting.md)."""
        suggested = self.writer.suggest(facts, asks, ctx)
        return [
            q.model_copy(
                update={
                    "suggested_answer": suggestion,
                    "suggestion_derivation": Derivation.MODEL,
                }
            )
            if (suggestion := suggested.answers.get(q.question_id))
            else q
            for q in questions
        ], suggested

    def _outline(self, asked: DraftRequest, record: Mapping[str, Any] | None) -> list[Outlined]:
        """The README's sections as the rules draft them, with their gaps and questions."""
        answers = _answers(asked.draft_answers)
        return [
            outlined(
                section,
                {
                    source: body
                    for source in section.sources
                    if (body := drafted(source, asked, record)) is not None
                },
                record,
                answers,
            )
            for section in self.sections
        ]

    def _offer(
        self,
        asked: DraftRequest,
        record: Mapping[str, Any] | None,
        questions: list[DocumentQuestion],
        ctx: RunContext,
    ) -> tuple[list[DocumentQuestion], Suggestions, str]:
        """A README's questions with a person's own words offered first, from another document or
        a decision, then a model's suggestions, and what the statement says of them."""
        assert asked.inventory is not None  # run checked it
        questions = shared_answers.offer(questions, asked.shared_answers, asked.project_decisions)
        questions, suggested = self._suggest(
            with_documents(_facts(asked.inventory, asked.requirements, record), asked),
            section_asks(self.sections, questions, has_documents=bool(asked.project_documents)),
            questions,
            ctx,
        )
        said = f" {how_suggested(suggested, TITLES[DocumentKind.README])}"
        return questions, suggested, said + shared_answers.how_offered(questions)

    def _revise(self, asked: DraftRequest, ctx: RunContext) -> AgentResult:
        """The current README revised as a person asked (`revise.py`), with the questions of
        the gaps it still marks; or an abstention that says why not."""
        current, inventory = asked.current_version, asked.inventory
        why = revisable(asked)
        if why is not None:
            return abstain(*why)
        assert current is not None and current.revision_request is not None
        assert inventory is not None
        record, _ = _record(asked.metadata_record)
        outline = self._outline(asked, record)
        revision = self.writer.revise(
            _facts(inventory, asked.requirements, record),
            current.document_text,
            current.revision_request,
            given_values(asked, outline),
            ctx,
        )
        if revision is None:
            return abstain(
                ReasonCode.CAPABILITY_NOT_IMPLEMENTED,
                "Revising the README as you ask needs a model, and none is configured here. "
                "Edit the README yourself instead.",
            )
        if revision.text == current.document_text:
            return abstain(ReasonCode.INSUFFICIENT_INPUT, unrevised(revision))
        marked = set(gaps(revision.text))
        questions = [q for p in outline for q in p.questions if q.question_id in marked]
        questions, suggested, offered = self._offer(asked, record, questions, ctx)
        prose = Prose(
            sections=dict.fromkeys(revision.changed, ""),
            dropped=revision.dropped,
            model_id=revision.model_id,
            usage=revision.usage,
            calls=revision.calls,
        )
        statement = revised_statement(revision, len(marked), len(questions)) + offered
        return self._result(
            asked, Drafted(revision.text, questions, statement, "draft", prose, suggested), ctx
        )

    def _readme(
        self, asked: DraftRequest, record: Mapping[str, Any] | None, ctx: RunContext
    ) -> tuple[str, list[DocumentQuestion], str, Prose, Stage]:
        """The README, or, before it is first written, the note that asks what it needs."""
        inventory, requirements = asked.inventory, asked.requirements
        assert inventory is not None  # run checked it
        outline = self._outline(asked, record)
        questions = [q for planned in outline for q in planned.questions]
        title = (_title(record) if record is not None else None) or "README"
        answered = sum(bool(p.answer or p.answered_parts) for p in outline)
        if asked.current_version is None and questions and not answered:
            # Ask first: no README is shown until the researcher has had the chance to answer.
            note = questions_note(title, outline, inventory, record, asked)
            statement = (
                f"It asks {count(len(questions), 'question')} before it writes the README, about "
                f"{listed([p.section.heading for p in outline if p.questions])}. Once they are "
                "answered, drafting the README again writes it from the answers. This version "
                "is a note, not the README, and cannot be approved."
            )
            return note, questions, statement, Prose(), "questions"

        # The writer may write about a section that has facts to draft from or an answer to write
        # from, and is given only those: never an earlier version (docs/specs/drafting.md).
        offered = [p.section.heading for p in outline if p.bodies or p.answer]
        prose = self.writer.write(
            _prose_facts(inventory, requirements, record, asked, outline), offered, ctx
        )
        parts = [f"# {title}"]
        if prose.overview:
            parts.append(prose.overview)
        complete = rewritten = 0
        for planned in outline:
            parts.append(f"## {planned.section.heading}")
            paragraph = prose.sections.get(planned.section.heading)
            if paragraph:
                parts.append(paragraph)
            parts.extend(planned.bodies.values())
            if planned.answer is not None:
                # A model's paragraph written from the answer takes its place; else the answer
                # is placed as given.
                rewritten += bool(paragraph)
                if not paragraph:
                    parts.append(planned.answer)
                continue
            parts.extend(planned.lines)
            complete += planned.complete
        statement = (
            f"A README of {len(self.sections)} sections, "
            f"{sum(bool(p.bodies) for p in outline)} of them drafted from the project's facts "
            f"({complete} in full), and {answered} written from your answers"
            + (f" ({rewritten} of them in a model's words)" if rewritten else "")
            + f". {how_written(prose)} It leaves {count(len(questions), 'gap')} for you to "
            "fill, each marked and asked as a question."
        )
        return "\n\n".join(parts) + "\n", questions, statement, prose, "draft"


def build() -> DocumentationEditor:
    """The editor on the template path. `factory.build` assembles it from its configuration."""
    return DocumentationEditor()
