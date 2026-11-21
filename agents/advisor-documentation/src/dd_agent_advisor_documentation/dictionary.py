"""The data dictionary, drafted by rule (docs/specs/drafting.md): one CSV row for each field of each
table in the inventory, each value followed by where it came from, and a question for each gap.

A column that several files share, by name, type and format, is asked about once, and the answer
fills that column's row in each of those files (#1317): a study whose runs each write the same
`forces.csv` is asked about `Cd` once, not once per run. A column with the same name but another
type or format is a column of its own, asked about on its own. A person who edits one file's row
in a version keeps that value for that file; the other files still take the shared answer.

A field's UCUM unit code is worked out by rule (`dd_units`) from the unit the field is given, so
the researcher, who gave the unit, checks the code rather than writing it. No model writes a cell
(docs/specs/drafting.md, invariant 3). A unit code is asked about once for the files of a shared
column that give the same unit; a file whose unit was edited to another is asked on its own.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from dd_agent_advisor_documentation.values import missing_codes
from dd_sdk.contract.models import (
    CurrentVersion,
    DocumentQuestion,
    DraftAnswer,
    FileInventory,
    TableField,
)
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

    INFERRED = (
        "inferred"  # read from the data by dd-inventory: a type or a format; or worked out by rule
    )
    SUPPLIED = "supplied"  # given by the researcher: in the inventory or an earlier version
    UNKNOWN = "unknown"  # no one has said yet: the cell is empty


# How each inventory value came to be there. dd-inventory infers a field's type and format from
# the table, and writes no description, so a description in the inventory was given by a person.
INVENTORY_SOURCES = {
    "type": Source.INFERRED,
    "format": Source.INFERRED,
    "description": Source.SUPPLIED,
    "missing_values": Source.INFERRED,  # codes the inventory's summary found (values.py)
    "unit_code": Source.INFERRED,  # worked out by rule from the unit (dd_units)
}

# What each data dictionary column asks of the researcher when it is unknown, of the field
# `{field}` in the place `{place}`: one file, or the files that share the column.
CELL_ASKS = {
    "type": "What type of value does `{field}` {place} hold?",
    "format": "In what format are the values of `{field}` {place} written?",
    "description": "What does `{field}` {place} record?",
    "unit": "In what unit is `{field}` {place} measured? Say if it has none.",
    "unit_code": (
        "What is the UCUM code (https://ucum.org) for `{unit}`, the unit of `{field}` {place}?"
    ),
    "missing_values": "Which values of `{field}` {place} mean that a value is missing?",
}
ONE_FILE = "in `{file}`"
SHARED = "in these files"
SHARED_NOTE = " It is a column of {n} files, such as `{file}`, and your answer applies to each."

# A column as the inventory describes it, whichever file it is in: its name, type and format.
type Column = tuple[str, str | None, str | None]


def column_of(table_field: TableField) -> Column:
    return (table_field.name, table_field.field_type, table_field.field_format)


@dataclass
class Gap:
    """One gap a question asks about: a column of the field `name`, in one file or in several
    files that share it, and the files whose cell it leaves unknown, in the inventory's order."""

    name: str
    column: str
    unit: str = ""  # the unit a unit code's question asks about
    files: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Dictionary:
    """A drafted data dictionary: its CSV, its questions, how many values came from each source,
    and the unit codes worked out, named for the statement."""

    text: str
    questions: list[DocumentQuestion]
    counts: dict[Source, int]
    unit_codes: list[str]


def shared_target(column: Column, value: str) -> dict[str, str | None]:
    """The gap a question about a column several files share fills: the column and which of its
    values, never the files, so that adding or leaving out a file keeps the question's
    identifier."""
    name, field_type, field_format = column
    return {
        "field": name,
        "field_type": field_type,
        "field_format": field_format,
        "column": value,
    }


