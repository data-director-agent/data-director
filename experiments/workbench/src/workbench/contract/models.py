"""Pydantic mirrors of the LinkML classes in schema/data_director.yaml.

The LinkML source is the contract; these models are how Python code constructs and reads
documents that conform to it. A test asserts that instances of every model here validate
against the generated JSON Schema, so the two cannot drift silently. Field names and enum
values are identical to the LinkML slot and permissible-value names on purpose.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

UUID7_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def new_invocation_id() -> str:
    """UUIDv7 (RFC 9562), from the standard library. ADR-0004."""
    return str(uuid.uuid7())


def now() -> datetime:
    return datetime.now(UTC)


# --- Enumerations ---------------------------------------------------------------------------


class OutcomeStatus(StrEnum):
    SUCCEEDED = "succeeded"
    ABSTAINED = "abstained"
    REFERRED = "referred"
    FAILED = "failed"
    SUSPENDED = "suspended"


class ReasonCode(StrEnum):
    # abstained
    NO_QUALIFYING_RESOURCE = "no_qualifying_resource"
    NO_CANDIDATES_RETRIEVED = "no_candidates_retrieved"
    REGISTRY_UNAVAILABLE = "registry_unavailable"
    NOT_APPLICABLE = "not_applicable"
    INSUFFICIENT_INPUT = "insufficient_input"
    CAPABILITY_NOT_IMPLEMENTED = "capability_not_implemented"
    # referred
    REQUIRES_HUMAN_JUDGEMENT = "requires_human_judgement"
    POLICY_REQUIRES_APPROVAL = "policy_requires_approval"
    OUTSIDE_AGENT_SCOPE = "outside_agent_scope"


class RecommendationKind(StrEnum):
    CONTROLLED_VOCABULARY = "controlled_vocabulary"
    ONTOLOGY = "ontology"
    TERMINOLOGY_UNCLASSIFIED = "terminology_unclassified"
    DATA_FORMAT = "data_format"
    FIELD_FORMAT = "field_format"


class Derivation(StrEnum):
    TEMPLATE = "template"
    MODEL = "model"
    LEXICAL = "lexical"
    REGISTRY = "registry"


class EnergyMethod(StrEnum):
    NOT_MEASURED = "not_measured"
    ESTIMATED = "estimated"
    MEASURED = "measured"


# --- Input ------------------------------------------------------------------------------------


class TableField(Frozen):
    name: str
    field_type: str | None = None
    field_format: str | None = None
    field_description: str | None = None


class DatasetProfile(Frozen):
    title: str | None = None
    description: str | None = None
    keywords: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    media_types: list[str] = Field(default_factory=list)
    fields: list[TableField] = Field(default_factory=list)


class InvocationRequest(Frozen):
    invocation_id: str = Field(default_factory=new_invocation_id, pattern=UUID7_PATTERN)
    agent_id: str
    requirement_ids: list[str] = Field(default_factory=list)
    issued_at: datetime = Field(default_factory=now)
    policy_bundle_ref: str
    input: DatasetProfile


# --- Outcome and problems -------------------------------------------------------------------


class Outcome(Frozen):
    status: OutcomeStatus
    reason_code: ReasonCode | None = None
    referred_to: str | None = None
    statement: str


class ProblemDetails(Frozen):
    type: str
    title: str | None = None
    http_status: int | None = None
    detail: str | None = None
    instance: str | None = None
    resume_condition: str | None = None
    resume_after: datetime | None = None


# --- R3 payload -----------------------------------------------------------------------------


class ResourceRef(Frozen):
    fairsharing_id: str
    doi: str | None = None
    name: str | None = None
    url: str | None = None
    record_type: str | None = None
    status: str | None = None


class Recommendation(Frozen):
    kind: RecommendationKind
    target: str
    resource: ResourceRef
    score: float | None = None
    rationale: str
    rationale_derivation: Derivation
    classification_derivation: Derivation | None = None
    evidence_hashes: list[str] = Field(default_factory=list)


class SearchedSummary(Frozen):
    queries: list[str] = Field(default_factory=list)
    snapshot_ref: str | None = None
    candidates_retrieved: int | None = None
    candidates_qualifying: int | None = None


class Recommendations(Frozen):
    items: list[Recommendation] = Field(default_factory=list)
    searched: SearchedSummary | None = None


# --- Evidence and telemetry -----------------------------------------------------------------


class EvidenceItem(Frozen):
    source_id: str
    source_uri: str | None = None
    retrieved_at: datetime | None = None
    snapshot_ref: str | None = None
    hash_algorithm: str = "sha256"
    canonicalisation: str
    content_hash: str = Field(pattern=SHA256_PATTERN)


class Telemetry(Frozen):
    trace_id: str | None = None
    model_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    energy_estimate_j: float | None = None
    energy_method: EnergyMethod = EnergyMethod.NOT_MEASURED


# --- Envelope -------------------------------------------------------------------------------


class Envelope(Frozen):
    invocation_id: str = Field(pattern=UUID7_PATTERN)
    agent_id: str
    agent_version: str
    completed_at: datetime
    outcome: Outcome
    payload: Recommendations | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)
    telemetry: Telemetry
    requires_human_review: Literal[True] = True
    problem: ProblemDetails | None = None

    def to_document(self) -> dict[str, Any]:
        """JSON-ready dict in the shape the generated schema validates.

        Optional slots are omitted rather than emitted as null (enum-ranged slots are not
        nullable in the generated schema). The one exception is `energy_estimate_j`, which is
        written as an explicit null: P14 asks for the footprint to be captured, and an explicit
        null says "slot exists, not measured" where an absent key says nothing.
        """
        doc = to_document(self)
        doc["telemetry"].setdefault("energy_estimate_j", None)
        return doc


def to_document(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json", exclude_none=True)
