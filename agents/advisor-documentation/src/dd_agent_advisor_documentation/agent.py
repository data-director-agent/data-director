"""advisor.documentation: the Documentation Editor persona (docs/specs/agents.md), the drafter
of the project's README and data dictionary (docs/specs/drafting.md).

Serves `preparation.documentation` (R5), not `setup.documentation` (no inventory yet, #1017).
Given a `DraftRequest` for a `readme` or a `data_dictionary`, it drafts a project document
(docs/specs/projects.md) from the project's inventory: the files and the tables' fields are
drafted, and what only the researcher knows, such as the methods and each field's definition,
unit and missing value codes, is marked for them. Each value in the data dictionary is marked
with where it came from: inferred from the inventory, supplied by the researcher, or unknown.

When a model is configured, which it is by default (`factory.py`), it may suggest an answer to a
data dictionary's questions about a field's definition or unit, and to the questions of the README
sections `readme.yaml` marks `suggest` (`prose.py`, `suggest`). The suggestion is offered with the
question (`suggested_answer`) and never placed in the document: the draft is made by rule before
the model is asked, and a suggestion becomes `supplied` only when the researcher records it, or a
correction of it, as their answer (docs/specs/drafting.md, invariant 7). Only for suggestions is
the model also given the documents the researcher attached (`project_documents`, `with_documents`),
and only then is it asked about the README's Methods (`suggest: documents`, `sections.py`).

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

Every gap is asked (docs/specs/drafting.md): the version carries one `DocumentQuestion` for each
README section, or part of one asked part by part, left for the researcher, and each `unknown` data
dictionary cell, or each column several files share by name, type and format (`dictionary.py`).
A README gap is an italic placeholder followed by `<!-- dd:gap <question-id> -->`.
A question's identifier is derived from its gap, so the same gap is asked under the same identifier
in every version. An answer in the request's `draft_answers` goes, as given, in its gap, `supplied`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from dd_agent_advisor_documentation.counts import counted
from dd_agent_advisor_documentation.dictionary import (
    Source,
    _answers,
    _question_id,
    dictionary,
)
from dd_agent_advisor_documentation.prose import (
    Ask,
    Prose,
    Suggestions,
    TemplateWriter,
    Writer,
    count,
    how_suggested,
    with_documents,
)
from dd_agent_advisor_documentation.record import (
    _collected,
    _creators,
    _from_record,
    _record,
    _record_general,
    _title,
    _values,
)
from dd_agent_advisor_documentation.sections import Section, load_sections
from dd_agent_advisor_documentation.values import field_facts
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
    FileInventory,
    GroundingMode,
    InvocationRequest,
    Outcome,
    OutcomeStatus,
    ReasonCode,
    RepositoryRequirements,
)
from dd_sdk.model import Usage

# How far a version has got (`document_stage`): a note that asks first, or the document itself.
type Stage = Literal["questions", "draft"]
# The key under which a writer is given the approved metadata record's values.
RECORD_FACTS = "approved_metadata_record"
# The keys under which the README's writer is given the researcher's answers, by section heading,
# and the project's decisions, once the researcher has answered a section.
RESEARCHER_ANSWERS = "researcher_answers"
PROJECT_DECISIONS = "project_decisions"
# How the draft marks what the researcher writes. A person's edit replaces it.
PLACEHOLDER = "_Still needed: {ask}_"
# What follows a placeholder: the question that asks for it. Not shown in the rendered README.
GAP_MARKER = "<!-- dd:gap {question_id} -->"
TITLES = {DocumentKind.README: "README", DocumentKind.DATA_DICTIONARY: "Data dictionary"}
MEDIA_TYPES = {DocumentKind.README: "text/markdown", DocumentKind.DATA_DICTIONARY: "text/csv"}

# What the editor does not do, said in every outcome: its payload is the core Document, which has
# no room for a list of limitations (docs/specs/drafting.md).
LIMITATIONS = (
    "It does not open the files, so it says nothing about their contents beyond what the "
    "inventory records. It infers no definitions, units or missing value codes, and does not "
    "read an earlier README or the reason given for a decision on an earlier version."
)


class DocumentationEditor:
    spec = AgentSpec(
        agent_id="advisor.documentation",
        version="0.7.0a1",
        title="Documentation Editor",
        icon="✍️",
        description=(
            "Drafts a project's README or data dictionary from its file inventory and its approved "
            "metadata record: the files, the tables' fields and the record's title, creators, "
            "dates of collection, location, funding, abstract and licence are drafted, with prose "
            "written by a model where one is configured, and the methods, definitions, units and "
            "missing value codes are marked and asked of the researcher, with a model's suggested "
            "answer offered beside a question, never written into the document."
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
        serves=("preparation.documentation",),
        reads_attached="to suggest answers to a draft's questions, for you to confirm or correct",
    )

    def __init__(self, sections: list[Section] | None = None, writer: Writer | None = None) -> None:
        self.sections = sections if sections is not None else load_sections()
        self.writer: Writer = writer if writer is not None else TemplateWriter()

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        asked = request.input
        assert isinstance(asked, DraftRequest)  # the conductor checked spec.accepts
        kind = asked.document_kind
        if kind not in TITLES:
            return abstain(
                ReasonCode.OUTSIDE_AGENT_SCOPE,
                "The Documentation Editor drafts a README or a data dictionary, not a "
                f"{kind.value}.",
            )
        inventory = asked.inventory
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
            suggestable = {
                s.heading: s.ask
                for s in self.sections
                if s.suggestable(has_documents=bool(asked.project_documents))
            }
            questions, suggested = self._suggest(
                with_documents(_facts(inventory, asked.requirements, record), asked),
                [
                    Ask(q.question_id, section=q.gap_section, asks=suggestable[q.gap_section])
                    for q in questions
                    if q.gap_section in suggestable and q.gap_part is None
                ],
                questions,
                ctx,
            )
            statement += f" {how_suggested(suggested, TITLES[kind])}"
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
            text, questions, counts = dictionary(
                inventory, asked.current_version, _answers(asked.draft_answers)
            )
            record, _ = _record(asked.metadata_record)
            questions, suggested = self._suggest(
                with_documents(_facts(inventory, None, record), asked),
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
                f"from the inventory, {counts[Source.SUPPLIED]} supplied by you and "
                f"{counts[Source.UNKNOWN]} unknown. It asks "
                f"{count(len(questions), 'question')}, one for each unknown value, or for each "
                "column several files share. "
                f"{how_suggested(suggested, TITLES[kind])}"
            )

        current = asked.current_version
        if current is not None:
            statement += f" It replaces version {current.version_ref.version} of the document."
        ref = input_ref(ctx)
        # A README's model may write prose and suggest answers: two calls, recorded together.
        logs = [log for log in (prose.calls, suggested.calls) if log is not None]
        usage = _sum(prose.usage, suggested.usage)
        return AgentResult(
            outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement=f"{statement} {LIMITATIONS}"),
            payload=Document(
                document_kind=kind,
                document_title=(current.document_title if current else None) or TITLES[kind],
                media_type=MEDIA_TYPES[kind],
                document_text=text,
                document_derivation=Derivation.MODEL if prose.written else Derivation.TEMPLATE,
                document_stage=stage,
                revises=current.version_ref if current else None,
                document_questions=questions,
                grounded_on=[ref],
            ),
            evidence=[input_evidence(ctx)],
            model_id=prose.model_id or suggested.model_id,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            model_calls=tuple(c for log in logs for c in log.calls),
            prompts={k: v for log in logs for k, v in log.prompts.items()},
        )

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

    def _readme(
        self, asked: DraftRequest, record: Mapping[str, Any] | None, ctx: RunContext
    ) -> tuple[str, list[DocumentQuestion], str, Prose, Stage]:
        """The README, or, before it is first written, the note that asks what it needs."""
        inventory, requirements = asked.inventory, asked.requirements
        assert inventory is not None  # run checked it
        answers = _answers(asked.draft_answers)
        drafted_from = [
            {
                source: body
                for source in section.sources
                if (body := _drafted(source, inventory, requirements, record)) is not None
            }
            for section in self.sections
        ]
        outline = [
            _outline(section, bodies, record, answers)
            for section, bodies in zip(self.sections, drafted_from, strict=True)
        ]
        questions = [q for planned in outline for q in planned.questions]
        title = (_title(record) if record is not None else None) or "README"
        answered = sum(bool(p.answer or p.answered_parts) for p in outline)
        if asked.current_version is None and questions and not answered:
            # Ask first: no README is shown until the researcher has had the chance to answer.
            note = _questions_note(title, outline, inventory, record, asked)
            statement = (
                f"It asks {count(len(questions), 'question')} before it writes the README, about "
                f"{_listed([p.section.heading for p in outline if p.questions])}. Once they are "
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
            + f". {_how_written(prose)} It leaves {count(len(questions), 'gap')} for you to "
            "fill, each marked and asked as a question."
        )
        return "\n\n".join(parts) + "\n", questions, statement, prose, "draft"


@dataclass(frozen=True)
class Outlined:
    """One README section as the rules draft it, before any prose: its bodies from the facts,
    the researcher's answer to it as a whole, its part lines and gap, and the questions asked."""

    section: Section
    bodies: Mapping[str, str]
    answer: str | None = None
    lines: tuple[str, ...] = ()
    questions: tuple[DocumentQuestion, ...] = ()
    answered_parts: int = 0
    complete: bool = False


