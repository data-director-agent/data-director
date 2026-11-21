"""Summary values of a table's fields, under statistical disclosure control
(docs/specs/personal-data.md, #611).

The one module that imports ACRO, the SACRO project's output checker. For each field it computes
the values a reader needs to describe the data (rows read, null count, a range, a mean,
categories and missing-value codes) and writes only those that pass the rules:

- every count passes ACRO's minimum threshold *k* and is then rounded to the rounding base;
- a range is the *k*-th smallest and *k*-th largest values, never the raw minimum and maximum,
  and needs at least 2*k* values (our own rule, since ACRO does not check an extreme);
- a mean passes ACRO's threshold, p-ratio and nk-dominance rules, so that no one or two values
  dominate it.

A value that fails is left out, not altered to pass, and counted in the field's check; it is kept
nowhere. ACRO runs in suppression mode, in memory: its results are never finalised, so it writes
no file, and its logging and printing are silenced.
"""

from __future__ import annotations

import contextlib
import csv
import io
import logging
import math
import warnings
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from importlib.metadata import version
from pathlib import Path
from typing import Any

from dd_inventory.tables import TABLE_SUFFIXES, Table

THRESHOLD = 10
ROUNDING_BASE = 5
ROW_CAP = 100_000
# Values often used for missing data, reported with their counts and left out of a range or a
# mean. The empty cell is a null, counted on its own.
MISSING_CODES = ("-99", "-999", "999", "9999", "NA", "N/A", "NaN", "null", ".")
NUMERIC = frozenset({"integer", "number"})
ORDERED = NUMERIC | {"year", "date", "datetime", "time"}
CATEGORICAL = frozenset({"string", "boolean"})
# A field with more distinct values than this is read as identifiers or free text, not
# categories, and gets no frequency table.
MAX_CATEGORIES = 50
TOOL = "acro"

_ROWS, _NULL, _CODE, _CATEGORY = "rows", "null", "code", "category"


@dataclass(frozen=True)
class SummaryRules:
    """The disclosure rules' parameters. A researcher may tighten them, never relax them: a
    threshold below 10 or a rounding base below 5 is refused (invariant 8)."""

    threshold: int = THRESHOLD
    rounding_base: int = ROUNDING_BASE
    row_cap: int = ROW_CAP

    def __post_init__(self) -> None:
        if self.threshold < THRESHOLD:
            raise ValueError(f"the threshold may not be below {THRESHOLD}")
        if self.rounding_base < ROUNDING_BASE:
            raise ValueError(f"the rounding base may not be below {ROUNDING_BASE}")
        if self.row_cap < 1:
            raise ValueError("the row cap must be at least 1")

    def rounded(self, count: int) -> int:
        """`count` rounded to the nearest multiple of the base, halves up."""
        return int(count / self.rounding_base + 0.5) * self.rounding_base

    def description(self) -> str:
        return (
            f"{TOOL} {version(TOOL)}, with a minimum threshold of {self.threshold} and counts "
            f"rounded to base {self.rounding_base}"
        )


@dataclass
class Summaries:
    """What `summarise` gives for one table: for each field by name, its `field_summary` and
    `field_disclosure_check`, and what a reader should know about them."""

    fields: dict[str, tuple[dict[str, Any], dict[str, Any]]] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)


def available() -> str | None:
    """Why summaries cannot be made here, or `None` when they can."""
    try:
        import acro  # noqa: F401
    except ImportError as exc:
        return f"the disclosure checker ({TOOL}) could not be loaded: {exc}"
    return None


def summarise(
    path: Path,
    table: Table,
    relative: str,
    rules: SummaryRules,
    skip_categories: frozenset[str] = frozenset(),
) -> Summaries:
    """The summary values of each of `table`'s fields that pass the rules. A field named in
    `skip_categories`, such as one where possible personal data were found, gets no categories,
    so that a category is never a matched value."""
    rows, capped = _read(path, table, rules.row_cap)
    out = Summaries()
    if capped:
        out.limitations.append(
            f"In {relative}, summary values were computed from the first {rules.row_cap} rows only."
        )
    try:
        with _quiet():
            from acro import ACRO

            checker = ACRO(suppress=True)
            for index, spec in enumerate(table.fields):
                name = spec["name"]
                values = [row[index] if index < len(row) else "" for row in rows]
                out.fields[name] = _field(
                    checker, values, spec, rules, categories=name not in skip_categories
                )
    except Exception as exc:  # noqa: BLE001 - ACRO and pandas raise their own errors on odd data
        # Only the error's type: its message could repeat a value from the table.
        return Summaries(
            limitations=[
                *out.limitations,
                f"The summary values of {relative} could not be made ({type(exc).__name__}).",
            ]
        )
    return out


def _read(path: Path, table: Table, cap: int) -> tuple[list[list[str]], bool]:
    """Up to `cap` rows after the headers, each cell stripped; and whether there were more."""
    delimiter = TABLE_SUFFIXES[path.suffix.lower()]
    rows: list[list[str]] = []
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as fh:
        reader = csv.reader(fh, delimiter=delimiter)
        for _ in range(table.header_rows):
            next(reader, None)
        for row in reader:
            if len(rows) == cap:
                return rows, True
            if row:
                rows.append([cell.strip() for cell in row])
    return rows, False


@contextlib.contextmanager
def _quiet() -> Iterator[None]:
    """Silence ACRO's logging, printing and warnings while it runs."""
    sink = io.StringIO()
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        with (
            warnings.catch_warnings(),
            contextlib.redirect_stdout(sink),
            contextlib.redirect_stderr(sink),
        ):
            warnings.simplefilter("ignore")
            yield
    finally:
        logging.disable(previous)


