"""What a writer and the data dictionary are told of a table field: its name, type and format,
and the summary values the inventory command wrote after disclosure control
(docs/specs/personal-data.md, #571, #611).

A summary value is read from the inventory, never from the data, so it is inferred in the sense
of docs/specs/drafting.md. A range's bounds are the k-th smallest and largest values, not the
minimum and maximum, and the writer is told so.
"""

from __future__ import annotations

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


def missing_codes(field: TableField) -> str:
    """The values the field holds that are often used for missing data, comma-separated; empty
    when it holds none or no summaries were made."""
    summary = field.field_summary
    if summary is None:
        return ""
    return ", ".join(m.missing_code for m in summary.summary_missing_codes)


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
