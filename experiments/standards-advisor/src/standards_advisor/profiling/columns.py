"""Column type inference — §5.1 tier 1, and the whole basis of R3.4.

The order the checks run in is the design, not an implementation detail, so it is written down
explicitly below. Every branch records the `Derivation` and, where there is one, the concrete
pattern that matched.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable

from standards_advisor.models.common import Derivation
from standards_advisor.models.profile import ColumnProfile, ColumnType
from standards_advisor.profiling import patterns

# A column is categorical if it has at most this many distinct values *and* they repeat. Both
# conditions are needed: 20 distinct values out of 20 rows is not a category system, it is an
# identifier or free text that happens to be short.
MAX_CATEGORICAL_DISTINCT = 20
MAX_CATEGORICAL_RATIO = 0.5

# Fraction of non-blank sampled values that must match for a type to be claimed. Below 1.0 so a
# single typo in forty rows does not demote a date column to free text; high enough that a
# genuinely mixed column is not mislabelled.
MATCH_THRESHOLD = 0.9

# Example values kept in the profile for human inspection of a run. They are NEVER sent to a
# model — §1.4 permits only names, inferred types and counts to leave the machine.
EXAMPLE_VALUES_KEPT = 3


def _fraction_matching(values: list[str], predicate: Callable[[str], bool]) -> float:
    if not values:
        return 0.0
    hits = sum(1 for value in values if predicate(value))
    return hits / len(values)


def _dominant_format(
    values: list[str], matcher: Callable[[str], str | None]
) -> tuple[str | None, float]:
    """Return the most common format among `values`, and the fraction it covers.

    Reporting the *dominant* format rather than the first that matched is what makes a mixed
    date column visible: if two formats each cover half the values, the coverage figure falls
    below the threshold and the column is not claimed as a date at all.
    """
    if not values:
        return None, 0.0
    counts: Counter[str] = Counter()
    for value in values:
        matched = matcher(value)
        if matched is not None:
            counts[matched] += 1
    if not counts:
        return None, 0.0
    best, hits = counts.most_common(1)[0]
    return best, hits / len(values)


def infer_type(name: str, values: list[str]) -> tuple[ColumnType, str | None, str | None]:
    """Infer one column's type from its sampled values.

    Returns `(type, pattern, unit)`. The check order is:

    1. **All blank** → `EMPTY`. There is nothing to recommend for an empty column, and saying
       so beats guessing from the header.
    2. **Date-time**, then **date**, by parsing against candidate formats. First because this is
       the cheapest and most certain finding in the whole pipeline, and R3.4 rests on it.
    3. **Structured identifier** (DOI, ORCID, URI, UUID, accession). Before categorisation: a
       column of ORCIDs has few distinct values in a small sample and would otherwise be called
       categorical, sending it to the wrong §5.2 search.
    4. **Coordinate** — requires the header to suggest one *and* every value to fall in the
       implied range. The name alone is not enough; a column called `x` is not a coordinate
       merely because it is called `x`.
    5. **Quantity with a unit**, from the value (`12.4 mg/L`) or the header
       (`organic_carbon_pct`), else a plain **number**. A unit in a header is a real R3.4
       finding: the unit is documented in prose rather than declared.
    6. **Categorical**, by low cardinality with repetition.
    7. **Free text**, the residue.
    """
    non_blank = [value for value in values if not patterns.is_blank(value)]
    if not non_blank:
        return ColumnType.EMPTY, None, None

    datetime_format, datetime_coverage = _dominant_format(non_blank, patterns.match_datetime_format)
    if datetime_coverage >= MATCH_THRESHOLD:
        return ColumnType.DATETIME, datetime_format, None

    date_format, date_coverage = _dominant_format(non_blank, patterns.match_date_format)
    if date_coverage >= MATCH_THRESHOLD:
        return ColumnType.DATE, date_format, None

    identifier_kind, identifier_coverage = _dominant_format(non_blank, patterns.match_identifier)
    if identifier_coverage >= MATCH_THRESHOLD:
        return ColumnType.IDENTIFIER, identifier_kind, None

    numeric_coverage = _fraction_matching(non_blank, patterns.is_number)

    if (
        numeric_coverage >= MATCH_THRESHOLD
        and patterns.looks_like_coordinate_name(name)
        and all(patterns.coordinate_in_range(name, value) for value in non_blank)
    ):
        return ColumnType.COORDINATE, "decimal_degrees", None

    if numeric_coverage >= MATCH_THRESHOLD:
        header_unit = patterns.unit_from_column_name(name)
        if header_unit is not None:
            return ColumnType.QUANTITY_WITH_UNIT, "unit_in_header", header_unit
        return ColumnType.NUMBER, None, None

    value_unit, value_unit_coverage = _dominant_format(non_blank, patterns.match_quantity_unit)
    if value_unit_coverage >= MATCH_THRESHOLD:
        return ColumnType.QUANTITY_WITH_UNIT, "unit_in_value", value_unit

    distinct = len(set(non_blank))
    if distinct <= MAX_CATEGORICAL_DISTINCT and distinct <= MAX_CATEGORICAL_RATIO * len(non_blank):
        return ColumnType.CATEGORICAL, None, None

    return ColumnType.FREE_TEXT, None, None


def profile_column(
    *,
    name: str,
    position: int,
    file: str,
    values: list[str],
    exact_counts: bool = False,
) -> ColumnProfile:
    """Build a `ColumnProfile` from sampled values.

    `exact_counts` is `False` for every caller in the pipeline, because the pipeline only ever
    sees the head of a file. It is recorded rather than assumed so that a later ranking rule
    cannot mistake a sample statistic for a population one.
    """
    inferred, pattern, unit = infer_type(name, values)
    non_blank = [value for value in values if not patterns.is_blank(value)]
    blank_count = len(values) - len(non_blank)

    return ColumnProfile(
        name=name,
        position=position,
        file=file,
        inferred_type=inferred,
        type_derivation=Derivation.LOCAL_PARSE,
        pattern=pattern,
        unit=unit,
        sample_size=len(values),
        blank_count=blank_count,
        blank_proportion=(blank_count / len(values)) if values else 0.0,
        distinct_count=len(set(non_blank)),
        distinct_count_is_exact=exact_counts,
        example_values=_examples(non_blank),
    )


def _examples(non_blank: list[str]) -> list[str]:
    """A few distinct values, for a human reading the run record. Never sent to a model."""
    seen: list[str] = []
    for value in non_blank:
        trimmed = value.strip()
        if trimmed not in seen:
            seen.append(trimmed)
        if len(seen) >= EXAMPLE_VALUES_KEPT:
            break
    return seen
