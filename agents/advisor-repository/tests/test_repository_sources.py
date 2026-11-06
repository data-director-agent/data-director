"""Reading re3data and FAIRsharing: the record parsers, the pinned re3data export, FAIRsharing's
live route over a mocked transport, its committed snapshot and the factory."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

import httpx
import pytest
from re3data_fixture import FIXTURE, build_fixture, session_registry

from dd_agent_advisor_repository import assess, factory, registry
from dd_agent_advisor_repository.classes import Affiliation, Answer
from dd_agent_advisor_repository.explain import AnthropicExplainer, TemplateExplainer
from dd_agent_advisor_repository.live import FairsharingLive
from dd_agent_advisor_repository.records import from_fairsharing_json, from_re3data_xml
from dd_agent_advisor_repository.retrieve import Query, RegistryUnavailable
from dd_agent_advisor_repository.snapshot import (
    FAIRSHARING_SNAPSHOT,
    FairsharingSnapshot,
    Re3dataRegistry,
)
from dd_sdk.credentials import ConfigError
from dd_sdk.evidence import DOCUMENT_CANONICALISATION, content_hash

DATA = Path(__file__).with_name("data")
UKDS_XML = (DATA / "r3d100010230.xml").read_bytes()
ORDA_XML = (DATA / "r3d100012124.xml").read_bytes()
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


@pytest.fixture(scope="session")
def re3data(tmp_path_factory: pytest.TempPathFactory) -> Re3dataRegistry:
    return session_registry(tmp_path_factory)


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
    assert "DDI (Data Documentation Initiative)" in record.metadata_standards
    assert record.doi == "https://doi.org/10.17616/R3230F"
    assert record.source_uri == record.doi
    assert "123 Social Sciences" in record.subjects
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
    empty = b'<r3d:re3data xmlns:r3d="http://www.re3data.org/schema/4-0"/>'
    assert from_re3data_xml(empty) is None


def test_a_record_drops_contact_details() -> None:
    record = from_re3data_xml(UKDS_XML)
    assert record is not None
    assert "@" not in json.dumps(record.document())


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


def test_a_failing_live_route_raises_registry_unavailable() -> None:
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


# --- the pinned re3data export ---------------------------------------------------------------


def test_the_registry_is_built_the_same_from_the_same_export() -> None:
    assert registry.build(FIXTURE) == registry.build(FIXTURE)


def test_a_built_registry_is_checked_against_its_pin(tmp_path: Path) -> None:
    built = build_fixture(tmp_path)
    assert registry.problem(built.path, built.manifest) is None
    built.path.write_bytes(built.path.read_bytes() + b"\n")
    found = registry.problem(built.path, built.manifest)
    assert found is not None and "dd-re3data fetch" in found
    with pytest.raises(RegistryUnavailable, match="does not match"):
        Re3dataRegistry(built.path, built.manifest).fetch("r3d100010230")


def test_an_unbuilt_registry_says_how_to_build_it(tmp_path: Path) -> None:
    build_fixture(tmp_path)
    with pytest.raises(RegistryUnavailable, match="uv run dd-re3data fetch"):
        Re3dataRegistry(tmp_path / "absent.jsonl", tmp_path / "manifest.json").fetch("r3d")


def test_registry_search_and_exact_name_lookup(re3data: Re3dataRegistry) -> None:
    assert re3data.snapshot_ref().label == "re3data:export:2026-11"
    top = re3data.search(Query(text="social survey"))[0]
    assert top.lexical_score > 0
    assert re3data.find("uk data service") is not None
    assert re3data.find("UK Data") is None
    assert re3data.search(Query(text="the of and")) == []
    eidc = re3data.fetch("r3d100010199")
    assert eidc is not None and eidc.certificates == ["CoreTrustSeal"]  # named in schema 4.0


def test_every_fairsharing_snapshot_record_matches_its_manifest(re3data: Re3dataRegistry) -> None:
    manifest = json.loads(FAIRSHARING_SNAPSHOT.with_name("manifest.json").read_text("utf-8"))
    assert hashlib.sha256(FAIRSHARING_SNAPSHOT.read_bytes()).hexdigest() == manifest["sha256"]
    databases = FairsharingSnapshot()
    # re3data's cross-reference is followed as stated. It need not be returned: re3data's CEDA
    # Archive names FAIRsharing's record of the CEDA centre, which names another re3data entry.
    missing = [
        r.fairsharing_id
        for r in re3data.records
        if r.fairsharing_id and databases.fetch(r.fairsharing_id) is None
    ]
    assert not missing, f"rebuild the FAIRsharing snapshot for {missing}"


def _serve(archive: bytes, seen: list[httpx.Request]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=archive)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_pins_a_month_then_builds_from_the_cache_without_asking_again(
    tmp_path: Path,
) -> None:
    seen: list[httpx.Request] = []
    archive = FIXTURE.read_bytes()
    built, manifest = tmp_path / "registry.jsonl", tmp_path / "manifest.json"
    fetch = partial(
        registry.fetch, cache_dir=tmp_path / "archives", registry=built, manifest=manifest
    )
    report = fetch(
        month="2026-11",
        update_pin=True,
        client=_serve(archive, seen),
        now=datetime(2026, 11, 3, tzinfo=UTC),
    )
    pin = registry.Pin.load(manifest)
    assert (report.pinned, pin.month, pin.records) == (True, "2026-11", report.records)
    assert pin.archive_sha256 == hashlib.sha256(archive).hexdigest()
    assert pin.citation == registry.CITATION
    assert [str(r.url) for r in seen] == [pin.archive]

    built.unlink()
    again = fetch(client=_serve(archive, seen))
    assert again.downloaded and len(seen) == 1  # built from the cached archive
    assert fetch(client=_serve(archive, seen)).downloaded is False


def test_an_archive_that_does_not_match_its_pin_is_refused(tmp_path: Path) -> None:
    build_fixture(tmp_path)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("100000001.xml", "<x/>")
    with pytest.raises(registry.RegistryError, match="not the pinned"):
        registry.fetch(
            cache_dir=tmp_path / "archives",
            registry=tmp_path / "absent.jsonl",
            manifest=tmp_path / "manifest.json",
            client=_serve(buffer.getvalue(), []),
        )


def test_downloads_name_the_project_not_a_person() -> None:
    agent = registry._user_agent()
    assert "github.com/data-director-agent/data-director" in agent
    assert "@" not in agent


# --- the factory ------------------------------------------------------------------------------


def test_the_factory_reads_the_pinned_registry_and_defaults_to_a_template() -> None:
    agent = factory.build({})
    assert isinstance(agent.repositories, Re3dataRegistry)
    assert isinstance(agent.explainer, TemplateExplainer)
    assert agent.spec.models == ()


def test_live_retrieval_asks_fairsharing_and_keeps_its_snapshot_as_fallback() -> None:
    agent = factory.build({"DD_REPOSITORY_RETRIEVAL": "live"})
    assert isinstance(agent.repositories, Re3dataRegistry)
    assert isinstance(agent.databases, FairsharingLive)
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
