"""The data dictionary, drafted by rule (docs/specs/drafting.md): one CSV row for each field of each
table in the inventory, each value followed by where it came from, and a question for each gap.

A column that several files share, by name, type and format, is asked about once, and the answer
fills that column's row in each of those files (#1317): a study whose runs each write the same
`forces.csv` is asked about `Cd` once, not once per run. A column with the same name but another
type or format is a column of its own, asked about on its own. A person who edits one file's row
in a version keeps that value for that file; the other files still take the shared answer.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from dd_sdk.contract.models import (
    CurrentVersion,
    DocumentQuestion,
    DraftAnswer,
    FileInventory,
    TableField,
)

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

# What each data dictionary column asks of the researcher when it is unknown, of the field
# `{field}` in the place `{place}`: one file, or the files that share the column.
CELL_ASKS = {
    "type": "What type of value does `{field}` {place} hold?",
    "format": "In what format are the values of `{field}` {place} written?",
    "description": "What does `{field}` {place} record?",
    "unit": "In what unit is `{field}` {place} measured? Say if it has none.",
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
    files: list[str] = field(default_factory=list)


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


def dictionary(
    inventory: FileInventory, current: CurrentVersion | None, answers: Mapping[str, str]
) -> tuple[str, list[DocumentQuestion], dict[Source, int]]:
    """The data dictionary as CSV, one row per field of each file, a question for each gap, and
    how many values came from each source.

    A value comes from, in order: an answer to that file's own cell, a value the researcher gave
    in the current version's row, an answer to the column the file shares with others, and the
    inventory; else it is unknown and asked. So their answers and edits survive regenerating, and
    an edit of one file's row overrides the shared answer for that file. The rows are the
    inventory's fields: a field no longer in it is dropped.
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
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(DICTIONARY_COLUMNS)
    for f in inventory.inventory_files:
        for c in f.file_fields:
            shared = len(files_of[column_of(c)]) > 1
            given = {
                "type": c.field_type,
                "format": c.field_format,
                "description": c.field_description,
            }
            before = earlier.get((f.file_path, c.name), {})
            row = [f.file_path, c.name]
            for column in VALUE_COLUMNS:
                own = _question_id({"file": f.file_path, "field": c.name, "column": column})
                ask = _question_id(shared_target(column_of(c), column)) if shared else own
                answer = answers.get(own)
                if answer is not None:
                    value, source = answer, Source.SUPPLIED
                else:
                    value, source = _cell(column, given.get(column) or "", before)
                    if source == Source.UNKNOWN and ask in answers:
                        value, source = answers[ask], Source.SUPPLIED
                if source == Source.UNKNOWN:
                    gap = gaps.setdefault(ask, Gap(c.name, column))
                    if f.file_path not in gap.files:
                        gap.files.append(f.file_path)
                counts[source] += 1
                row += [value, source.value]
            writer.writerow(row)
    questions = [_question(qid, gap) for qid, gap in gaps.items()]
    return out.getvalue(), questions, counts


def _question(question_id: str, gap: Gap) -> DocumentQuestion:
    """The one question for a gap: one file's cell, or a shared column's cells in each file."""
    first, many = gap.files[0], len(gap.files) > 1
    prompt = CELL_ASKS[gap.column].format(
        field=gap.name, place=SHARED if many else ONE_FILE.format(file=first)
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


def _question_id(target: Mapping[str, str | None]) -> str:
    """A question's identifier, derived from the gap it targets and never from its position, so
    that the same gap has the same identifier in every version (docs/specs/drafting.md)."""
    canonical = json.dumps(target, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"q-{digest[:QUESTION_ID_DIGITS]}"


def _answers(given: Sequence[DraftAnswer]) -> dict[str, str]:
    """The recorded answers by the question they answer. A blank answer leaves its gap open; of
    two answers to one question, the later in the list wins."""
    return {a.answered_question: a.answer_text for a in given if a.answer_text.strip()}
