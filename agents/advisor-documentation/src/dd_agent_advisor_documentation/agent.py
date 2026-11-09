"""advisor.documentation: the Documentation Editor persona (docs/specs/agents.md), the drafter
of the project's README and data dictionary (docs/specs/drafting.md).

Serves `setup.documentation` and `preparation.documentation` (R5). Given a `DraftRequest` for a
`readme` or a `data_dictionary`, it drafts a project document (docs/specs/projects.md) from the
project's inventory: the files and the tables' fields are drafted, and what only the researcher
knows, such as the methods and each field's definition, unit and missing value codes, is marked
for them. Each value in the data dictionary is marked with where it came from: inferred from the
inventory, supplied by the researcher, or unknown.

When a model is configured, it may suggest an answer to a data dictionary's questions about a
field's definition or unit (`prose.py`, `suggest`). The suggestion is offered with the question
(`suggested_answer`) and never placed in a cell: the dictionary is drafted by rule before the model
is asked, and a suggestion becomes `supplied` only when the researcher records it, or a correction
of it, as their answer (docs/specs/drafting.md, invariant 7).

A README also takes, as given, the title, creators, funding, abstract and licence of the
project's approved metadata record, when the request carries one in DataCite's JSON form, and
cites the dataset by its creators and title. These are supplied content: a person approved them
(docs/specs/drafting.md, invariant 2).

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
README section left for the researcher and each `unknown` data dictionary cell. A README gap is an
italic placeholder followed by `<!-- dd:gap <question-id> -->`. A question's identifier is derived
from its gap, so the same gap is asked under the same identifier in every version. An answer in
the request's `draft_answers` is placed, as given, in the gap it answers and marked `supplied`.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, NamedTuple

import yaml

from dd_agent_advisor_documentation.prose import (
    Ask,
    Prose,
    Suggestions,
    TemplateWriter,
    Writer,
)
from dd_sdk.agent import AgentResult, AgentSpec, Derived, RunContext
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
    ApprovedMetadataRecord,
    CurrentVersion,
    Derivation,
    Document,
    DocumentKind,
    DocumentQuestion,
    DraftAnswer,
    DraftRequest,
    EvidenceItem,
    FileInventory,
    GroundingMode,
    GroundingRef,
    InvocationRequest,
    Outcome,
    OutcomeStatus,
    ReasonCode,
    RepositoryRequirements,
)
from dd_sdk.evidence import HASH_ALGORITHM, INPUT_CANONICALISATION

README = Path(__file__).with_name("readme.yaml")
# The key under which a writer is given the approved metadata record's values.
RECORD_FACTS = "approved_metadata_record"
# The project facts a README section may be drafted from (readme.yaml explains each).
SOURCES = frozenset(
    {
        "files",
        "licences",
        "record_general",
        "record_abstract",
        "record_rights",
        "record_citation",
    }
)
# The metadata record's schema the editor reads: DataCite's, in the JSON form of its REST API's
# attributes, as advisor.metadata drafts it.
DATACITE = "http://datacite.org/schema/kernel-4"
# How the draft marks what the researcher writes. A person's edit replaces it.
PLACEHOLDER = "_To be written by the researcher: {ask}_"
# What follows a placeholder: the question that asks for it. Not shown in the rendered README.
GAP_MARKER = "<!-- dd:gap {question_id} -->"
# How many hexadecimal digits of the gap's SHA-256 a question identifier keeps.
QUESTION_ID_DIGITS = 16
# The data dictionary's columns: a row is keyed by its file and field, and each value is followed
# by a column saying where it came from (Source).
KEY_COLUMNS = ("file", "field")
VALUE_COLUMNS = ("type", "format", "description", "unit", "missing_values")
SOURCE_SUFFIX = "_source"
DICTIONARY_COLUMNS = KEY_COLUMNS + tuple(
    column for value in VALUE_COLUMNS for column in (value, value + SOURCE_SUFFIX)
)


class Source(StrEnum):
    """Where a value in the data dictionary came from, so that a person can check it."""

    INFERRED = "inferred"  # read from the data by dd-inventory: a type or a format
    SUPPLIED = "supplied"  # given by the researcher: in the inventory or an earlier version
    UNKNOWN = "unknown"  # no one has said yet: the cell is empty


# How each inventory value came to be there. dd-inventory infers a field's type and format from
# the table, and writes no description, so a description in the inventory was given by a person.
INVENTORY_SOURCES = {
    "type": Source.INFERRED,
    "format": Source.INFERRED,
    "description": Source.SUPPLIED,
}

# What each data dictionary column asks of the researcher when it is unknown.
CELL_ASKS = {
    "type": "What type of value does `{field}` in `{file}` hold?",
    "format": "In what format are the values of `{field}` in `{file}` written?",
    "description": "What does `{field}` in `{file}` record?",
    "unit": "In what unit is `{field}` in `{file}` measured? Say if it has none.",
    "missing_values": "Which values of `{field}` in `{file}` mean that a value is missing?",
}

TITLES = {DocumentKind.README: "README", DocumentKind.DATA_DICTIONARY: "Data dictionary"}
MEDIA_TYPES = {DocumentKind.README: "text/markdown", DocumentKind.DATA_DICTIONARY: "text/csv"}

# What the editor does not do, said in every outcome: its payload is the core Document, which has
# no room for a list of limitations (docs/specs/drafting.md).
LIMITATIONS = (
    "It does not open the files, so it says nothing about their contents beyond what the "
    "inventory records. It infers no definitions, units or missing value codes, and does not "
    "read an earlier README or the reason given for a decision on an earlier version."
)


class Section(NamedTuple):
    heading: str
    ask: str
    # The project facts it is drafted from, in order; empty: the researcher writes it all.
    sources: tuple[str, ...] = ()
    # The fact that, when it gives anything, says all the section asks, so no gap is left.
    complete_from: str | None = None


def load_sections(path: Path = README) -> list[Section]:
    with path.open(encoding="utf-8") as fh:
        table = yaml.safe_load(fh)
    sections = []
    for entry in table:
        given = entry.get("from")
        sources = (given,) if isinstance(given, str) else tuple(given or ())
        complete_from = entry.get("complete_from")
        for source in sources:
            if source not in SOURCES:
                raise ValueError(
                    f"{path}: section {entry['heading']!r} drafts from unknown {source!r}"
                )
        if complete_from is not None and complete_from not in sources:
            raise ValueError(
                f"{path}: section {entry['heading']!r} is completed from {complete_from!r}, "
                "which it is not drafted from"
            )
        sections.append(
            Section(
                str(entry["heading"]),
                " ".join(str(entry["ask"]).split()),
                sources,
                complete_from,
            )
        )
    if not sections:
        raise ValueError(f"{path}: no sections")
    return sections


class DocumentationEditor:
    spec = AgentSpec(
        agent_id="advisor.documentation",
        version="0.3.0a1",
        title="Documentation Editor",
        description=(
            "Drafts a project's README or data dictionary from its file inventory and its "
            "approved metadata record: the files, the tables' fields and the record's title, "
            "creators, abstract and licence are drafted, with prose written by a model where one "
            "is configured, and the methods, definitions, units and missing value codes are "
            "marked and asked of the researcher, with a model's suggested definition or unit "
            "offered beside a question, never written into the document."
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
        serves=("setup.documentation", "preparation.documentation"),
    )

    def __init__(self, sections: list[Section] | None = None, writer: Writer | None = None) -> None:
        self.sections = sections if sections is not None else load_sections()
        self.writer: Writer = writer if writer is not None else TemplateWriter()

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        asked = request.input
        assert isinstance(asked, DraftRequest)  # the conductor checked spec.accepts
        kind = asked.document_kind
        if kind not in TITLES:
            return _abstain(
                ReasonCode.OUTSIDE_AGENT_SCOPE,
                "The Documentation Editor drafts a README or a data dictionary, not a "
                f"{kind.value}.",
            )
        inventory = asked.inventory
        if inventory is None or not inventory.inventory_files:
            return _abstain(
                ReasonCode.INSUFFICIENT_INPUT,
                "Add the project's file inventory first: the draft is made from it.",
            )

        answers = _answers(asked.draft_answers)
        prose = Prose()
        suggested = Suggestions()
        if kind == DocumentKind.README:
            record, unread = _record(asked.metadata_record)
            text, questions, statement, prose = self._readme(
                inventory, asked.requirements, record, answers, ctx
            )
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
                return _abstain(
                    ReasonCode.INSUFFICIENT_INPUT,
                    "The inventory lists no table with fields, so there is no data dictionary to "
                    "draft.",
                )
            # The dictionary is drafted by rule first, so nothing the model says can reach a cell.
            text, questions, counts = _dictionary(inventory, asked.current_version, answers)
            record, _ = _record(asked.metadata_record)
            questions, suggested = self._suggest(inventory, record, questions, ctx)
            statement = (
                f"A data dictionary of {fields} fields, drafted by rule (a model fills no cell), "
                f"each value marked with where it came from: {counts[Source.INFERRED]} inferred "
                f"from the inventory, {counts[Source.SUPPLIED]} supplied by you and "
                f"{counts[Source.UNKNOWN]} unknown. It asks "
                f"{_count(len(questions), 'question')}, one for each unknown value. "
                f"{_how_suggested(suggested)}"
            )

        current = asked.current_version
        if current is not None:
            statement += f" It replaces version {current.version_ref.version} of the document."
        ref = GroundingRef(source_id=ctx.input_ref, content_hash=ctx.input_hash)
        # A README's model writes prose and a data dictionary's suggests answers: one, not both.
        calls = prose.calls or suggested.calls
        usage = prose.usage if prose.calls else suggested.usage
        return AgentResult(
            outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement=f"{statement} {LIMITATIONS}"),
            payload=Document(
                document_kind=kind,
                document_title=(current.document_title if current else None) or TITLES[kind],
                media_type=MEDIA_TYPES[kind],
                document_text=text,
                document_derivation=Derivation.MODEL if prose.written else Derivation.TEMPLATE,
                revises=current.version_ref if current else None,
                document_questions=questions,
                grounded_on=[ref],
            ),
            evidence=[
                EvidenceItem(
                    source_id=ctx.input_ref,
                    retrieved_at=datetime.now(UTC),
                    hash_algorithm=HASH_ALGORITHM,
                    canonicalisation=INPUT_CANONICALISATION,
                    content_hash=ctx.input_hash,
                )
            ],
            model_id=prose.model_id or suggested.model_id,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            model_calls=calls.calls if calls else (),
            prompts=calls.prompts if calls else {},
        )

    def _suggest(
        self,
        inventory: FileInventory,
        record: Mapping[str, Any] | None,
        questions: list[DocumentQuestion],
        ctx: RunContext,
    ) -> tuple[list[DocumentQuestion], Suggestions]:
        """The questions, each with the writer's suggested answer where it made one. The writer is
        given the facts a README is drafted from, never the answers, a field's description or an
        earlier version (docs/specs/drafting.md)."""
        asks = [
            Ask(q.question_id, q.gap_file, q.gap_field, q.gap_column)
            for q in questions
            if q.gap_file is not None and q.gap_field is not None and q.gap_column is not None
        ]
        suggested = self.writer.suggest(_facts(inventory, None, record), asks, ctx)
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
        self,
        inventory: FileInventory,
        requirements: RepositoryRequirements | None,
        record: Mapping[str, Any] | None,
        answers: Mapping[str, str],
        ctx: RunContext,
    ) -> tuple[str, list[DocumentQuestion], str, Prose]:
        drafted_from = [
            {
                source: body
                for source in section.sources
                if (body := _drafted(source, inventory, requirements, record)) is not None
            }
            for section in self.sections
        ]
        # The writer may write about a section only if it has facts to draft from, and is given
        # only those facts: never the answers, nor an earlier version (docs/specs/drafting.md).
        prose = self.writer.write(
            _facts(inventory, requirements, record),
            [s.heading for s, bodies in zip(self.sections, drafted_from, strict=True) if bodies],
            ctx,
        )
        title = _title(record) if record is not None else None
        parts = [f"# {title or 'README'}"]
        if prose.overview:
            parts.append(prose.overview)
        questions: list[DocumentQuestion] = []
        drafted = answered = complete = 0
        for section, bodies in zip(self.sections, drafted_from, strict=True):
            drafted += bool(bodies)
            parts.append(f"## {section.heading}")
            if bodies and (paragraph := prose.sections.get(section.heading)):
                parts.append(paragraph)
            parts.extend(bodies.values())
            question_id = _question_id({"section": section.heading})
            answer = answers.get(question_id)
            if answer is not None:
                parts.append(answer)
                answered += 1
                continue
            if section.complete_from in bodies:
                complete += 1
                continue
            placeholder = PLACEHOLDER.format(ask=section.ask)
            parts.append(f"{placeholder}\n{GAP_MARKER.format(question_id=question_id)}")
            questions.append(
                DocumentQuestion(
                    question_id=question_id,
                    question_prompt=f"For the README's {section.heading} section: {section.ask}",
                    gap_section=section.heading,
                )
            )
        statement = (
            f"A README of {len(self.sections)} sections, {drafted} of them drafted from the "
            f"project's facts ({complete} in full), and {answered} written from your answers. "
            f"{_how_written(prose)} It leaves {_count(len(questions), 'gap')} for you to write, "
            "each marked and asked as a question."
        )
        return "\n\n".join(parts) + "\n", questions, statement, prose


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
        f"A model ({prose.model_id}) wrote {_count(prose.written, 'paragraph')} of prose from "
        "those facts alone"
        if prose.written
        else f"A model ({prose.model_id}) was asked for prose but its draft added none"
    )
    if prose.dropped:
        said += (
            f"; {_count(len(prose.dropped), 'paragraph')} it wrote "
            f"{'was' if len(prose.dropped) == 1 else 'were'} not used ("
            + "; ".join(prose.dropped)
            + ")"
        )
    return said + ". Check the prose before you approve it."


def _how_suggested(suggested: Suggestions) -> str:
    """What the statement says about the suggested answers."""
    if suggested.model_id is None:
        return "No model is configured, so it suggests no answers."
    if suggested.unused:
        return f"It suggests no answers, because {suggested.unused} ({suggested.model_id})."
    n = len(suggested.answers)
    said = (
        f"A model ({suggested.model_id}) suggested an answer to "
        f"{_count(n, 'question')}, offered beside the question and not written into the "
        "dictionary: a suggestion becomes yours only when you save it, or a correction of it, as "
        "your answer"
        if n
        else f"A model ({suggested.model_id}) was asked to suggest answers but offered none"
    )
    if suggested.dropped:
        said += (
            f"; {_count(len(suggested.dropped), 'suggestion')} it made "
            f"{'was' if len(suggested.dropped) == 1 else 'were'} not offered ("
            + "; ".join(suggested.dropped)
            + ")"
        )
    return said + "."


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
            **(
                {
                    "fields": [
                        {
                            k: v
                            for k, v in (
                                ("name", c.name),
                                ("type", c.field_type),
                                ("format", c.field_format),
                            )
                            if v
                        }
                        for c in f.file_fields
                    ]
                }
                if f.file_fields
                else {}
            ),
        }
        for f in inventory.inventory_files
    ]
    facts: dict[str, Any] = {
        "file_count": len(files),
        "total_size_bytes": sum(f.file_size for f in inventory.inventory_files),
        "table_count": sum(1 for f in inventory.inventory_files if f.file_fields),
        "files": files,
    }
    if record is not None:
        year = record.get("publicationYear")
        given = {
            "title": _title(record),
            "creators": _creators(record),
            "funders": _values(record, "fundingReferences", "funderName"),
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


def _record(given: ApprovedMetadataRecord | None) -> tuple[dict[str, Any] | None, str | None]:
    """The approved metadata record's properties, or None and, if there was a record, why it was
    not read."""
    if given is None:
        return None, None
    unread = "The approved metadata record was not used: "
    if given.conforms_to != DATACITE:
        return None, unread + f"the editor reads only DataCite records ({DATACITE})."
    try:
        properties = json.loads(given.document_text)
    except json.JSONDecodeError:
        return None, unread + "its text is not JSON."
    if not isinstance(properties, dict):
        return None, unread + "its text is not a JSON object of DataCite properties."
    return properties, None


def _values(record: Mapping[str, Any], prop: str, key: str) -> list[str]:
    """Each non-empty `key` of the entries of a DataCite property whose value is a list of
    objects. A placeholder the metadata mock left (null, or blank) is not a value."""
    entries = record.get(prop)
    if not isinstance(entries, list):
        return []
    return [
        value.strip()
        for entry in entries
        if isinstance(entry, dict) and isinstance(value := entry.get(key), str) and value.strip()
    ]


def _title(record: Mapping[str, Any]) -> str | None:
    """The record's main title: its first title with no `titleType`, else its first title."""
    entries = record.get("titles")
    if not isinstance(entries, list):
        return None
    main = [e for e in entries if isinstance(e, dict) and not e.get("titleType")]
    titles = _values({"titles": main}, "titles", "title") or _values(record, "titles", "title")
    return titles[0] if titles else None


