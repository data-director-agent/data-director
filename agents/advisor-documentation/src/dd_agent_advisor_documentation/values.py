"""What a writer and the data dictionary are told of a table field: its name, type and format,
and the summary values the inventory command wrote after disclosure control
(docs/specs/personal-data.md, #571, #611).

A summary value is read from the inventory, never from the data, so it is inferred in the sense
of docs/specs/drafting.md. A range's bounds are the k-th smallest and largest values, not the
minimum and maximum, and the writer is told so.
"""

from __future__ import annotations

import json
import re
from typing import Any

from dd_sdk.contract.models import TableField

# What the writer is told a range is, beside the range itself.
RANGE_NOTE = "bounds leave out the extremes: at least {k} values lie at or beyond each"


def field_facts(field: TableField) -> dict[str, Any]:
    """The field as a writer sees it: name, type and format, with `values` when it has any."""
    facts: dict[str, Any] = {
        k: v
        for k, v in (
            ("name", field.name),
            ("type", field.field_type),
            ("format", field.field_format),
        )
        if v
    }
    if values := _values(field):
        facts["values"] = values
    return facts


# Where a list of values that mean "missing" is split when it is not already JSON: a new line, a
# comma or a semicolon.
_SPLIT = re.compile(r"[\n,;]")
# What a bare value never holds: brackets or a colon, which a note about the value would, or a full
# stop and a space, which ends a sentence.
_NOT_BARE = re.compile(r"[()\[\]:]|\.\s")


def missing_values_cell(text: str) -> str:
    """The `missing_values` cell for an answer or a cell: a JSON array of strings, the form of a
    Frictionless Table Schema field's `missingValues` (https://datapackage.org/standard/table-schema/).

    A JSON array of strings is kept as it is, whatever its values, so `[""]` says that only an
    empty cell is missing, which is the standard's default. Text is split on new lines, commas and
    semicolons into values, each trimmed, empty ones left out and repeats dropped, when each is
    a bare value such as `-99` or `NA`. Nothing is guessed from the words: `none` is a value, as
    `NA` is. Text in which any part is a note, such as `-99 (sensor off), NA`, is the person's own
    words and is kept as written, for them to put right. Text with no value gives "", a gap still
    open. A cell written before this form, `-99, NA`, reads the same way.
    """
    stripped = text.strip()
    if not stripped:
        return ""
    try:
        loaded = json.loads(stripped)
    except ValueError:
        loaded = None
    if isinstance(loaded, list) and all(isinstance(v, str) for v in loaded):
        values = list(dict.fromkeys(loaded))
    else:
        if _NOT_BARE.search(stripped):
            return stripped
        values = list(dict.fromkeys(v for v in map(str.strip, _SPLIT.split(stripped)) if v))
    return json.dumps(values, ensure_ascii=False, separators=(",", ":")) if values else ""


def missing_codes(field: TableField) -> str:
    """The values the field holds that are often used for missing data, as a `missing_values` cell;
    empty when it holds none or no summaries were made."""
    summary = field.field_summary
    if summary is None or not summary.summary_missing_codes:
        return ""
    return missing_values_cell(json.dumps([m.missing_code for m in summary.summary_missing_codes]))


def _values(field: TableField) -> dict[str, Any]:
    summary, check = field.field_summary, field.field_disclosure_check
    if summary is None or check is None:
        return {}
    values: dict[str, Any] = {}
    if summary.summary_range_low is not None and summary.summary_range_high is not None:
        values["range"] = {
            "low": summary.summary_range_low,
            "high": summary.summary_range_high,
            "note": RANGE_NOTE.format(k=check.check_threshold),
        }
    if summary.summary_mean is not None:
        values["mean"] = round(summary.summary_mean, 4)
    if summary.summary_categories:
        values["categories"] = {
            c.category_value: c.category_count for c in summary.summary_categories
        }
    if summary.summary_missing_codes:
        values["missing_value_codes"] = {
            m.missing_code: m.missing_code_count for m in summary.summary_missing_codes
        }
    for key, count in (
        ("rows_read", summary.summary_rows_read),
        ("empty_cells", summary.summary_null_count),
    ):
        if count is not None:
            values[key] = count
    if values and check.check_suppressed:
        values["left_out"] = (
            f"{check.check_suppressed} value(s) were left out because fewer than "
            f"{check.check_threshold} records shared them"
        )
    return values
