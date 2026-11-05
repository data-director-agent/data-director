"""advisor.documentation: the Documentation Editor persona (docs/specs/agents.md). A mock,
and the stub drafter of the project's README and data dictionary (#200).

Serves `setup.documentation` and `preparation.documentation` (R5). Given a `DraftRequest` for a
`readme` or a `data_dictionary`, it drafts a project document (docs/specs/projects.md) from the
project's inventory: the files and the tables' fields are drafted, and what only the researcher
knows, such as the methods, each field's definition, unit and missing value codes, the licence and
the citation, is marked for them. Each value in the data dictionary is marked with where it came
from: inferred from the inventory, supplied by the researcher, or unknown.

The README's sections are those of `readme.yaml`. The mock writes no prose of its own, reads no
file, consults no source and calls no model, so its grounding mode is `none` and it cites only its
input. Regenerating a document drafts it afresh from the project's facts, and names the version it
replaces in `revises`; a regenerated data dictionary keeps the values the researcher gave in that
version. The real editor is TODO(#358).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import NamedTuple

import yaml

from dd_sdk import serve
from dd_sdk.agent import AgentResult, AgentSpec, Derived, RunContext
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
    CurrentVersion,
    Derivation,
    Document,
    DocumentKind,
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
# The project facts a README section may be drafted from (readme.yaml explains each).
SOURCES = frozenset({"files", "tables", "licences"})
# How the draft marks what the researcher writes. A person's edit replaces it.
PLACEHOLDER = "_To be written by the researcher: {ask}_"
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

TITLES = {DocumentKind.README: "README", DocumentKind.DATA_DICTIONARY: "Data dictionary"}
MEDIA_TYPES = {DocumentKind.README: "text/markdown", DocumentKind.DATA_DICTIONARY: "text/csv"}

# What the mock does not do, said in every outcome: its payload is the core Document, which has
# no room for a list of limitations (docs/specs/agents.md).
LIMITATIONS = (
    "This is a mock: it copies the inventory's file and field names and writes no prose of its "
    "own. It does not open the files, infers no definitions, units or missing value codes, and "
    "does not read the reason given for a decision on an earlier version."
)


class Section(NamedTuple):
    heading: str
    ask: str
    source: str | None  # the project fact it is drafted from, or None: the researcher writes it


def load_sections(path: Path = README) -> list[Section]:
    with path.open(encoding="utf-8") as fh:
        table = yaml.safe_load(fh)
    sections = []
    for entry in table:
        source = entry.get("from")
        if source is not None and source not in SOURCES:
            raise ValueError(f"{path}: section {entry['heading']!r} drafts from unknown {source!r}")
        sections.append(Section(str(entry["heading"]), " ".join(str(entry["ask"]).split()), source))
    if not sections:
        raise ValueError(f"{path}: no sections")
    return sections


class DocumentationEditor:
    spec = AgentSpec(
        agent_id="advisor.documentation",
        version="0.1.0a1",
        title="Documentation Editor",
        description=(
            "Mock. Drafts a project's README or data dictionary from its file inventory: the files "
            "and the tables' fields are drafted, and the description, methods, definitions, units, "
            "missing value codes, licence and citation are marked for the researcher to write."
        ),
        action_class="advise",
        accepts=(ClassSchema.of(DraftRequest),),
        grounding_mode=GroundingMode.NONE,
        payload=ClassSchema.of(Document),
        derivations={
            "document_title": Derived(Derivation.TEMPLATE),
            "document_text": Derived(Derivation.TEMPLATE),
        },
        serves=("setup.documentation", "preparation.documentation"),
    )

    def __init__(self, sections: list[Section] | None = None) -> None:
        self.sections = sections if sections is not None else load_sections()

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

        if kind == DocumentKind.README:
            text, statement = self._readme(inventory, asked.requirements)
        else:
            fields = sum(len(f.file_fields) for f in inventory.inventory_files)
            if not fields:
                return _abstain(
                    ReasonCode.INSUFFICIENT_INPUT,
                    "The inventory lists no table with fields, so there is no data dictionary to "
                    "draft.",
                )
            text, counts = _dictionary(inventory, asked.current_version)
            statement = (
                f"Mock: a data dictionary of {fields} fields, each value marked with where it came "
                f"from: {counts[Source.INFERRED]} inferred from the inventory, "
                f"{counts[Source.SUPPLIED]} supplied by you and {counts[Source.UNKNOWN]} unknown, "
                "left for you to fill in."
            )

        current = asked.current_version
        if current is not None:
            statement += f" It replaces version {current.version_ref.version} of the document."
        ref = GroundingRef(source_id=ctx.input_ref, content_hash=ctx.input_hash)
        return AgentResult(
            outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement=f"{statement} {LIMITATIONS}"),
            payload=Document(
                document_kind=kind,
                document_title=(current.document_title if current else None) or TITLES[kind],
                media_type=MEDIA_TYPES[kind],
                document_text=text,
                document_derivation=Derivation.TEMPLATE,
                revises=current.version_ref if current else None,
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
        )

    def _readme(
        self, inventory: FileInventory, requirements: RepositoryRequirements | None
    ) -> tuple[str, str]:
        parts = ["# README"]
        drafted = 0
        for section in self.sections:
            body = _drafted(section.source, inventory, requirements)
            drafted += body is not None
            parts.append(f"## {section.heading}")
            if body is not None:
                parts.append(body)
            parts.append(PLACEHOLDER.format(ask=section.ask))
        statement = (
            f"Mock: a README of {len(self.sections)} sections, {drafted} of them drafted from the "
            "project's inventory and the repository chosen. What each section asks of you is "
            "marked for you to write."
        )
        return "\n\n".join(parts) + "\n", statement


def _drafted(
    source: str | None, inventory: FileInventory, requirements: RepositoryRequirements | None
) -> str | None:
    """A section's text drafted from one project fact, or None if there is nothing to draft."""
    if source == "files":
        rows = [
            (f"`{f.file_path}`", _format(f.file_media_type, f.file_pronom_ids), str(f.file_size))
            for f in inventory.inventory_files
        ]
        return _table(("File", "Format", "Size (bytes)"), rows)
    if source == "tables":
        tables = [
            f"`{f.file_path}`:\n\n"
            + _table(
                ("Field", "Type", "Format"),
                [(f"`{c.name}`", c.field_type or "", c.field_format or "") for c in f.file_fields],
            )
            for f in inventory.inventory_files
            if f.file_fields
        ]
        return "\n\n".join(tables) or None
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


def _dictionary(
    inventory: FileInventory, current: CurrentVersion | None
) -> tuple[str, dict[Source, int]]:
    """The data dictionary as CSV, one row per field, and how many values came from each source.

    A value the researcher gave in the current version wins over the inventory's, so that their
    edits survive regenerating. The rows are the inventory's fields: a field no longer in it is
    dropped.
    """
    earlier = _earlier_rows(current)
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
                value, source = _cell(column, given.get(column) or "", before)
                counts[source] += 1
                row += [value, source.value]
            writer.writerow(row)
    return out.getvalue(), counts


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


def _abstain(reason: ReasonCode, statement: str) -> AgentResult:
    return AgentResult(
        outcome=Outcome(status=OutcomeStatus.ABSTAINED, reason_code=reason, statement=statement)
    )


def build() -> DocumentationEditor:
    return DocumentationEditor()


def main() -> int:
    """The `dd-advisor-documentation` console script: serve over A2A with `dd_sdk.serve`."""
    return serve.main(build)