def _creators(record: Mapping[str, Any]) -> list[str]:
    """Each creator's name, or else their family and given names, as the record writes them."""
    entries = record.get("creators")
    if not isinstance(entries, list):
        return []
    names = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
            continue
        parts = [entry.get("familyName"), entry.get("givenName")]
        given = [p.strip() for p in parts if isinstance(p, str) and p.strip()]
        if given:
            names.append(", ".join(given))
    return names


def _from_record(source: str, record: Mapping[str, Any]) -> str | None:
    """A section's text from the approved metadata record, its values placed as given."""
    title = _title(record)
    creators = _creators(record)
    if source == "record_general":
        lines = [
            (label, value)
            for label, value in (
                ("Title", title),
                ("Creators", "; ".join(creators)),
                ("Funding", "; ".join(_values(record, "fundingReferences", "funderName"))),
            )
            if value
        ]
        return "\n".join(f"- **{label}:** {value}" for label, value in lines) or None
    if source == "record_abstract":
        entries = record.get("descriptions")
        abstracts = [
            e
            for e in entries or []
            if isinstance(e, dict) and e.get("descriptionType") == "Abstract"
        ]
        found = _values({"descriptions": abstracts}, "descriptions", "description")
        return found[0] if found else None
    if source == "record_rights":
        entries = record.get("rightsList")
        rights = []
        for entry in entries if isinstance(entries, list) else []:
            if not isinstance(entry, dict):
                continue
            name, uri = entry.get("rights"), entry.get("rightsUri") or entry.get("rightsURI")
            name = name.strip() if isinstance(name, str) else ""
            uri = uri.strip() if isinstance(uri, str) else ""
            if name or uri:
                rights.append(f"{name} (<{uri}>)" if name and uri else name or f"<{uri}>")
        return ("Licence: " + "; ".join(rights) + ".") if rights else None
    if source == "record_citation":
        if not (creators and title):
            return None
        year = record.get("publicationYear")
        when = f" ({year})" if isinstance(year, int | str) and str(year).strip() else ""
        return f"{_closed('; '.join(creators) + when)} {_closed(title)}"
    return None


