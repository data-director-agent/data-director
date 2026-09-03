"""§6.1 — the dataset profile.

The profile is the only thing later stages search on, so a profiling mistake shows up as a
retrieval mistake unless the profile records how each of its own statements was arrived at
(§5.1). Every inferred field here therefore carries a `Derivation`, either inside a `Term` or
as a sibling `*_derivation` field.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from standards_advisor.models.common import Derivation, Frozen, LifecyclePhase, Term


class ColumnType(StrEnum):
    """What tier-1 inference concluded a column holds.

    These are the categories §5.1 names, and R3.4 rests entirely on them: a column recognised
    as dates yields an ISO 8601 recommendation with near-total confidence and no model
    involved.
    """

    DATE = "date"
    DATETIME = "datetime"
    NUMBER = "number"
    QUANTITY_WITH_UNIT = "quantity_with_unit"
    CATEGORICAL = "categorical"
    IDENTIFIER = "identifier"
    COORDINATE = "coordinate"
    FREE_TEXT = "free_text"
    EMPTY = "empty"
    """Every sampled value was blank. Distinguished from free text on purpose — there is
    nothing to recommend for an empty column, and saying so is better than guessing."""

    TIME = "time"
    """A time of day with no date. ISO 8601 covers it, so R3.4 has something to say."""
    DURATION = "duration"
    """An elapsed quantity. ISO 8601 durations are the answer, and are widely got wrong."""
    BOOLEAN = "boolean"
    """A two-valued field. How true and false are written down — `TRUE`/`1`/`yes` — is a real
    interoperability question, which is why this is a type rather than a categorical."""

    UNKNOWN = "unknown"
    """Declared in a data dictionary in terms we could not map (§8).

    The same choice `EmptyRegistry` makes one layer up: refusing beats a plausible guess. The
    column stays in the profile with its `declared_type` recorded verbatim, a failure explains
    why it could not be mapped, and no field-level search is run on it — rather than it being
    quietly filed as free text and given advice that does not apply.

    Only ever produced by the §8 route. Tier-1 inference always reaches a conclusion, even if
    that conclusion is `FREE_TEXT` or `EMPTY`."""


class ContentFingerprint(Frozen):
    """Identifies the input, so C17 caching can be added later without reworking run records."""

    algorithm: str = "sha256"
    digest: str
    total_bytes: int
    files_hashed: int


class SourceRef(Frozen):
    """Where the profile's inputs came from and when it was built."""

    kind: str
    """`local_files`, `planned_documentation` (§8 — a README and a draft data dictionary, with no
    data yet), or a repository name once repository ingest exists."""
    locations: list[str] = Field(default_factory=list)
    metadata_record: str | None = None


class FileEntry(Frozen):
    path: str
    format: str | None
    """A short label such as `csv` or `xlsx`; `None` when nothing recognised it."""
    format_derivation: Derivation | None
    """Which signal decided — `FILE_MAGIC` beats `FILE_EXTENSION` where both fire."""
    media_type: str | None = None
    size_bytes: int
    rows_sampled: int | None = None
    """Rows actually read. Evidence that only the head was touched (§1.4)."""
    is_tabular: bool = False
    notes: list[str] = Field(default_factory=list)


