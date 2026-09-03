"""Shared vocabulary for every document in §6.

`Derivation` and `Term` are the two load-bearing types here. §6.1 requires that everything
inferred records *how it was arrived at*, and §6.1 says plainly why: it is what lets a later
test harness tell a profiling mistake from a ranking mistake. There are exactly two ways to
carry that in this codebase — a `Term`, or a sibling `*_derivation` field — and no third.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Frozen(BaseModel):
    """Base for every document type: immutable, and rejects unknown fields.

    `extra="forbid"` matters more than it looks. These models are the published contract of
    §6, and silently swallowing a misspelled field is how a schema stops meaning anything.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


class Derivation(StrEnum):
    """How a statement in a profile was arrived at."""

    SUPPLIED_METADATA = "supplied_metadata"
    """Came with the dataset. Not inferred at all."""

    FILE_EXTENSION = "file_extension"
    """Format guessed from the filename. Weakest of the format signals."""

    FILE_MAGIC = "file_magic"
    """Format read from the leading bytes of the file. Beats the extension."""

    LOCAL_PARSE = "local_parse"
    """Derived by parsing file content locally, with no model involved (§5.1 tier 1)."""

    MODEL_FROM_REGISTRY_LIST = "model_from_registry_list"
    """A model chose from a fixed list fetched from the registry (§5.1 tier 2)."""

    MODEL_INFERRED = "model_inferred"
    """A model wrote this from free text (§5.1 tier 3). Widens a search; always flagged."""


class StageName(StrEnum):
    """The six pipeline stages, in order. §6.3 writes one PROV activity per member."""

    PROFILE = "profile"
    RETRIEVE = "retrieve"
    RANK = "rank"
    EXPLAIN = "explain"
    CHECK = "check"
    ASSEMBLE = "assemble"


class StageStatus(StrEnum):
    OK = "ok"
    EMPTY = "empty"
    """Ran correctly and produced nothing. Not a failure — see §5.5."""
    DEGRADED = "degraded"
    """Produced a result, but something was unavailable or skipped. Recorded, not raised."""
    NOT_IMPLEMENTED = "not_implemented"
    """A v0.1 stub. Explicit in the run record rather than indistinguishable from `empty`."""


class RecommendationKind(StrEnum):
    """The four kinds of recommendation R3 owes, one per §5.2 search.

    This enum is the mechanism for R3.6. `nodes/assemble.py` iterates it and writes a
    `NothingFound` for every member with no surviving recommendation, and nothing else in the
    codebase constructs a `NothingFound`. A fifth kind therefore cannot be added without its
    abstention path appearing automatically.

    The first two members are separate for the reason R3 demands: concept linkage pins a
    column's *values* to identifiers, ontology alignment maps the dataset's *structure* onto
    classes and properties (§2.1).
    """

    CONTROLLED_VOCABULARY_LINKAGE = "controlled_vocabulary_linkage"  # R3.1
    ONTOLOGY_ALIGNMENT = "ontology_alignment"  # R3.2
    OPEN_FORMAT = "open_format"  # R3.3
    FIELD_LEVEL_STANDARD = "field_level_standard"  # R3.4


class TermList(StrEnum):
    """The registry's own controlled lists.

    Members name lists to *fetch*, never terms to use. R3.5 forbids a built-in list of
    standards, and that includes the facets used to search for them.
    """

    SUBJECT = "subject"
    DOMAIN = "domain"
    RECORD_TYPE = "record_type"


class Term(Frozen):
    """A controlled term, with the list it came from and how it got here."""

    term: str
    list_name: str | None = None
    """The registry list this term belongs to, or `None` for a term from supplied metadata."""
    list_version: str | None = None
    derivation: Derivation


class AgentRef(Frozen):
    """Agent identity, written into every run record (C13)."""

    identity: str
    version: str


class RegistrySnapshotRef(Frozen):
    """Which copy of the registry answered (§7.3).

    `stale` and `version` appear in the output document, not only in a log, because §7.3
    requires the date be visible in the interface.
    """

    version: str
    source: str
    stale: bool
    retrieved_at: str | None = None


class PromptRef(Frozen):
    """Which prompt, at which version, with which content (§5.4).

    Not in §6.2's sketch. Added because §5.4 requires the prompt version be recorded with each
    run, and a version string without a hash does not survive someone editing the file.
    """

    name: str
    version: str
    sha256: str


class RankingConfigRef(Frozen):
    """Which ranking weights were in force (§5.3)."""

    version: str
    sha256: str


class ScoreComponent(Frozen):
    """One attributed contribution to a candidate's score.

    Not in §6.2's sketch, which has only a flat `score_features` map. §5.3 requires that a
    model's contribution be recorded as *its own named component*, "not folded invisibly into
    a rule's output" — and a `{name: value}` map cannot say whether `subject_overlap: 0.9` came
    from a rule or from the model. Both are kept: `score_features` for readability,
    `score_components` for attribution.
    """

    name: str
    source: str = Field(pattern="^(rule|model)$")
    raw: float
    weight: float
    contribution: float
    note: str | None = None
    """Why a model contributed this, or why a rule was skipped."""


class StageReport(Frozen):
    """What one stage did. Appended to state by every node; the basis of §6.3."""

    stage: StageName
    status: StageStatus
    started_at: str
    ended_at: str
    counts: dict[str, int] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    prompts: list[PromptRef] = Field(default_factory=list)
    model_id: str | None = None
    model_params: dict[str, str] = Field(default_factory=dict)
    """Parameters **actually sent**, stringified. Not the ones requested."""


class StageFailure(Frozen):
    """A content-level problem, recorded as data rather than raised (see `errors`)."""

    stage: StageName
    kind: str
    detail: str
    at: str