def _closed(text: str) -> str:
    """`text` ending with a full stop, unless it already ends a sentence."""
    return text if text.endswith((".", "?", "!")) else text + "."


def _format(media_type: str | None, pronom_ids: list[str]) -> str:
    known = media_type or "unknown"
    return f"{known} ({', '.join(pronom_ids)})" if pronom_ids else known


def _table(header: tuple[str, ...], rows: Sequence[tuple[str, ...]]) -> str:
    def line(cells: tuple[str, ...]) -> str:
        return "| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |"

    return "\n".join([line(header), line(tuple("---" for _ in header)), *map(line, rows)])


def _dictionary(
    inventory: FileInventory, current: CurrentVersion | None, answers: Mapping[str, str]
) -> tuple[str, list[DocumentQuestion], dict[Source, int]]:
    """The data dictionary as CSV, one row per field, a question for each unknown value, and how
    many values came from each source.

    An answer the researcher recorded wins, then a value they gave in the current version, then the
    inventory's, so that their answers and edits survive regenerating. The rows are the
    inventory's fields: a field no longer in it is dropped.
    """
    earlier = _earlier_rows(current)
    questions: list[DocumentQuestion] = []
    counts = dict.fromkeys(Source, 0)
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(DICTIONARY_COLUMNS)
    for f in inventory.inventory_files:
        for c in f.file_fields:
            given = {
                "type": c.field_type,
                "format": c.field_format,
                "description": c.field_description,
            }
            before = earlier.get((f.file_path, c.name), {})
            row = [f.file_path, c.name]
            for column in VALUE_COLUMNS:
                question_id = _question_id({"file": f.file_path, "field": c.name, "column": column})
                answer = answers.get(question_id)
                if answer is not None:
                    value, source = answer, Source.SUPPLIED
                else:
                    value, source = _cell(column, given.get(column) or "", before)
                if source == Source.UNKNOWN:
                    questions.append(
                        DocumentQuestion(
                            question_id=question_id,
                            question_prompt=CELL_ASKS[column].format(
                                field=c.name, file=f.file_path
                            ),
                            gap_file=f.file_path,
                            gap_field=c.name,
                            gap_column=column,
                        )
                    )
                counts[source] += 1
                row += [value, source.value]
            writer.writerow(row)
    return out.getvalue(), questions, counts