class ColumnProfile(Frozen):
    """One column: observed from sampled values (§5.1), or declared in a data dictionary (§8).

    R3.4 depends on this either way. `type_derivation` says which route produced it —
    `LOCAL_PARSE` for a column parsed from a file, `DECLARED_IN_DATA_DICTIONARY` for one a
    researcher wrote down before the data existed.

    The count fields are optional because a planned column has nothing to count. Reporting `0`
    blanks for a column that has never been filled in would be a statement about data that does
    not exist, and the §5.3 rules are already specified to skip a missing input rather than
    score it zero.
    """

    name: str
    position: int
    file: str
    """The file this column belongs to, or the dictionary that declared it (§8)."""
    inferred_type: ColumnType
    type_derivation: Derivation
    pattern: str | None = None
    """The concrete pattern that matched — e.g. `%d/%m/%Y`. Naming the format is the whole
    point for R3.4: 'it is a date' is not actionable, 'it is `%d/%m/%Y`, use ISO 8601' is."""
    unit: str | None = None
    """A unit for the column's values, e.g. `pct` from `organic_carbon_pct`."""
    unit_derivation: Derivation | None = None
    """How the unit was arrived at — `LOCAL_PARSE` when read off the column name,
    `DECLARED_IN_DATA_DICTIONARY` when the dictionary said so outright.

    §6.1 requires everything inferred to record how, and a unit guessed from a header suffix is
    very much inferred. That this was missing before §8 was a gap, not a decision: R5 lists units
    among the things only a researcher can supply, so the difference between a declared unit and
    one pattern-matched out of a column name is exactly what a reader needs to see."""

    sample_size: int | None = None
    blank_count: int | None = None
    blank_proportion: float | None = None
    distinct_count: int | None = None
    """Distinct values *observed*. `None` for a planned column, and deliberately not filled
    from a declared enumeration: a codebook listing three permitted values is a statement about
    what may be recorded, not a count of what was. `permitted_values` carries that, more
    precisely, and a ranking rule must not be able to read a plan as a measurement."""
    distinct_count_is_exact: bool | None = None
    """Tri-state. `None` when no data was read at all (§8), `False` when only the head was
    sampled — which is always, for a real file — and `True` never, so far. Recorded so a later
    rule cannot mistake a sample statistic for a population one; `ranking.rules.type_match` is
    the rule that will read it."""

    example_values: list[str] = Field(default_factory=list)
    """Observed values, kept for human inspection of a run. **Never sent to a model** — §1.4
    permits only names, inferred types and counts to leave the machine. Contrast
    `permitted_values`, which may."""

    declared_type: str | None = None
    """The type as the data dictionary wrote it, before mapping onto `ColumnType` (§8).

    Kept verbatim because the mapping is lossy and may be wrong: a declared type we could not
    map is recorded here with the failure that says so, rather than guessed at."""
    description: str | None = None
    """The variable definition from the data dictionary — first in R5's list of things that
    "cannot be inferred and require direct researcher input"."""
    permitted_values: list[str] = Field(default_factory=list)
    """The values a data dictionary declares this column may take.

    §1.4 permits these to reach a model, where `example_values` never may. The line is declared
    schema versus observed data: a codebook entry is a statement of intent written by the
    researcher, not an observation of anything or anyone. It is also exactly what R3.1 needs in
    order to match a vocabulary before any data exists."""
    missing_value_codes: list[str] = Field(default_factory=list)
    """How this *particular* column says absence will be recorded.

    Populated only from a genuinely per-field declaration. Table Schema declares `missingValues`
    at schema level, so the usual case lands on `DatasetProfile.missing_value_codes` instead —
    copying one schema-wide declaration onto every column would present a global fact as a
    per-field one, and a reader could not tell which it had been."""


class MeasuredVariable(Frozen):
    """A variable named in the free-text description (§5.1 tier 3). None at v0.1."""

    name: str
    derivation: Derivation
    source_text: str | None = None


class DatasetProfile(Frozen):
    """§6.1."""

    profile_id: str
    fingerprint: ContentFingerprint
    source: SourceRef
    profiled_at: str
    profiler_version: str

    phase: LifecyclePhase = LifecyclePhase.COLLECTED
    """Which entry point produced this profile (§8). Defaults to the pre-§8 behaviour.

    Read by `assemble` to say which recommendations are advice brought forward from a later
    Blueprint phase, and by `retrieve` to decide whether to search on planned or found formats.
    """

    title: str | None = None
    abstract: str | None = None
    keywords: list[str] = Field(default_factory=list)

    title_derivation: Derivation | None = None
    abstract_derivation: Derivation | None = None
    keywords_derivation: Derivation | None = None
    """How the free-text description was arrived at.

    `SUPPLIED_METADATA` when it came from a repository-style metadata record, `LOCAL_PARSE` when
    it was read out of README prose (§8). §6.1 requires everything inferred to say how, and
    these three had no derivation before §8 because they were only ever copied from a supplied
    record — reading them out of a README is genuine parsing, and `retrieve` puts both the title
    and the abstract into registry queries as free text, so a mistake here surfaces as a
    retrieval mistake."""

    subjects: list[Term] = Field(default_factory=list)
    fields_of_research: list[Term] = Field(default_factory=list)
    entity_scope: list[Term] = Field(default_factory=list)
    """What kind of thing the values name (§5.2). Separates a vocabulary covering the right
    subject from one covering the right subject *and* the right kind of value. Empty at v0.1:
    filling it needs the registry's own term lists, and the §5.3 rule that reads it is
    specified to be skipped, not scored zero, when it is empty."""

    files: list[FileEntry] = Field(default_factory=list)
    """Empty for a pre-collection profile — there are no files yet, and that is not a fault."""
    columns: list[ColumnProfile] = Field(default_factory=list)
    measured_variables: list[MeasuredVariable] = Field(default_factory=list)

    missing_value_codes: list[str] = Field(default_factory=list)
    """How absence is to be recorded across the dataset — `NA`, `-999`, the empty string.

    Dataset-level because that is where Table Schema declares it. R5 names missing value codes
    among the elements that "cannot be inferred and require direct researcher input", so having
    them at all is a fact worth recording; a dataset that has not decided is a dataset whose
    missingness will be inconsistent."""

    target_repository: str | None = None
    formats_found: list[str] = Field(default_factory=list)
    """Distinct formats across `files`, for the R3.3 search. Derived, but recorded rather than
    recomputed so the query that ran can be reconstructed from the profile alone."""

    formats_planned: list[str] = Field(default_factory=list)
    """Formats the researcher intends to write, where no file exists yet (§8).

    Deliberately not merged into `formats_found`. R3.3 answers the two differently — an open
    alternative to a format already in use, against a choice not yet made — and an abstention
    has to be able to say which it was looking at."""