def _outline(
    section: Section,
    bodies: Mapping[str, str],
    record: Mapping[str, Any] | None,
    answers: Mapping[str, str],
) -> Outlined:
    """A section's gaps and questions, decided by rule (docs/specs/drafting.md, invariant 5)."""
    question_id = _question_id({"section": section.heading})
    answer = answers.get(question_id)
    if answer is not None:
        return Outlined(section, bodies, answer=answer)
    if section.parts:
        # Each part is its own gap and question. An answer to the section as a whole, recorded
        # before it was asked part by part, is placed above and asks nothing.
        given = _record_general(record)
        lines: list[str] = []
        questions: list[DocumentQuestion] = []
        answered = 0
        for part in section.parts:
            if part.given_by and given[part.given_by]:
                continue
            part_id = _question_id({"section": section.heading, "part": part.label})
            part_answer = answers.get(part_id)
            if part_answer is not None:
                lines.append(f"- **{part.label}:** {part_answer}")
                answered += 1
                continue
            marker = GAP_MARKER.format(question_id=part_id)
            lines.append(f"- **{part.label}:** {PLACEHOLDER.format(ask=part.ask)}\n{marker}")
            questions.append(
                DocumentQuestion(
                    question_id=part_id,
                    question_prompt=f"{part.label}: {part.ask}",
                    gap_section=section.heading,
                    gap_part=part.label,
                )
            )
        return Outlined(section, bodies, None, tuple(lines), tuple(questions), answered)
    if section.complete_from in bodies:
        return Outlined(section, bodies, complete=True)
    marker = GAP_MARKER.format(question_id=question_id)
    question = DocumentQuestion(
        question_id=question_id,
        question_prompt=f"For the README's {section.heading} section: {section.ask}",
        gap_section=section.heading,
    )
    return Outlined(
        section,
        bodies,
        lines=(f"{PLACEHOLDER.format(ask=section.ask)}\n{marker}",),
        questions=(question,),
    )


