"""§6.1 — the dataset profile.

The profile is the only thing later stages search on, so a profiling mistake shows up as a
retrieval mistake unless the profile records how each of its own statements was arrived at
(§5.1). Every inferred field here therefore carries a `Derivation`, either inside a `Term` or
as a sibling `*_derivation` field.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from standards_advisor.models.common import Derivation, Frozen, Term


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


class ContentFingerprint(Frozen):
    """Identifies the input, so C17 caching can be added later without reworking run records."""

    algorithm: str = "sha256"
    digest: str
    total_bytes: int
    files_hashed: int


class SourceRef(Frozen):
    """Where the profile's inputs came from and when it was built."""

    kind: str
    """`local_files`, or a repository name once repository ingest exists."""
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
    """One column, as inferred locally from sampled values. R3.4 depends on this."""

    name: str
    position: int
    file: str
    inferred_type: ColumnType
    type_derivation: Derivation
    pattern: str | None = None
    """The concrete pattern that matched — e.g. `%d/%m/%Y`. Naming the format is the whole
    point for R3.4: 'it is a date' is not actionable, 'it is `%d/%m/%Y`, use ISO 8601' is."""
    unit: str | None = None
    """A unit read from the column name, e.g. `pct` from `organic_carbon_pct`."""
    sample_size: int
    blank_count: int
    blank_proportion: float
    distinct_count: int
    distinct_count_is_exact: bool
    """False whenever only the head was sampled — which is always. Recorded so a later rule
    cannot mistake a sample statistic for a population one."""
    example_values: list[str] = Field(default_factory=list)
    """Kept in the profile for human inspection of a run. **Never sent to a model** — §1.4
    permits only names, inferred types and counts to leave the machine."""


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

    title: str | None = None
    abstract: str | None = None
    keywords: list[str] = Field(default_factory=list)

    subjects: list[Term] = Field(default_factory=list)
    fields_of_research: list[Term] = Field(default_factory=list)
    entity_scope: list[Term] = Field(default_factory=list)
    """What kind of thing the values name (§5.2). Separates a vocabulary covering the right
    subject from one covering the right subject *and* the right kind of value. Empty at v0.1:
    filling it needs the registry's own term lists, and the §5.3 rule that reads it is
    specified to be skipped, not scored zero, when it is empty."""

    files: list[FileEntry] = Field(default_factory=list)
    columns: list[ColumnProfile] = Field(default_factory=list)
    measured_variables: list[MeasuredVariable] = Field(default_factory=list)

    target_repository: str | None = None
    formats_found: list[str] = Field(default_factory=list)
    """Distinct formats across `files`, for the R3.3 search. Derived, but recorded rather than
    recomputed so the query that ran can be reconstructed from the profile alone."""
