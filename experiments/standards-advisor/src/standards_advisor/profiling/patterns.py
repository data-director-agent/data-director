"""Pure recognisers for §5.1 tier-1 column typing. No I/O, no model, no state.

§5.1 says working out column types "does more work than it looks like", and that R3.4 rests on
it entirely. The reason it is worth building first is here: a column recognised as dates by
successfully parsing its sampled values against a list of candidate formats yields an ISO 8601
recommendation with near-total confidence and nothing inferred by a model.

The important output is not "this is a date" but **which format matched**. "Use ISO 8601" is
not actionable advice on its own; "this column is `%d/%m/%Y`, which ISO 8601 would write
`%Y-%m-%d`" is.
"""

from __future__ import annotations

import re
from datetime import datetime

# Candidate date formats, most specific and least ambiguous first. Order matters: a value like
# "03/06/2024" parses under both %d/%m/%Y and %m/%d/%Y, and whichever is tried first wins for
# the whole column. Day-first leads because this is a British project, and the choice is
# recorded in the profile rather than hidden — an ambiguous column should be visible as a
# question, not settled silently.
DATE_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%d %B %Y",
    "%d %b %Y",
    "%B %d, %Y",
    "%Y%m%d",
)

DATETIME_FORMATS: tuple[str, ...] = (
    # %z matches a literal "Z" as well as ±HH:MM, so there is no separate Zulu format here.
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
)

# Structured identifiers, checked before low-cardinality categorisation. A column of ORCIDs has
# few distinct values in a small sample and would otherwise be called categorical, which would
# send it to the wrong §5.2 search.
IDENTIFIER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("doi", re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:)?10\.\d{4,9}/\S+$", re.I)),
    ("orcid", re.compile(r"^(?:https?://orcid\.org/)?\d{4}-\d{4}-\d{4}-\d{3}[\dX]$", re.I)),
    ("uri", re.compile(r"^https?://\S+$", re.I)),
    ("uuid", re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)),
    # A coded accession: letters, a separator, then at least one digit group. Requires the
    # separator so that short categorical codes ("O", "A", "B") are not swept up.
    ("accession", re.compile(r"^[A-Za-z]{2,}[-_.][A-Za-z0-9]*\d[A-Za-z0-9-_.]*$")),
)

_NUMBER = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$")

# A quantity written with its unit in the value rather than the header: "12.4 mg/L", "5km".
_QUANTITY_WITH_UNIT = re.compile(
    r"^[+-]?(?:\d+\.?\d*|\.\d+)\s*"
    r"(?P<unit>%|[A-Za-zµ°]+(?:[/·^.-]?[A-Za-z0-9µ°]+)*)$"
)

# Units appearing as a header suffix. Matched against the trailing token of a snake_case name.
UNIT_SUFFIXES: frozenset[str] = frozenset(
    {
        "pct",
        "percent",
        "perc",
        "mm",
        "cm",
        "m",
        "km",
        "nm",
        "um",
        "g",
        "kg",
        "mg",
        "ug",
        "ng",
        "t",
        "l",
        "ml",
        "ul",
        "s",
        "sec",
        "min",
        "hr",
        "h",
        "day",
        "days",
        "yr",
        "year",
        "years",
        "c",
        "k",
        "degc",
        "degk",
        "celsius",
        "kelvin",
        "ppm",
        "ppb",
        "ph",
        "cm3",
        "m3",
        "m2",
        "cm2",
        "ha",
        "gcm3",
        "g_cm3",
        "kgm3",
        "mgl",
        "mg_l",
        "ugl",
        "count",
        "n",
    }
)

_COORDINATE_NAME = re.compile(
    r"(^|_)(lat|latitude|lon|long|longitude|lng|easting|northing|x|y)($|_)", re.I
)
_LATITUDE_NAME = re.compile(r"(^|_)(lat|latitude)($|_)", re.I)


def is_blank(value: str) -> bool:
    return not value.strip()


def is_number(value: str) -> bool:
    return bool(_NUMBER.match(value.strip()))


def match_date_format(value: str) -> str | None:
    """Return the first `DATE_FORMATS` entry that parses `value`, or `None`."""
    candidate = value.strip()
    for fmt in DATE_FORMATS:
        try:
            datetime.strptime(candidate, fmt)  # noqa: DTZ007 — parsing a naive date is the point
        except ValueError:
            continue
        return fmt
    return None


def match_datetime_format(value: str) -> str | None:
    """Return the first `DATETIME_FORMATS` entry that parses `value`, or `None`."""
    candidate = value.strip()
    for fmt in DATETIME_FORMATS:
        try:
            datetime.strptime(candidate, fmt)  # noqa: DTZ007 — offset may be absent by design
        except ValueError:
            continue
        return fmt
    return None


def match_identifier(value: str) -> str | None:
    """Return the name of the first identifier pattern matching `value`, or `None`."""
    candidate = value.strip()
    for name, pattern in IDENTIFIER_PATTERNS:
        if pattern.match(candidate):
            return name
    return None


def match_quantity_unit(value: str) -> str | None:
    """Return a unit read from the *value*, e.g. `mg/L` in `12.4 mg/L`."""
    match = _QUANTITY_WITH_UNIT.match(value.strip())
    if match is None:
        return None
    return match.group("unit")


def unit_from_column_name(name: str) -> str | None:
    """Return a unit read from a column *name*, e.g. `pct` from `organic_carbon_pct`.

    A unit in the header is a genuine R3.4 finding: it means the unit is documented in prose
    rather than declared, which is precisely what a units standard such as UCUM addresses.
    """
    tokens = [token for token in re.split(r"[_\s-]+", name.strip().lower()) if token]
    if not tokens:
        return None
    # Try the longest trailing run first, so `g_cm3` beats `cm3`.
    for size in (3, 2, 1):
        if len(tokens) <= size:
            continue
        candidate = "_".join(tokens[-size:])
        if candidate in UNIT_SUFFIXES:
            return candidate
        squashed = "".join(tokens[-size:])
        if squashed in UNIT_SUFFIXES:
            return candidate
    return None


def looks_like_coordinate_name(name: str) -> bool:
    return bool(_COORDINATE_NAME.search(name))


def coordinate_in_range(name: str, value: str) -> bool:
    """Whether a numeric value falls in the range its column name implies.

    The name alone is not enough — a column called `x` is not a coordinate just because it is
    called `x` — so the range check has to agree before a column is reported as one.
    """
    try:
        number = float(value.strip())
    except ValueError:
        return False
    limit = 90.0 if _LATITUDE_NAME.search(name) else 180.0
    return -limit <= number <= limit
