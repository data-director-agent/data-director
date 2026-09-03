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


class LifecyclePhase(StrEnum):
    """Which of the Blueprint's researcher entry points a run serves (§8).

    The Blueprint's §8.2 process flow has three entry points into six phases. Only the first two
    concern R3, and they differ in one way that reaches every stage: whether the data exists yet.
    `PRE_COLLECTION` is Figure 1's "workflow entry point for researchers starting a new project
    before data collection begins" — there are no files to profile, so the profile is built from
    the README and draft data dictionary R5 has produced, and the facets §5.2 searches on have to
    be asked for rather than inferred.
    """

    PRE_COLLECTION = "pre_collection"
    """Blueprint Phase 1. No data exists; a README and a draft data dictionary do."""

    COLLECTED = "collected"
    """Blueprint Phase 4 onwards, and the only thing that existed before §8: data files on disk."""


class Derivation(StrEnum):
    """How a statement in a profile was arrived at.

    Roughly ordered weakest to strongest, with one deliberate exception: `RESEARCHER_ANSWER` is
    the *strongest* signal here, not the weakest. It is the person who will collect the data
    saying what it is, which no amount of inference improves on — so it sits with the other
    non-inferred sources rather than with the model-assisted ones.
    """

    SUPPLIED_METADATA = "supplied_metadata"
    """Came with the dataset. Not inferred at all."""

    DECLARED_IN_DATA_DICTIONARY = "declared_in_data_dictionary"
    """Read from a data dictionary the researcher wrote (§8). Declared, not inferred.

    The counterpart of `LOCAL_PARSE` for a dataset that does not exist yet: where tier 1 parses
    values to find out what a column holds, this reads what the researcher has said it will hold.
    """

    RESEARCHER_ANSWER = "researcher_answer"
    """Answered by the researcher when asked (§8, the `elicit` stage).

    R5 names the elements that "cannot be inferred and require direct researcher input". Asking
    is the honest way to fill them, and an answer is evidence of intent rather than a guess about
    it — so this outranks every model-assisted derivation below.
    """

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
    """The seven pipeline stages, in order. §6.3 writes one PROV activity per member.

    Declaration order is the pipeline order, and three other places must agree with it:
    `graph.PIPELINE_ORDER`, `nodes.support.STAGE_ORDER` (which numbers the `stages/NN-*.json`
    files) and `provenance.prov`'s stage-to-entity mapping. `test_provenance` compares the
    manifest's stages against `list(StageName)`, so a stage that stops reporting fails there.
    """

    ELICIT = "elicit"
    """§8. Gathers the context §5.2 cannot infer when no data exists. Runs on every path and
    returns early outside pre-collection, so the graph keeps one unconditional line."""

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


class IntakeConfigRef(Frozen):
    """Which intake question set was in force (§8).

    A separate type from `RankingConfigRef` despite the identical shape. These are two
    independently versioned files, and a single shared `ConfigRef` would make it possible to
    write one into the other's field without anything noticing — the run record's whole job is
    to say precisely which of each was used (R10).
    """

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