def _cell(column: str, given: str, before: Mapping[str, str]) -> tuple[str, Source]:
    """One value and its source: the researcher's earlier value, else the inventory's.

    An earlier value that differs from the inventory's is taken as the researcher's, whatever the
    earlier source column says: a person correcting a type in a spreadsheet seldom changes its
    source too. The earlier source columns are therefore not read.
    """
    earlier = (before.get(column) or "").strip()
    if earlier and earlier != given:
        return earlier, Source.SUPPLIED
    if given:
        return given, INVENTORY_SOURCES.get(column, Source.SUPPLIED)
    return "", Source.UNKNOWN


def _earlier_rows(current: CurrentVersion | None) -> dict[tuple[str, str], dict[str, str]]:
    """The current version's rows by (file, field), if it is a CSV data dictionary."""
    if current is None or current.media_type != "text/csv" or not current.document_text:
        return {}
    reader = csv.DictReader(io.StringIO(current.document_text))
    if not reader.fieldnames or not set(KEY_COLUMNS) <= set(reader.fieldnames):
        return {}
    return {(row["file"], row["field"]): row for row in reader}


def _question_id(target: Mapping[str, str]) -> str:
    """A question's identifier, derived from the gap it targets and never from its position, so
    that the same gap has the same identifier in every version (docs/specs/drafting.md)."""
    canonical = json.dumps(target, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"q-{digest[:QUESTION_ID_DIGITS]}"


def _answers(given: Sequence[DraftAnswer]) -> dict[str, str]:
    """The recorded answers by the question they answer. A blank answer leaves its gap open; of
    two answers to one question, the later in the list wins."""
    return {a.answered_question: a.answer_text for a in given if a.answer_text.strip()}


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def _abstain(reason: ReasonCode, statement: str) -> AgentResult:
    return AgentResult(
        outcome=Outcome(status=OutcomeStatus.ABSTAINED, reason_code=reason, statement=statement)
    )


def build() -> DocumentationEditor:
    """The editor on the template path. `factory.build` assembles it from its configuration."""
    return DocumentationEditor()
