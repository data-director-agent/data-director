"""The data dictionary, drafted by rule (docs/specs/drafting.md, invariant 3).

One CSV row per field of each table in the inventory, keyed by its file and field. Each value is
followed by a column saying where it came from (`Source`), and each value no one has given yet is
asked as a question. A model never writes a cell: it may only suggest an answer to a question,
which the agent adds after the dictionary is drafted.

A field's UCUM unit code is worked out by rule (`dd_units`) from the unit the field is given, so
the researcher, who gave the unit, checks the code rather than writing it.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from dd_sdk.contract.models import CurrentVersion, DocumentQuestion, FileInventory, TableField
from dd_units import means_no_unit, ucum_code

# How many hexadecimal digits of the gap's SHA-256 a question identifier keeps.
QUESTION_ID_DIGITS = 16
# The data dictionary's columns: a row is keyed by its file and field, and each value is followed
# by a column saying where it came from (Source).
KEY_COLUMNS = ("file", "field")
VALUE_COLUMNS = ("type", "format", "description", "unit", "unit_code", "missing_values")
SOURCE_SUFFIX = "_source"
DICTIONARY_COLUMNS = KEY_COLUMNS + tuple(
    column for value in VALUE_COLUMNS for column in (value, value + SOURCE_SUFFIX)
)
# A column worked out from another: it is not asked while the other is unknown, because it will
# be worked out once that is given.
WORKED_OUT_FROM = {"unit_code": "unit"}
# The unit code of a field whose unit is given as none.
NOT_APPLICABLE = "n/a"
# How many of the unit codes worked out the statement names, for the researcher to check.
CODES_NAMED = 5


class Source(StrEnum):
    """Where a value in the data dictionary came from, so that a person can check it."""

    INFERRED = "inferred"  # read from the inventory (a type or a format), or worked out by rule
    SUPPLIED = "supplied"  # given by the researcher: in the inventory or an earlier version
    UNKNOWN = "unknown"  # no one has said yet: the cell is empty


# How each value the rule starts from came to be there. dd-inventory infers a field's type and
# format from the table, and writes no description, so a description in the inventory was given by
# a person. A unit code is worked out by rule from the field's unit.
INVENTORY_SOURCES = {
    "type": Source.INFERRED,
    "format": Source.INFERRED,
    "description": Source.SUPPLIED,
    "unit_code": Source.INFERRED,
}

# What each data dictionary column asks of the researcher when it is unknown.
CELL_ASKS = {
    "type": "What type of value does `{field}` in `{file}` hold?",
    "format": "In what format are the values of `{field}` in `{file}` written?",
    "description": "What does `{field}` in `{file}` record?",
    "unit": "In what unit is `{field}` in `{file}` measured? Say if it has none.",
    "unit_code": (
        "What is the UCUM code (https://ucum.org) for `{unit}`, the unit of `{field}` in `{file}`?"
    ),
    "missing_values": "Which values of `{field}` in `{file}` mean that a value is missing?",
}


@dataclass(frozen=True)
class Dictionary:
    """A drafted data dictionary: its CSV, its questions, how many values came from each source,
    and the unit codes worked out, named for the statement."""

    text: str
    questions: list[DocumentQuestion]
    counts: dict[Source, int]
    unit_codes: list[str]


@dataclass(frozen=True)
class _Cell:
    value: str
    source: Source
    question: DocumentQuestion | None


def draft_dictionary(
    inventory: FileInventory, current: CurrentVersion | None, answers: Mapping[str, str]
) -> Dictionary:
    """The data dictionary as CSV, one row per field, a question for each unknown value it may
    ask, and how many values came from each source.

    An answer the researcher recorded wins, then a value they gave in the current version, then the
    rule's, so that their answers and edits survive regenerating. The rows are the inventory's
    fields: a field no longer in it is dropped.
    """
    earlier = _earlier_rows(current)
    questions: list[DocumentQuestion] = []
    counts = dict.fromkeys(Source, 0)
    unit_codes: list[str] = []
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(DICTIONARY_COLUMNS)
    for f in inventory.inventory_files:
        for c in f.file_fields:
            cells = _row(f.file_path, c, earlier.get((f.file_path, c.name), {}), answers)
            row = [f.file_path, c.name]
            for cell in cells.values():
                row += [cell.value, cell.source.value]
                counts[cell.source] += 1
                if cell.question is not None:
                    questions.append(cell.question)
            writer.writerow(row)
            code = cells["unit_code"]
            if code.source == Source.INFERRED and code.value != NOT_APPLICABLE:
                unit_codes.append(_named_code(code.value, cells["unit"].value, c.name))
    return Dictionary(out.getvalue(), questions, counts, unit_codes)


def worked_out_unit_code(unit: str) -> str:
    """The unit code the rule gives a unit: its UCUM code, `n/a` for a field with no unit, or ""
    when the rule cannot tell."""
    if not unit.strip():
        return ""
    if means_no_unit(unit):
        return NOT_APPLICABLE
    found = ucum_code(unit)
    return found.code if found is not None else ""


def asks_about(column: str, row: Mapping[str, str]) -> bool:
    """Whether an unknown cell is asked: always, except a cell worked out from another that is
    itself still unknown."""
    source_column = WORKED_OUT_FROM.get(column)
    return source_column is None or row.get(source_column + SOURCE_SUFFIX) != Source.UNKNOWN


def question_id(target: Mapping[str, str]) -> str:
    """A question's identifier, derived from the gap it targets and never from its position, so
    that the same gap has the same identifier in every version (docs/specs/drafting.md)."""
    canonical = json.dumps(target, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"q-{digest[:QUESTION_ID_DIGITS]}"


def _row(
    file: str, field: TableField, before: Mapping[str, str], answers: Mapping[str, str]
) -> dict[str, _Cell]:
    """One field's cells, column by column, so that a worked-out cell reads the cell it is worked
    out from, wherever that value came from."""
    given = {
        "type": field.field_type or "",
        "format": field.field_format or "",
        "description": field.field_description or "",
    }
    cells: dict[str, _Cell] = {}
    for column in VALUE_COLUMNS:
        earlier = before
        if column == "unit_code":
            given[column] = worked_out_unit_code(cells["unit"].value)
            earlier = _edited_code(before)
        target = {"file": file, "field": field.name, "column": column}
        answer = answers.get(question_id(target))
        if answer is not None:
            value, source = answer, Source.SUPPLIED
        else:
            value, source = _cell(column, given.get(column, ""), earlier)
        state = {k + SOURCE_SUFFIX: v.source for k, v in cells.items()}
        asked = source == Source.UNKNOWN and asks_about(column, state)
        cells[column] = _Cell(value, source, _question(target, cells) if asked else None)
    return cells


def _question(target: Mapping[str, str], cells: Mapping[str, _Cell]) -> DocumentQuestion:
    unit = cells["unit"].value if "unit" in cells else ""
    column = target["column"]
    return DocumentQuestion(
        question_id=question_id(target),
        question_prompt=CELL_ASKS[column].format(
            field=target["field"], file=target["file"], unit=unit
        ),
        gap_file=target["file"],
        gap_field=target["field"],
        gap_column=column,
    )


def _cell(column: str, given: str, before: Mapping[str, str]) -> tuple[str, Source]:
    """One value and its source: the researcher's earlier value, else the rule's.

    An earlier value that differs from the rule's is taken as the researcher's, whatever the
    earlier source column says: a person correcting a type in a spreadsheet seldom changes its
    source too. The earlier source columns are therefore not read.
    """
    earlier = (before.get(column) or "").strip()
    if earlier and earlier != given:
        return earlier, Source.SUPPLIED
    if given:
        return given, INVENTORY_SOURCES.get(column, Source.SUPPLIED)
    return "", Source.UNKNOWN


def _edited_code(before: Mapping[str, str]) -> Mapping[str, str]:
    """The earlier row, with its unit code only if a person edited it. A code the rule worked out
    from the earlier unit was not edited, so a changed unit gives a fresh code, not the old one."""
    code = (before.get("unit_code") or "").strip()
    if code and code == worked_out_unit_code(before.get("unit") or ""):
        return {k: v for k, v in before.items() if k != "unit_code"}
    return before


def _named_code(code: str, unit: str, field: str) -> str:
    found = ucum_code(unit)
    name = f" ({found.name})" if found is not None and found.name else ""
    return f"`{code}`{name} for `{field}`"


def _earlier_rows(current: CurrentVersion | None) -> dict[tuple[str, str], dict[str, str]]:
    """The current version's rows by (file, field), if it is a CSV data dictionary."""
    if current is None or current.media_type != "text/csv" or not current.document_text:
        return {}
    reader = csv.DictReader(io.StringIO(current.document_text))
    if not reader.fieldnames or not set(KEY_COLUMNS) <= set(reader.fieldnames):
        return {}
    return {(row["file"], row["field"]): row for row in reader}


def unit_codes_statement(unit_codes: Sequence[str]) -> str:
    """What the outcome's statement says about the unit codes it worked out, for checking."""
    if not unit_codes:
        return ""
    named = "; ".join(unit_codes[:CODES_NAMED])
    more = len(unit_codes) - CODES_NAMED
    rest = f"; and {more} more" if more > 0 else ""
    noun = "code" if len(unit_codes) == 1 else "codes"
    return (
        f"It worked out {len(unit_codes)} UCUM unit {noun} by rule from the units you gave, "
        f"for you to check: {named}{rest}."
    )
