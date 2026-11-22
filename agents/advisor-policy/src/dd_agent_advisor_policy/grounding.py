"""How the agent cites what it retrieved: a grounding reference for each record, and the evidence
item it rests on, hashed whole under `dd-json-document-v1` (docs/specs/grounding.md)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from dd_agent_advisor_policy.retrieve import SourceRecord
from dd_mcp_pid.ror_records import Organisation
from dd_sdk.contract.models import EvidenceItem, GroundingRef
from dd_sdk.evidence import DOCUMENT_CANONICALISATION, HASH_ALGORITHM, content_hash
from dd_sdk.registry import SnapshotRef

FAIRSHARING = "FAIRsharing"


def record_ref(record: SourceRecord) -> GroundingRef:
    return GroundingRef(source_id=record.source_id, content_hash=record.content_hash())


def organisation_hash(org: Organisation) -> str:
    return content_hash(org.document(), DOCUMENT_CANONICALISATION)


def org_ref(org: Organisation) -> GroundingRef:
    return GroundingRef(source_id=org.id, content_hash=organisation_hash(org))


def record_evidence(
    records: dict[str, SourceRecord],
    labels: dict[str, str],
    fairsharing: Callable[[str], SnapshotRef] | None = None,
) -> list[EvidenceItem]:
    """One evidence item per record, under the `snapshot_ref` of the registry it came from. A
    FAIRsharing record's own copy, when `fairsharing` says it (the live route or its local
    cache), also gives the time FAIRsharing last sent or confirmed it."""
    now = datetime.now(UTC)
    out: list[EvidenceItem] = []
    for sid, record in sorted(records.items()):
        ref = fairsharing(sid) if fairsharing and record.registry == FAIRSHARING else None
        out.append(
            EvidenceItem(
                source_id=sid,
                source_uri=record.source_uri,
                retrieved_at=(ref.retrieved_at if ref else None) or now,
                snapshot_ref=(ref.as_string() if ref else labels.get(record.registry)) or None,
                hash_algorithm=HASH_ALGORITHM,
                canonicalisation=DOCUMENT_CANONICALISATION,
                content_hash=record.content_hash(),
                content=record.document(),
            )
        )
    return out


def org_evidence(organisations: dict[str, Organisation], snapshot_ref: str) -> list[EvidenceItem]:
    """One evidence item per ROR record."""
    now = datetime.now(UTC)
    return [
        EvidenceItem(
            source_id=oid,
            source_uri=oid,
            retrieved_at=now,
            snapshot_ref=snapshot_ref,
            hash_algorithm=HASH_ALGORITHM,
            canonicalisation=DOCUMENT_CANONICALISATION,
            content_hash=organisation_hash(org),
            content=org.document(),
        )
        for oid, org in sorted(organisations.items())
    ]