def _field(
    checker: Any, values: list[str], spec: dict[str, Any], rules: SummaryRules, *, categories: bool
) -> tuple[dict[str, Any], dict[str, Any]]:
    field_type = spec.get("field_type")
    present = [v for v in values if v and v not in MISSING_CODES]
    by_category = categories and field_type in CATEGORICAL and len(set(present)) <= MAX_CATEGORIES
    kinds = [kind for v in values if (kind := _kind(v, by_category=by_category))]
    counts = _counts(checker, kinds)
    summary: dict[str, Any] = {}
    suppressed = sum(1 for c in counts.values() if c is None)
    rows = _counts(checker, [(_ROWS, "")] * len(values)).get((_ROWS, "")) if values else None
    if rows is not None:
        summary["summary_rows_read"] = rules.rounded(rows)
    elif values:
        suppressed += 1
    if (nulls := counts.get((_NULL, ""))) is not None:
        summary["summary_null_count"] = rules.rounded(nulls)
    codes = [
        {"missing_code": value, "missing_code_count": rules.rounded(count)}
        for (kind, value), count in sorted(counts.items(), key=lambda kv: kv[0])
        if kind == _CODE and count is not None
    ]
    # Ordered by rounded count, then name, so that the order does not tell two equal counts apart.
    kept = sorted(
        (-rules.rounded(count), value)
        for (kind, value), count in counts.items()
        if kind == _CATEGORY and count is not None
    )
    cats = [{"category_value": value, "category_count": -count} for count, value in kept]
    if field_type in ORDERED and present:
        bounds = _range(present, field_type, spec.get("field_format"), rules.threshold)
        if bounds is None:
            suppressed += 1
        else:
            summary["summary_range_low"], summary["summary_range_high"] = bounds
    if field_type in NUMERIC and present:
        mean = _mean(checker, present)
        if mean is None:
            suppressed += 1
        else:
            summary["summary_mean"] = mean
    if cats:
        summary["summary_categories"] = cats
    if codes:
        summary["summary_missing_codes"] = codes
    return summary, _check(field_type, rules, suppressed)


def _kind(value: str, *, by_category: bool) -> tuple[str, str] | None:
    """What a cell is counted as: a null, a missing-value code or a category, with its value; or
    `None` when it is counted as none of them."""
    if not value:
        return (_NULL, "")
    if value in MISSING_CODES:
        return (_CODE, value)
    return (_CATEGORY, value) if by_category else None


def _counts(checker: Any, kinds: list[tuple[str, str]]) -> dict[tuple[str, str], int | None]:
    """Each kind's count, or `None` where ACRO's minimum threshold suppressed it. ACRO is given
    opaque labels (`L0`, `L1`, ...), never the values: it builds pandas queries from labels, which
    a value holding a quote or a null byte would break."""
    if not kinds:
        return {}
    import pandas as pd

    distinct = sorted(set(kinds))
    label = {kind: f"L{i}" for i, kind in enumerate(distinct)}
    frame = pd.DataFrame({"label": [label[k] for k in kinds], "all": "n"})
    table = checker.crosstab(frame["label"], frame["all"])
    counted = {
        str(name): None if pd.isna(count) else int(count)
        for name, count in table.iloc[:, 0].items()
    }
    return {kind: counted.get(label[kind]) for kind in distinct}


def _mean(checker: Any, present: list[str]) -> float | None:
    """The mean of the values that parse as numbers, or `None` where ACRO suppressed it."""
    numbers = [n for n in (_number(v) for v in present) if n is not None]
    if not numbers:
        return None
    import pandas as pd

    frame = pd.DataFrame({"all": "n", "value": numbers})
    table = checker.pivot_table(frame, index="all", values="value", aggfunc="mean")
    value = table.iloc[0, 0]
    return None if pd.isna(value) else float(value)


def _range(
    present: list[str], field_type: str, field_format: str | None, k: int
) -> tuple[str, str] | None:
    """The *k*-th smallest and *k*-th largest values, as written in the file, or `None` when
    fewer than 2*k* values parse (invariant 6)."""
    keyed = [(key, v) for v in present if (key := _order_key(v, field_type, field_format))]
    if len(keyed) < 2 * k:
        return None
    keyed.sort(key=lambda kv: kv[0])
    return keyed[k - 1][1], keyed[-k][1]


def _order_key(value: str, field_type: str, field_format: str | None) -> tuple[Any] | None:
    """What `value` sorts by, in a one-item tuple so that zero is kept, or `None` if it does not
    parse as the field's type. A date or time with a time zone sorts by its UTC time."""
    if field_type in NUMERIC or field_type == "year":
        number = _number(value)
        return None if number is None else (number,)
    try:
        if field_format and field_format not in ("default", "any"):
            # A field's own format, read as written: a zone, if any, is in the format.
            parsed: Any = datetime.strptime(value, field_format)  # noqa: DTZ007
            if field_type == "date":
                parsed = parsed.date()
            elif field_type == "time":
                parsed = parsed.time()
        elif field_type == "date":
            parsed = date.fromisoformat(value)
        elif field_type == "datetime":
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            parsed = time.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if isinstance(parsed, datetime) and parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    elif isinstance(parsed, time):
        parsed = parsed.replace(tzinfo=None)
    return (parsed,)


def _number(value: str) -> float | None:
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _check(field_type: str | None, rules: SummaryRules, suppressed: int) -> dict[str, Any]:
    applied = ["minimum threshold", "rounding"]
    if field_type in ORDERED:
        applied.append("k-th value range")
    if field_type in NUMERIC:
        applied += ["p-ratio", "nk dominance"]
    return {
        "check_tool": TOOL,
        "check_tool_version": version(TOOL),
        "check_rules": applied,
        "check_threshold": rules.threshold,
        "check_rounding_base": rules.rounding_base,
        "check_suppressed": suppressed,
    }
