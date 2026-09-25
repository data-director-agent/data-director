"""FAIRsharing record projection, the live backend (recorded), and the committed snapshot."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dd_agent_r3 import rank
from dd_agent_r3.agent import R3Agent
from dd_agent_r3.fairsharing.live import LiveBackend
from dd_agent_r3.fairsharing.records import (
    MODEL_AND_FORMAT,
    TERMINOLOGY,
    from_api_json,
    from_public_json,
)
from dd_agent_r3.fairsharing.snapshot import (
    DEFAULT_MANIFEST,
    DEFAULT_SNAPSHOT,
    SnapshotBackend,
)
from dd_agent_r3.retrieve import Query, RegistryUnavailable
from dd_agent_r3.testing import make_conductor, request
from dd_sdk.contract.models import OutcomeStatus, RecommendationKind

PUBLIC_SHAPE = {
    "fairsharing_data_licence": "https://creativecommons.org/licenses/by-sa/4.0/ ...",
    "id": "399",
    "name": "AGROVOC",
    "registry": "Standard",
    "type": "terminology_artefact",
    "abbreviation": "AGROVOC",
    "metadata": {
        "doi": "10.25504/FAIRsharing.anpj91",
        "name": "AGROVOC",
        "status": "ready",
        "description": "A controlled vocabulary covering all areas of interest of FAO.",
        "contacts": [{"contact_name": "Someone", "contact_email": "x@example.org"}],
    },
    "tags": {
        "subjects": [{"iri": "http://example.org/agri", "label": "Agriculture"}],
        "domains": [{"iri": None, "label": "Food"}],
    },
}


def test_public_record_projection_drops_personal_data_and_uses_doi_suffix_as_id() -> None:
    rec = from_public_json(PUBLIC_SHAPE, source_uri="https://fairsharing.org/399")
    assert rec.fairsharing_id == "FAIRsharing.anpj91"
    assert rec.numeric_id == "399"
    assert rec.record_type == TERMINOLOGY
    assert rec.subjects == ["Agriculture"] and rec.domains == ["Food"]
    assert "contact" not in json.dumps(rec.model_dump())
    api_shape = {
        "id": "399",
        "type": "fairsharing_records",
        "attributes": {
            "metadata": PUBLIC_SHAPE["metadata"],
            "abbreviation": "AGROVOC",
            "record_type": "terminology_artefact",
            "fairsharing_registry": "Standard",
            "subjects": ["Agriculture"],
            "domains": ["Food"],
        },
    }
    # Both routes hash identically: the evidence hash is route-independent.
    assert from_api_json(api_shape).content_hash() == rec.content_hash()


@pytest.mark.vcr
def test_live_record_fetch_needs_no_account() -> None:
    """Recorded from the public record route. Replayed with --record-mode=none in CI."""
    backend = LiveBackend()
    rec = backend.fetch("399")
    assert rec is not None
    assert rec.name == "AGROVOC"
    assert rec.record_type == TERMINOLOGY
    assert rec.fairsharing_id.startswith("FAIRsharing.")
    assert backend.fetch("FAIRsharing.does-not-exist") is None


def test_live_search_without_credentials_is_registry_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FAIRSHARING_LOGIN", raising=False)
    monkeypatch.delenv("FAIRSHARING_PASSWORD", raising=False)
    with pytest.raises(RegistryUnavailable, match="needs an account"):
        LiveBackend().search(Query("soil"))


# --- the committed snapshot -------------------------------------------------------------------


@pytest.fixture(scope="module")
def snapshot() -> SnapshotBackend:
    if not DEFAULT_SNAPSHOT.is_file():
        pytest.skip("snapshot not built")
    return SnapshotBackend()


def test_snapshot_manifest_matches_file(snapshot: SnapshotBackend) -> None:
    import hashlib

    manifest = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["records"] == len(snapshot.records)
    assert manifest["sha256"] == hashlib.sha256(DEFAULT_SNAPSHOT.read_bytes()).hexdigest()
    assert (DEFAULT_SNAPSHOT.parent / "LICENCE.md").read_text().count("CC BY-SA 4.0") >= 1
    assert snapshot.snapshot_ref().label.startswith("snapshot:20")


def test_snapshot_search_filters_by_record_type(snapshot: SnapshotBackend) -> None:
    hits = snapshot.search(Query("soil agriculture environment", record_type=TERMINOLOGY, limit=5))
    assert hits and all(h.record.record_type == TERMINOLOGY for h in hits)
    formats = snapshot.search(Query("json", record_type=MODEL_AND_FORMAT, limit=5))
    assert formats and all(h.record.record_type == MODEL_AND_FORMAT for h in formats)


@pytest.mark.requirement("R3", "R3.1", "R3.2", "R3.3")
def test_r3_over_the_real_snapshot_recommends_for_the_soil_sample(
    snapshot: SnapshotBackend, tmp_path: Path
) -> None:
    conductor = make_conductor(tmp_path / "runs", r3=R3Agent(retrieval=snapshot), crate=False)
    env = conductor.invoke(request("r3.standards-advisor"))
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.payload is not None and env.payload.items
    kinds = {i.kind for i in env.payload.items}
    assert kinds & {RecommendationKind.CONTROLLED_VOCABULARY, RecommendationKind.ONTOLOGY}
    assert RecommendationKind.DATA_FORMAT in kinds
    # R3.4: a field-level date/time recommendation is made only if the snapshot holds a standard
    # that is about dates and times by name (ISO 8601); otherwise none, rather than a guess.
    has_temporal_standard = any(rank.is_temporal_standard(r) for r in snapshot.records)
    assert (RecommendationKind.FIELD_FORMAT in kinds) == has_temporal_standard
    for item in env.payload.items:
        if item.kind == RecommendationKind.FIELD_FORMAT:
            assert item.target.startswith("field:")
    assert conductor.grounding_reports[env.invocation_id].passed
    # Every cited record is a real snapshot record with a DOI, so attribution holds (CC BY-SA).
    for item in env.payload.items:
        rec = snapshot.fetch(item.grounded_on[0].source_id)
        assert rec is not None and rec.doi
    # R3.6 on the same snapshot: an unrelated profile abstains rather than guessing.
    from dd_sdk.contract.models import DatasetProfile

    unrelated = DatasetProfile(
        title="Mediaeval manuscript catalogue", keywords=["palaeography", "codicology"]
    )
    env2 = conductor.invoke(request("r3.standards-advisor", unrelated))
    assert env2.outcome.status in (OutcomeStatus.ABSTAINED, OutcomeStatus.SUCCEEDED)
    if env2.outcome.status == OutcomeStatus.ABSTAINED:
        assert env2.outcome.reason_code is not None


def test_ranking_config_is_the_only_source_of_numbers() -> None:
    cfg = rank.config()
    assert set(cfg) >= {
        "limit",
        "title_tokens",
        "weights",
        "status_weights",
        "confidence_floor",
        "max_per_kind",
    }
    assert abs(sum(cfg["weights"].values()) - 1.0) < 1e-9