def draft_dictionary(
    inventory: FileInventory, current: CurrentVersion | None, answers: Mapping[str, str]
) -> Dictionary:
    """The data dictionary as CSV, one row per field of each file, a question for each gap it may
    ask, and how many values came from each source.

    A value comes from, in order: an answer to that file's own cell, a value the researcher gave
    in the current version's row, an answer to the column the file shares with others, and the
    inventory or the rule; else it is unknown and asked. So their answers and edits survive
    regenerating, and an edit of one file's row overrides the shared answer for that file. The
    rows are the inventory's fields: a field no longer in it is dropped.
    """
    earlier = _earlier_rows(current)
    files_of: dict[Column, list[str]] = {}
    for f in inventory.inventory_files:
        for c in f.file_fields:
            files = files_of.setdefault(column_of(c), [])
            if f.file_path not in files:
                files.append(f.file_path)
    # Each gap by its question's identifier, in the order first met.
    gaps: dict[str, Gap] = {}
    counts = dict.fromkeys(Source, 0)
    unit_codes: list[str] = []
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(DICTIONARY_COLUMNS)
    for f in inventory.inventory_files:
        for c in f.file_fields:
            shared = len(files_of[column_of(c)]) > 1
            before = earlier.get((f.file_path, c.name), {})
            cells = _cells(f.file_path, c, shared=shared, before=before, answers=answers, gaps=gaps)
            row = [f.file_path, c.name]
            for value, source in cells.values():
                counts[source] += 1
                row += [value, source.value]
            writer.writerow(row)
            code, source = cells["unit_code"]
            if source == Source.INFERRED and code != NOT_APPLICABLE:
                unit_codes.append(_named_code(code, cells["unit"][0], c.name))
    questions = [_question(qid, gap) for qid, gap in gaps.items()]
    return Dictionary(out.getvalue(), questions, counts, unit_codes)


def _cells(
    file: str,
    c: TableField,
    *,
    shared: bool,
    before: Mapping[str, str],
    answers: Mapping[str, str],
    gaps: dict[str, Gap],
) -> dict[str, tuple[str, Source]]:
    """One field's cells, column by column, so that a worked-out cell reads the cell it is worked
    out from. A cell left unknown that is asked joins its gap in `gaps`."""
    given = {
        "type": c.field_type,
        "format": c.field_format,
        "description": c.field_description,
        "missing_values": missing_codes(c),
    }
    cells: dict[str, tuple[str, Source]] = {}
    for column in VALUE_COLUMNS:
        own = question_id({"file": file, "field": c.name, "column": column})
        unit = cells["unit"][0] if "unit" in cells else ""
        target = shared_target(column_of(c), column)
        if column in WORKED_OUT_FROM:
            # A unit code follows its file's unit: files share its question only if they give the
            # same unit.
            target["unit"] = unit
            given[column] = worked_out_unit_code(unit)
        ask = question_id(target) if shared else own
        answer = answers.get(own)
        if answer is not None:
            value, source = answer, Source.SUPPLIED
        else:
            row_before = _edited_code(before) if column == "unit_code" else before
            value, source = _cell(column, given.get(column) or "", row_before)
            if source == Source.UNKNOWN and ask in answers:
                value, source = answers[ask], Source.SUPPLIED
        cells[column] = (value, source)
        states = {k + SOURCE_SUFFIX: v[1] for k, v in cells.items()}
        if source == Source.UNKNOWN and asks_about(column, states):
            gap = gaps.setdefault(ask, Gap(c.name, column, unit))
            if file not in gap.files:
                gap.files.append(file)
    return cells


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
    itself still unknown. `row` holds the source column of each cell met so far."""
    source_column = WORKED_OUT_FROM.get(column)
    return source_column is None or row.get(source_column + SOURCE_SUFFIX) != Source.UNKNOWN


def _question(question_id: str, gap: Gap) -> DocumentQuestion:
    """The one question for a gap: one file's cell, or a shared column's cells in each file."""
    first, many = gap.files[0], len(gap.files) > 1
    prompt = CELL_ASKS[gap.column].format(
        field=gap.name, unit=gap.unit, place=SHARED if many else ONE_FILE.format(file=first)
    )
    if many:
        prompt += SHARED_NOTE.format(n=len(gap.files), file=first)
    return DocumentQuestion(
        question_id=question_id,
        question_prompt=prompt,
        gap_file=first,
        gap_field=gap.name,
        gap_column=gap.column,
        gap_files=list(gap.files) if many else None,
    )


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


def question_id(target: Mapping[str, str | None]) -> str:
    """A question's identifier, derived from the gap it targets and never from its position, so
    that the same gap has the same identifier in every version (docs/specs/drafting.md)."""
    canonical = json.dumps(target, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"q-{digest[:QUESTION_ID_DIGITS]}"


_question_id = question_id


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


def _answers(given: Sequence[DraftAnswer]) -> dict[str, str]:
    """The recorded answers by the question they answer. A blank answer leaves its gap open; of
    two answers to one question, the later in the list wins."""
    return {a.answered_question: a.answer_text for a in given if a.answer_text.strip()}