def _questions_note(
    title: str,
    outline: Sequence[Outlined],
    inventory: FileInventory,
    record: Mapping[str, Any] | None,
    asked: DraftRequest,
) -> str:
    """What a `questions` version says in place of the README: what is asked, and what the README
    will be written from. It has no gaps: its questions are on the version."""
    tables = sum(1 for f in inventory.inventory_files if f.file_fields)
    known = [count(len(inventory.inventory_files), "file")]
    if tables:
        known.append(count(tables, "table"))
    if record is not None:
        known.append("the approved metadata record")
    if asked.project_documents:
        known.append(f"{count(len(asked.project_documents), 'document')} you attached")
    asking = _listed([p.section.heading for p in outline if p.questions])
    return (
        f"# {title}\n\n"
        "_This is not the README yet._ Before writing it, the Documentation Editor needs what only "
        f"you can say about {asking}. Answer the questions below, then ask for the README to be "
        f"drafted: it will be written from your answers and from {_listed(known)}. Anything you "
        "leave unanswered is marked in the README as still needed.\n"
    )


def _listed(items: Sequence[str]) -> str:
    """`items` as an English list: "a", "a and b", "a, b and c"."""
    if len(items) < 2:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _prose_facts(
    inventory: FileInventory,
    requirements: RepositoryRequirements | None,
    record: Mapping[str, Any] | None,
    asked: DraftRequest,
    outline: Sequence[Outlined],
) -> dict[str, Any]:
    """What the writer is told for the README's prose: the facts, and, when the researcher has
    answered a section, their answers by heading, the project's decisions and the documents they
    attached, so that the section can be written from them (docs/specs/drafting.md, invariant 4).
    """
    facts = _facts(inventory, requirements, record)
    given = {p.section.heading: p.answer for p in outline if p.answer is not None}
    if not given:
        return facts
    facts[RESEARCHER_ANSWERS] = given
    if asked.project_decisions:
        facts[PROJECT_DECISIONS] = [
            d.model_dump(mode="json", exclude_none=True) for d in asked.project_decisions
        ]
    return with_documents(facts, asked)


