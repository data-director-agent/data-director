"""ROR: the registry built from a pinned dump, the live route, and how a funder's name is
resolved."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from ror_fixture import FIXTURE, INACTIVE, NERC, NERC_JO, NERC_SD, UKRI, build_fixture

from dd_agent_advisor_policy import ror
from dd_agent_advisor_policy.classes import Actor, ActorRole
from dd_agent_advisor_policy.resolve import Ambiguous, Resolved, Unknown, names, resolve
from dd_sdk.registry import RegistryUnavailable

API_RECORD = Path(__file__).with_name("data") / "ror-02b5d8509.api.json"


@pytest.fixture(scope="module")
def dump(tmp_path_factory: pytest.TempPathFactory) -> ror.RorDump:
    return build_fixture(tmp_path_factory.mktemp("ror"))


def funder(name: str, ror_id: str | None = None) -> Actor:
    return Actor(role=ActorRole.FUNDER, name=name, ror_id=ror_id)


# --- the built registry -----------------------------------------------------------------------


def test_the_build_is_deterministic_and_keeps_only_what_identifies(tmp_path: Path) -> None:
    first, second = ror.build(FIXTURE), ror.build(FIXTURE)
    assert first == second
    lines = [json.loads(line) for line in first.decode().splitlines()]
    assert [d["id"] for d in lines] == sorted(d["id"] for d in lines)
    assert set(lines[0]) == set(ror.Organisation.model_fields)
    # Each line is the document as hashed: re-serialising it gives the same bytes.
    for raw, doc in zip(first.decode().splitlines(), lines, strict=True):
        assert json.dumps(doc, sort_keys=True, ensure_ascii=False) == raw


def test_a_built_registry_matches_its_pin_and_a_changed_one_does_not(tmp_path: Path) -> None:
    dump = build_fixture(tmp_path)
    assert ror.problem(dump.path, dump.manifest) is None
    assert dump.snapshot_ref().label == "ror:dump:v2.15"
    dump.path.write_bytes(dump.path.read_bytes() + b"\n")
    assert ror.problem(dump.path, dump.manifest) is not None
    dump.path.unlink()
    assert ror.problem(dump.path, dump.manifest) is not None


def test_an_unbuilt_registry_is_unavailable_not_empty(tmp_path: Path) -> None:
    dump = ror.RorDump(tmp_path / "registry.jsonl", tmp_path / "manifest.json")
    with pytest.raises(RegistryUnavailable):
        dump.find("NERC")


def test_fetch_builds_from_the_cached_pinned_dump(tmp_path: Path) -> None:
    cache = tmp_path / "archives"
    cache.mkdir()
    (cache / "v2.15-2026-10-20-ror-data.zip").write_bytes(FIXTURE.read_bytes())
    (tmp_path / "pinned").mkdir()
    built = build_fixture(tmp_path / "pinned")
    registry = tmp_path / "registry.jsonl"
    report = ror.fetch(cache_dir=cache, registry=registry, manifest=built.manifest)
    assert report.downloaded and not report.pinned
    assert (
        hashlib.sha256(registry.read_bytes()).hexdigest()
        == ror.Pin.load(built.manifest).snapshot_sha256
    )


def test_the_pinned_dump_is_declared_as_a_built_source() -> None:
    from dd_agent_advisor_policy.ror_source import SOURCE

    assert SOURCE.name == "ror"
    assert SOURCE.pin() == ror.Pin.load().archive_sha256


def test_the_committed_pin_names_its_licence_and_citation() -> None:
    pin = ror.Pin.load()
    assert pin.label.startswith("ror:dump:v")
    assert "CC0" in pin.licence
    assert pin.doi.startswith("https://doi.org/10.5281/zenodo.")


# --- finding an organisation ------------------------------------------------------------------


def test_a_name_acronym_or_alias_is_found_whatever_its_case(dump: ror.RorDump) -> None:
    assert [o.id for o in dump.find("Natural Environment Research Council")] == [NERC]
    assert [o.id for o in dump.find("  natural   ENVIRONMENT research council ")] == [NERC]
    assert {o.id for o in dump.find("nerc")} == {NERC, NERC_JO, NERC_SD}
    assert [o.id for o in dump.find("National Energy Research Centre")] == [NERC_SD]
    assert dump.find("Natural Environment") == []


def test_an_inactive_organisation_is_not_found_by_name_but_is_by_identifier(
    dump: ror.RorDump,
) -> None:
    org = dump.get(INACTIVE)
    assert org is not None and not org.active
    assert dump.find(org.names[0].value) == []


def test_an_organisation_is_read_by_identifier_in_either_form(dump: ror.RorDump) -> None:
    org = dump.get("02b5d8509")
    assert org is not None and org == dump.get(NERC)
    assert org.crossref_funder_preferred == "501100000270"
    assert UKRI in org.parents
    assert dump.get("0abcdef12") is None
    assert dump.get("not an identifier") is None


def _live(handler: Any) -> ror.RorLive:
    return ror.RorLive(client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_the_live_route_gives_the_same_organisation_as_the_dump(dump: ror.RorDump) -> None:
    item = json.loads(API_RECORD.read_text(encoding="utf-8"))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/02b5d8509"):
            return httpx.Response(200, json=item)
        assert request.url.params["query"] == "NERC"
        # The API's search is fuzzy; only exact names are kept.
        near = {**item, "id": "https://ror.org/0aaaaaa11", "names": [{"value": "NERCC"}]}
        return httpx.Response(200, json={"items": [item, near]})

    live = _live(handler)
    assert live.get("https://ror.org/02b5d8509") == dump.get(NERC)
    assert [o.id for o in live.find("NERC")] == [NERC]
    assert live.snapshot_ref().label.startswith("ror:live:")


def test_a_live_failure_is_unavailable_and_an_unknown_identifier_is_none() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(RegistryUnavailable):
        _live(down).find("NERC")
    assert _live(lambda r: httpx.Response(404)).get("0abcdef12") is None
    with pytest.raises(RegistryUnavailable):
        _live(lambda r: httpx.Response(500)).find("NERC")


# --- resolving a funder ------------------------------------------------------------------------


def test_one_organisation_resolves_and_is_searched_by_each_of_its_names(
    dump: ror.RorDump,
) -> None:
    actor = funder("Natural Environment Research Council")
    found = resolve(actor, dump)
    assert isinstance(found, Resolved) and found.organisation.id == NERC
    assert names(actor, found)[0] == actor.name
    assert "NERC" in names(actor, found)


def test_an_ambiguous_name_is_not_guessed_and_funders_rank_first(dump: ror.RorDump) -> None:
    found = resolve(funder("NERC"), dump)
    assert isinstance(found, Ambiguous)
    assert found.candidates[0].id == NERC
    assert {o.id for o in found.candidates} == {NERC, NERC_JO, NERC_SD}
    assert names(funder("NERC"), found) == ["NERC"]


def test_a_given_ror_identifier_settles_an_ambiguous_name(dump: ror.RorDump) -> None:
    found = resolve(funder("NERC", ror_id="02b5d8509"), dump)
    assert isinstance(found, Resolved) and found.organisation.id == NERC


def test_a_parent_and_child_name_resolves_through_rors_relationships(dump: ror.RorDump) -> None:
    found = resolve(funder("UKRI-NERC"), dump)
    assert isinstance(found, Resolved) and found.organisation.id == NERC


def test_an_unknown_name_and_a_non_funder_are_not_resolved(dump: ror.RorDump) -> None:
    assert isinstance(resolve(funder("Ministry of Nowhere"), dump), Unknown)
    journal = Actor(role=ActorRole.JOURNAL, name="NERC")
    assert isinstance(resolve(journal, dump), Unknown)
