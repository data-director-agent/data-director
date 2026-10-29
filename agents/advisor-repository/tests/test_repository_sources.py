"""Reading re3data and FAIRsharing: the record parsers, the live routes over a mocked transport,
the committed snapshots and the factory."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from dd_agent_advisor_repository import assess, factory
from dd_agent_advisor_repository.classes import Affiliation, Answer
from dd_agent_advisor_repository.explain import AnthropicExplainer, TemplateExplainer
from dd_agent_advisor_repository.live import FairsharingLive, Re3dataLive
from dd_agent_advisor_repository.records import from_fairsharing_json, from_re3data_xml
from dd_agent_advisor_repository.retrieve import Query, RegistryUnavailable
from dd_agent_advisor_repository.snapshot import (
    FAIRSHARING_SNAPSHOT,
    RE3DATA_SNAPSHOT,
    FairsharingSnapshot,
    Re3dataSnapshot,
)
from dd_sdk.credentials import ConfigError
from dd_sdk.evidence import DOCUMENT_CANONICALISATION, content_hash

DATA = Path(__file__).with_name("data")
UKDS_XML = (DATA / "r3d100010230.xml").read_bytes()
ORDA_XML = (DATA / "r3d100012124.xml").read_bytes()
SEARCH_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<list>
  <repository><id>r3d100012124</id><name>ORDA</name></repository>
  <repository><id>r3d100010230</id><name>UK Data Service</name></repository>
</list>"""
FAIRSHARING_JSON = {
    "id": "2502",
    "name": "UK Data Service",
    "registry": "Database",
    "type": "repository",
    "metadata": {
        "doi": "10.25504/FAIRsharing.1ky0cs",
        "name": "UK Data Service",
        "abbreviation": "UKDS",
        "status": "ready",
        "data_access_condition": {"type": "partially open", "notes": "Open or controlled."},
        "data_deposition_condition": {"type": "open", "notes": "Mainly for ESRC researchers."},
        "data_curation": {"type": "manual"},
        "data_access_for_pre_publication_review": "not found",
        "cross_references": [{"portal": "re3data", "name": "re3data:r3d100010230"}],
    },
    "tags": {"subjects": [{"label": "Economics"}, {"label": "Demographics"}]},
}


# --- parsers ----------------------------------------------------------------------------------


def test_a_re3data_record_keeps_the_phase_3_facts() -> None:
    record = from_re3data_xml(UKDS_XML)
    assert record is not None
    assert (record.re3data_id, record.name) == ("r3d100010230", "UK Data Service")
    assert record.pid_systems == ["DOI"]
    assert record.data_access_types == ["embargoed", "restricted"]
    assert "feeRequired" in record.data_access_restrictions
    assert record.data_upload_restrictions == ["registration"]
    assert record.fairsharing_id == "FAIRsharing.1ky0cs"
    assert "DDI - Data Documentation Initiative" in record.metadata_standards
    assert assess.assigns_pids(record) == Answer.YES
    assert assess.commercial(record) == Answer.NO
    assert assess.fee_required(record) == Answer.UNSTATED


def test_a_commercial_supplier_is_not_an_operator_and_ror_identifies_the_institution() -> None:
    record = from_re3data_xml(ORDA_XML)
    assert record is not None
    figshare = next(i for i in record.institutions if i.name == "figshare")
    assert (figshare.type, figshare.responsibilities) == ("commercial", ["technical"])
    assert assess.commercial(record) == Answer.NO
    home = assess.affiliated(record, Affiliation(name="x", ror="https://ror.org/05krs5044"))
    assert home is not None and home.name == "University of Sheffield"
    assert assess.affiliated(record, Affiliation(name="University of Leeds")) is None


def test_the_record_hash_does_not_depend_on_the_order_a_source_lists_things() -> None:
    record = from_re3data_xml(UKDS_XML)
    assert record is not None
    shuffled = record.model_validate(
        {**record.document(), "keywords": list(reversed(record.keywords))}
    )
    assert shuffled.content_hash() == record.content_hash()
    assert record.content_hash() == content_hash(record.document(), DOCUMENT_CANONICALISATION)


def test_an_unknown_re3data_identifier_is_no_record() -> None:
    empty = b'<r3d:re3data xmlns:r3d="http://www.re3data.org/schema/2-2"/>'
    assert from_re3data_xml(empty) is None


def test_a_fairsharing_database_record_keeps_its_conditions() -> None:
    record = from_fairsharing_json(FAIRSHARING_JSON)
    assert record is not None
    assert record.fairsharing_id == "FAIRsharing.1ky0cs"
    assert record.deposition_notes == "Mainly for ESRC researchers."
    assert record.re3data_ids == ["r3d100010230"]
    assert record.subjects == ["Demographics", "Economics"]
    assert from_fairsharing_json({"name": "no DOI"}) is None


