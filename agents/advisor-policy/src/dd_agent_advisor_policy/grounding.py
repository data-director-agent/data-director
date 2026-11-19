"""How the agent cites what it retrieved: a grounding reference for each record, and the evidence
item it rests on, hashed whole under `dd-json-document-v1` (docs/specs/grounding.md)."""

from __future__ import annotations

from datetime import UTC, datetime

from dd_agent_advisor_policy.retrieve import SourceRecord
from dd_agent_advisor_policy.ror_records import Organisation
from dd_sdk.contract.models import EvidenceItem, GroundingRef
from dd_sdk.evidence import DOCUMENT_CANONICALISATION, HASH_ALGORITHM, content_hash


def record_ref(record: SourceRecord) -> GroundingRef:
    return GroundingRef(source_id=record.source_id, content_hash=record.content_hash())


def organisation_hash(org: Organisation) -> str:
    return content_hash(org.document(), DOCUMENT_CANONICALISATION)


def org_ref(org: Organisation) -> GroundingRef:
    return GroundingRef(source_id=org.id, content_hash=organisation_hash(org))


def record_evidence(records: dict[str, SourceRecord], labels: dict[str, str]) -> list[EvidenceItem]:
    """One evidence item per record, under the `snapshot_ref` of the registry it came from."""
    now = datetime.now(UTC)
    return [
        EvidenceItem(
            source_id=sid,
            source_uri=record.source_uri,
            retrieved_at=now,
            snapshot_ref=labels.get(record.registry) or None,
            hash_algorithm=HASH_ALGORITHM,
            canonicalisation=DOCUMENT_CANONICALISATION,
            content_hash=record.content_hash(),
            content=record.document(),
        )
        for sid, record in sorted(records.items())
    ]


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