def _how_written(prose: Prose) -> str:
    """What the statement says about the README's prose: who wrote it, and what was not used."""
    if prose.model_id is None:
        return "It was drafted on the template path: no model is configured, so it has no prose."
    if prose.unused:
        return (
            f"It was drafted on the template path, with no prose, because {prose.unused} "
            f"({prose.model_id})."
        )
    said = (
        f"A model ({prose.model_id}) wrote {count(prose.written, 'paragraph')} of prose from "
        "those facts alone"
        if prose.written
        else f"A model ({prose.model_id}) was asked for prose but its draft added none"
    )
    if prose.dropped:
        said += (
            f"; {count(len(prose.dropped), 'paragraph')} it wrote "
            f"{'was' if len(prose.dropped) == 1 else 'were'} not used ("
            + "; ".join(prose.dropped)
            + ")"
        )
    return said + ". Check the prose before you approve it."


def _sum(*usages: Usage) -> Usage:
    """The tokens of several calls: unknown only if no call reports them."""

    def total(counts: list[int | None]) -> int | None:
        known = [n for n in counts if n is not None]
        return sum(known) if known else None

    return Usage(total([u.input_tokens for u in usages]), total([u.output_tokens for u in usages]))


def _facts(
    inventory: FileInventory,
    requirements: RepositoryRequirements | None,
    record: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """What a writer is told: the facts the README is drafted from, and nothing else. A field's
    description is left out: a definition is the researcher's to give (docs/specs/drafting.md)."""
    files = [
        {
            "path": f.file_path,
            "format": _format(f.file_media_type, f.file_pronom_ids),
            "size_bytes": f.file_size,
            **({"fields": [field_facts(c) for c in f.file_fields]} if f.file_fields else {}),
        }
        for f in inventory.inventory_files
    ]
    facts: dict[str, Any] = {
        **counted(inventory),
        "files": files,
    }
    if record is not None:
        year = record.get("publicationYear")
        given = {
            "title": _title(record),
            "creators": _creators(record),
            "funders": _values(record, "fundingReferences", "funderName"),
            "dates_collected": _collected(record),
            "geographic_locations": _values(record, "geoLocations", "geoLocationPlace"),
            "abstract": _from_record("record_abstract", record),
            "licence": _from_record("record_rights", record),
            "publication_year": str(year) if isinstance(year, int | str) and str(year) else None,
        }
        facts[RECORD_FACTS] = {k: v for k, v in given.items() if v}
    if requirements is not None and requirements.licences:
        facts["repository"] = {
            "name": requirements.repository_name,
            "licences_offered": list(requirements.licences),
        }
    return facts


def _drafted(
    source: str,
    inventory: FileInventory,
    requirements: RepositoryRequirements | None,
    record: Mapping[str, Any] | None,
) -> str | None:
    """A section's text drafted from one project fact, or None if there is nothing to draft."""
    if source.startswith("record_"):
        return _from_record(source, record) if record is not None else None
    if source == "files":
        rows = [
            (f"`{f.file_path}`", _format(f.file_media_type, f.file_pronom_ids), str(f.file_size))
            for f in inventory.inventory_files
        ]
        return _table(("File", "Format", "Size (bytes)"), rows)
    if source == "licences":
        if requirements is None or not requirements.licences:
            return None
        offered = ", ".join(f"`{licence}`" for licence in requirements.licences)
        return f"{requirements.repository_name} offers these licences: {offered}."
    return None


def _format(media_type: str | None, pronom_ids: list[str]) -> str:
    known = media_type or "unknown"
    return f"{known} ({', '.join(pronom_ids)})" if pronom_ids else known


def _table(header: tuple[str, ...], rows: Sequence[tuple[str, ...]]) -> str:
    def line(cells: tuple[str, ...]) -> str:
        return "| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |"

    return "\n".join([line(header), line(tuple("---" for _ in header)), *map(line, rows)])


def build() -> DocumentationEditor:
    """The editor on the template path. `factory.build` assembles it from its configuration."""
    return DocumentationEditor()
