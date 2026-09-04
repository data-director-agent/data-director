"""Reading a draft data dictionary as Frictionless Table Schema (§8).

Table Schema is used rather than a shape invented here because C5 says no formats are invented
here, and because it is itself a registered standard — so the input to a grounded
recommendation is as grounded as the output. It is also plain JSON, which is why this reads it
with `jsonio` rather than taking on the `frictionless` package: a heavy dependency for a
`json.loads` and a type table would be hard to justify in an experiment whose dependency list
is part of what is being judged.

Two things about the format are worth knowing before reading the mapping below.

**`format` is already strptime syntax.** For temporal types Table Schema's `format` is
`default`, `any`, or a pattern in C/Python strptime form — the same alphabet as
`profiling.patterns.DATE_FORMATS`. So there is no translation layer here, only a membership
test, and a valid pattern that tier 1 does not recognise is itself the R3.4 finding.

**`missingValues` is declared per schema, not per field.** It therefore lands on the profile
rather than on every column; see `DatasetProfile.missing_value_codes`. Table Schema v2 adds a
per-field form, which is read when present and only then.

There is no `unit` in the standard. Where a schema carries one it is a local extension, so a
unit here usually comes from the column name instead — the same heuristic tier 1 uses, recorded
with the same derivation so the difference stays visible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from standards_advisor.jsonio import read_json_object, text_list
from standards_advisor.models.common import Derivation
from standards_advisor.models.profile import ColumnProfile, ColumnType
from standards_advisor.profiling import patterns

#: Table Schema types that map onto a `ColumnType` with no further inspection.
SIMPLE_TYPES: dict[str, ColumnType] = {
    "boolean": ColumnType.BOOLEAN,
    "date": ColumnType.DATE,
    "datetime": ColumnType.DATETIME,
    "time": ColumnType.TIME,
    "duration": ColumnType.DURATION,
    "geopoint": ColumnType.COORDINATE,
    "geojson": ColumnType.COORDINATE,
}

#: Coarse-grained dates. Table Schema gives them their own types; ISO 8601 covers both, and the
#: pattern is what makes that recommendation actionable rather than a platitude.
COARSE_DATE_PATTERNS: dict[str, str] = {
    "year": "%Y",
    "yearmonth": "%Y-%m",
}

#: Types with no honest `ColumnType`. Structured or deliberately unconstrained values, for which
#: none of R3.4's field-level standards apply — so they become `UNKNOWN` and are reported, rather
#: than being filed as free text and given advice that does not fit.
UNMAPPABLE_TYPES: frozenset[str] = frozenset({"object", "array", "any"})

#: String formats that make a column an identifier rather than prose.
IDENTIFIER_FORMATS: frozenset[str] = frozenset({"uuid", "uri", "binary"})

#: The default the standard assigns when `format` is absent or `default`, per type.
DEFAULT_PATTERNS: dict[ColumnType, str] = {
    ColumnType.DATE: "%Y-%m-%d",
    ColumnType.TIME: "%H:%M:%S",
}


@dataclass(frozen=True)
class DictionaryFinding:
    """A content problem, for the caller to record with `StageRun.fail`."""

    kind: str
    detail: str


@dataclass(frozen=True)
class ParsedDictionary:
    """One data dictionary, as far as it could be read."""

    columns: list[ColumnProfile] = field(default_factory=list)
    missing_value_codes: list[str] = field(default_factory=list)
    title: str | None = None
    description: str | None = None
    notes: list[str] = field(default_factory=list)
    findings: list[DictionaryFinding] = field(default_factory=list)


def read_dictionary(path: Path) -> ParsedDictionary:
    """Parse a Table Schema file into column profiles.

    Never raises: an unreadable or malformed dictionary comes back as a `ParsedDictionary` with
    no columns and a finding saying why, because a dictionary we cannot read is a fact about the
    input rather than a defect in the pipeline (see `errors`).
    """
    raw, error = read_json_object(path)
    if error is not None:
        return ParsedDictionary(
            findings=[DictionaryFinding("dictionary_unreadable", f"{path} {error}")]
        )

    fields = raw.get("fields")
    if not isinstance(fields, list) or not fields:
        return ParsedDictionary(
            findings=[
                DictionaryFinding(
                    "dictionary_has_no_fields",
                    f"{path} declares no `fields`; a Table Schema without them describes nothing",
                )
            ]
        )

    columns: list[ColumnProfile] = []
    notes: list[str] = []
    findings: list[DictionaryFinding] = []

    for position, entry in enumerate(fields):
        if not isinstance(entry, dict):
            findings.append(
                DictionaryFinding(
                    "dictionary_field_malformed", f"field {position} is not an object"
                )
            )
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            findings.append(
                DictionaryFinding("dictionary_field_unnamed", f"field {position} has no name")
            )
            continue
        column, column_notes, column_findings = _column(entry, name.strip(), position, str(path))
        columns.append(column)
        notes.extend(column_notes)
        findings.extend(column_findings)

    return ParsedDictionary(
        columns=columns,
        missing_value_codes=_missing_values(raw.get("missingValues")),
        title=_text(raw.get("title")),
        description=_text(raw.get("description")),
        notes=notes,
        findings=findings,
    )


def _column(
    entry: dict[str, object], name: str, position: int, source: str
) -> tuple[ColumnProfile, list[str], list[DictionaryFinding]]:
    """Map one Table Schema field onto a `ColumnProfile`."""
    notes: list[str] = []
    findings: list[DictionaryFinding] = []

    declared_type = _text(entry.get("type")) or "string"
    declared_format = _text(entry.get("format"))
    constraints = entry.get("constraints")
    enum = text_list(constraints.get("enum")) if isinstance(constraints, dict) else []

    unit, unit_derivation = _unit(entry, name, declared_type)
    inferred, pattern = _map_type(
        declared_type=declared_type,
        declared_format=declared_format,
        enum=enum,
        unit=unit,
        entry=entry,
    )

    if inferred is ColumnType.UNKNOWN:
        findings.append(
            DictionaryFinding(
                "declared_type_unmapped",
                f"{name}: declared type {declared_type!r} has no field-level standard we can "
                "search for, so no advice is offered for it rather than advice that does not fit",
            )
        )

    if pattern is not None and inferred in {ColumnType.DATE, ColumnType.DATETIME}:
        known = patterns.DATE_FORMATS if inferred is ColumnType.DATE else patterns.DATETIME_FORMATS
        if pattern not in known:
            # Not a failure. An unusual but valid pattern is precisely what R3.4 exists to find,
            # and saying so is more useful than dropping the column's format.
            notes.append(
                f"{name}: declared format {pattern!r} is not one tier 1 recognises — "
                "worth an ISO 8601 recommendation on its own"
            )

    return (
        ColumnProfile(
            name=name,
            position=position,
            file=source,
            inferred_type=inferred,
            type_derivation=Derivation.DECLARED_IN_DATA_DICTIONARY,
            pattern=pattern,
            unit=unit,
            unit_derivation=unit_derivation,
            declared_type=declared_type,
            description=_text(entry.get("description")) or _text(entry.get("title")),
            permitted_values=enum,
            missing_value_codes=_missing_values(entry.get("missingValues")),
        ),
        notes,
        findings,
    )


def _map_type(
    *,
    declared_type: str,
    declared_format: str | None,
    enum: list[str],
    unit: str | None,
    entry: dict[str, object],
) -> tuple[ColumnType, str | None]:
    """Decide a column's type and pattern, in a documented precedence.

    The order matters and mirrors `profiling.columns.infer_type`'s reasoning, adapted to a
    declaration rather than a sample:

    1. Types with no honest mapping are `UNKNOWN`. Nothing later can rescue them.
    2. Temporal and geographic types win next: they are unambiguous, and they are where R3.4 has
       the most to say.
    3. A declared enumeration beats the underlying type. A column whose permitted values are
       listed is a coded field, whatever it is coded *as*, and coded fields are exactly what
       R3.1 links to a vocabulary — an integer code list needs a vocabulary far more than it
       needs a number format.
    4. Then identifiers, then quantities with units, then plain numbers, then prose.
    """
    if declared_type in UNMAPPABLE_TYPES:
        return ColumnType.UNKNOWN, None

    if declared_type in COARSE_DATE_PATTERNS:
        return ColumnType.DATE, COARSE_DATE_PATTERNS[declared_type]

    simple = SIMPLE_TYPES.get(declared_type)
    if simple is not None:
        return simple, _pattern(simple, declared_format)

    if enum:
        return ColumnType.CATEGORICAL, None

    if declared_type == "string":
        if declared_format in IDENTIFIER_FORMATS:
            return ColumnType.IDENTIFIER, declared_format
        if patterns.looks_like_coordinate_name(_name_of(entry)):
            return ColumnType.COORDINATE, None
        return ColumnType.FREE_TEXT, None

    if declared_type in {"number", "integer"}:
        if patterns.looks_like_coordinate_name(_name_of(entry)):
            return ColumnType.COORDINATE, None
        return (ColumnType.QUANTITY_WITH_UNIT if unit else ColumnType.NUMBER), None

    # A type the standard does not define. Recorded as unknown for the same reason as the
    # structured types: we do not know what it is, so we say so.
    return ColumnType.UNKNOWN, None


def _pattern(column_type: ColumnType, declared_format: str | None) -> str | None:
    """The concrete pattern for a temporal column.

    `default` and absence both mean the standard's own ISO form; `any` means the schema declines
    to say, so we decline too rather than assuming ISO. Anything else is a strptime pattern and
    is taken verbatim.
    """
    if declared_format in {None, "default"}:
        return DEFAULT_PATTERNS.get(column_type)
    if declared_format == "any":
        return None
    return declared_format


#: Declared types for which a unit read off the column name is plausible. Restricting the
#: heuristic to these matters: `unit_from_column_name` recognises `year` as a unit, so a column
#: called `survey_year` declared as a Table Schema `year` would otherwise be reported as a
#: quantity measured in years. A unit belongs to a magnitude, not to a date, a flag or a label.
UNIT_BEARING_TYPES: frozenset[str] = frozenset({"number", "integer"})


def _unit(
    entry: dict[str, object], name: str, declared_type: str
) -> tuple[str | None, Derivation | None]:
    """A column's unit, and how it was arrived at.

    Table Schema has no `unit`, so a schema carrying one is using a local extension — but when
    it does, it is the researcher stating the unit outright, which R5 names as something only
    they can supply, and it is honoured whatever the declared type. Failing that we fall back to
    the same column-name heuristic tier 1 uses, but only for types a unit can belong to, and
    record the weaker derivation so the two are never confused.
    """
    declared = _text(entry.get("unit"))
    if declared is not None:
        return declared, Derivation.DECLARED_IN_DATA_DICTIONARY
    if declared_type not in UNIT_BEARING_TYPES:
        return None, None
    from_name = patterns.unit_from_column_name(name)
    if from_name is not None:
        return from_name, Derivation.LOCAL_PARSE
    return None, None


def _name_of(entry: dict[str, object]) -> str:
    return _text(entry.get("name")) or ""


def _missing_values(value: object) -> list[str]:
    """Missing-value codes, **keeping the empty string**.

    Not `jsonio.text_list`, which drops empties — correct for keywords and enumerations, wrong
    here. `""` is Table Schema's own default missing value and a real declaration: "a blank cell
    means missing" and "we have no convention for blank cells" are different statements, and R5
    names missing value codes as something only the researcher can tell us. Codes are also not
    stripped, since leading or trailing space could be the convention itself.
    """
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