# --- live routes ------------------------------------------------------------------------------


def _client(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=handler)


def _re3data(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/api/beta/repositories":
        return httpx.Response(200, content=SEARCH_XML)
    rid = request.url.path.rsplit("/", 1)[-1]
    body = {"r3d100010230": UKDS_XML, "r3d100012124": ORDA_XML}.get(rid)
    return httpx.Response(200, content=body) if body else httpx.Response(404)


def test_live_re3data_search_fetches_each_hit_in_registry_order() -> None:
    live = Re3dataLive(_client(httpx.MockTransport(_re3data)))
    hits = live.search(Query(text="social", limit=2))
    assert [h.record.re3data_id for h in hits] == ["r3d100012124", "r3d100010230"]
    assert hits[0].lexical_score > hits[1].lexical_score
    assert live.find("ukds") is not None  # an additional name
    assert live.find("UK Data") is None  # no partial matches
    assert live.fetch("r3d100099999") is None


def test_a_failing_live_route_raises_registry_unavailable() -> None:
    down = Re3dataLive(_client(httpx.MockTransport(lambda r: httpx.Response(503))))
    with pytest.raises(RegistryUnavailable):
        down.search(Query(text="social"))

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(RegistryUnavailable):
        FairsharingLive(_client(httpx.MockTransport(refuse))).fetch("FAIRsharing.1ky0cs")


def test_live_fairsharing_fetch_reads_the_public_record_route() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["accept"] == "application/json"
        if request.url.path == "/FAIRsharing.1ky0cs":
            return httpx.Response(200, json=FAIRSHARING_JSON)
        return httpx.Response(200, text="<html></html>", headers={"content-type": "text/html"})

    live = FairsharingLive(_client(httpx.MockTransport(handler)))
    record = live.fetch("FAIRsharing.1ky0cs")
    assert record is not None and record.name == "UK Data Service"
    assert live.fetch("FAIRsharing.unknown") is None


# --- snapshots --------------------------------------------------------------------------------


def test_the_committed_snapshots_match_their_manifests_and_hold_every_cross_reference() -> None:
    import hashlib

    for path in (RE3DATA_SNAPSHOT, FAIRSHARING_SNAPSHOT):
        manifest = json.loads(path.with_name("manifest.json").read_text(encoding="utf-8"))
        assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest["sha256"]
        assert manifest["missing"] == []
    repositories = Re3dataSnapshot()
    databases = FairsharingSnapshot()
    # re3data's cross-reference is followed as stated. It need not be returned: re3data's CEDA
    # Archive names FAIRsharing's record of the CEDA centre, which names another re3data entry.
    for record in repositories.records:
        if record.fairsharing_id:
            assert databases.fetch(record.fairsharing_id) is not None


def test_snapshot_search_and_exact_name_lookup() -> None:
    snapshot = Re3dataSnapshot()
    assert snapshot.snapshot_ref().label.startswith("re3data:snapshot:")
    top = snapshot.search(Query(text="social survey"))[0]
    assert top.lexical_score > 0
    assert snapshot.find("uk data service") is not None
    assert snapshot.find("UK Data") is None
    assert snapshot.search(Query(text="the of and")) == []


def test_a_missing_snapshot_is_registry_unavailable(tmp_path: Path) -> None:
    with pytest.raises(RegistryUnavailable):
        Re3dataSnapshot(tmp_path / "absent.jsonl").fetch("r3d100010230")


# --- the factory ------------------------------------------------------------------------------


def test_the_factory_defaults_to_the_snapshots_and_a_template() -> None:
    agent = factory.build({})
    assert isinstance(agent.repositories, Re3dataSnapshot)
    assert isinstance(agent.explainer, TemplateExplainer)
    assert agent.spec.models == ()


def test_live_retrieval_keeps_the_snapshots_as_fallback() -> None:
    agent = factory.build({"DD_REPOSITORY_RETRIEVAL": "live"})
    assert isinstance(agent.repositories, Re3dataLive)
    assert isinstance(agent.fallback, Re3dataSnapshot)
    assert isinstance(agent.databases_fallback, FairsharingSnapshot)


def test_the_model_explainer_is_declared_on_the_spec() -> None:
    agent = factory.build({"DD_REPOSITORY_EXPLAINER": "anthropic", "ANTHROPIC_API_KEY": "sk-test"})
    assert isinstance(agent.explainer, AnthropicExplainer)
    assert [m.provider for m in agent.spec.models] == ["anthropic"]


@pytest.mark.parametrize(
    "env",
    [{"DD_REPOSITORY_RETRIEVAL": "web"}, {"DD_REPOSITORY_EXPLAINER": "oracle"}],
)
def test_an_unknown_setting_is_a_configuration_error(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError):
        factory.build(env)
