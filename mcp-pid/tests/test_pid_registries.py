"""Each registry's client, against recorded answers: what a record keeps, and how an unknown
identifier, a failing service and an unreadable answer are told apart."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from pid_support import (
    CROSSREF_DOI,
    DATACITE_DOI,
    NERC,
    ORCID_ID,
    built_registry,
    http,
)

from dd_mcp_pid.cli import SettingsError, contact, registries
from dd_mcp_pid.dois import MAX_CREATORS, Crossref, DataCite, bare_doi
from dd_mcp_pid.http import Http, UnavailableError, user_agent
from dd_mcp_pid.orcid import Orcid, checksum_ok, orcid_url
from dd_mcp_pid.ror import RorApi, RorIndex


def test_a_datacite_doi_is_cut_to_its_record() -> None:
    record = DataCite(http("DataCite")).get(DATACITE_DOI)
    assert record is not None
    assert record.doi == DATACITE_DOI
    assert record.agency == "DataCite"
    assert record.title == "Data Director Agentic AI Tool Blueprint"
    assert record.type == "Other"
    assert record.publisher == "Research Data Alliance"
    assert record.publication_year == "2026"
    assert record.creators[0] == "Clare, Connie"


def test_a_crossref_doi_is_cut_to_the_same_shape_with_its_creators_capped() -> None:
    record = Crossref(http("Crossref")).get(CROSSREF_DOI)
    assert record is not None
    assert record.agency == "Crossref"
    assert record.title is not None and record.title.startswith("The FAIR Guiding Principles")
    assert record.type == "journal-article"
    assert record.publication_year == "2016"
    assert record.creators[0] == "Wilkinson, Mark D."
    assert len(record.creators) == MAX_CREATORS


def test_no_record_holds_an_integer() -> None:
    def ints(value: object) -> bool:
        if isinstance(value, dict):
            return any(ints(v) for v in value.values())
        if isinstance(value, list):
            return any(ints(v) for v in value)
        return isinstance(value, int) and not isinstance(value, bool)

    for record in (
        DataCite(http("DataCite")).get(DATACITE_DOI),
        Crossref(http("Crossref")).get(CROSSREF_DOI),
    ):
        assert record is not None and not ints(record.document())


def test_a_doi_the_agency_did_not_register_is_not_found_there() -> None:
    assert DataCite(http("DataCite")).get(CROSSREF_DOI) is None
    assert Crossref(http("Crossref")).get(DATACITE_DOI) is None


@pytest.mark.parametrize(
    ("given", "bare"),
    [
        ("10.15497/RDA00157", "10.15497/rda00157"),
        ("https://doi.org/10.15497/RDA00157", "10.15497/rda00157"),
        ("doi: 10.15497/rda00157", "10.15497/rda00157"),
        ("10.15497", None),
        ("not a doi", None),
    ],
)
def test_a_doi_is_read_bare_and_lower_case(given: str, bare: str | None) -> None:
    assert bare_doi(given) == bare


def test_a_failing_service_is_retried_then_reported_unavailable() -> None:
    calls: list[str] = []

    def busy(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(503)

    with pytest.raises(UnavailableError, match="DataCite: HTTP 503"):
        DataCite(http("DataCite", busy)).get(DATACITE_DOI)
    assert len(calls) == 3


def test_a_service_that_recovers_answers_after_a_retry() -> None:
    answers = iter([httpx.Response(429), httpx.Response(404)])
    assert DataCite(http("DataCite", lambda _r: next(answers))).get(DATACITE_DOI) is None


def test_an_unreachable_service_names_only_the_failure() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(UnavailableError, match=r"^Crossref: ConnectError$"):
        Crossref(http("Crossref", down)).get(CROSSREF_DOI)


def test_an_answer_that_cannot_be_read_is_unavailable_not_a_record() -> None:
    with pytest.raises(UnavailableError, match="not JSON"):
        DataCite(http("DataCite", lambda _r: httpx.Response(200, text="<html>"))).get("10.1/x")
    with pytest.raises(UnavailableError, match="cannot be read"):
        DataCite(http("DataCite", lambda _r: httpx.Response(200, json={}))).get("10.1/x")


def test_requests_name_this_server_and_send_no_email_address() -> None:
    seen: list[httpx.Request] = []

    def keep(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(404)

    DataCite(http("DataCite", keep)).get(DATACITE_DOI)
    agent = seen[0].headers["user-agent"]
    assert agent == user_agent()
    assert agent.startswith("data-director-mcp-pid/") and "@" not in agent
    assert "mailto" not in str(seen[0].url)


def test_an_operators_contact_address_reaches_datacite_and_crossref_only() -> None:
    seen: list[httpx.Request] = []

    def keep(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(404)

    def client(name: str) -> Http:
        return Http(name, transport=httpx.MockTransport(keep), contact="ops@example.org")

    DataCite(client("DataCite")).get(DATACITE_DOI)
    Crossref(client("Crossref")).get(CROSSREF_DOI)
    for request in seen:
        agent = request.headers["user-agent"]
        assert agent.startswith("data-director-mcp-pid/")
        assert "mailto:ops@example.org" in agent
    assert DataCite(contact="ops@example.org").http.contact == "ops@example.org"
    assert Crossref(contact="ops@example.org").http.contact == "ops@example.org"
    assert Orcid().http.contact is None and RorApi().http.contact is None


@pytest.mark.parametrize(
    ("value", "address"), [("", None), ("  ", None), (" ops@example.org ", "ops@example.org")]
)
def test_a_contact_setting_is_one_plain_address_or_none(value: str, address: str | None) -> None:
    assert contact({"DD_REGISTRY_CONTACT": value}) == address
    assert contact({}) is None


@pytest.mark.parametrize(
    "value", ["not an address", "ops@example", "a@b.org; x", "a@b.org)\r\nX-Other: 1", "<a@b.org>"]
)
def test_a_contact_setting_that_is_not_an_address_stops_start_up(value: str) -> None:
    with pytest.raises(SettingsError, match="DD_REGISTRY_CONTACT"):
        registries({"DD_REGISTRY_CONTACT": value})


def test_an_orcid_id_is_read_with_its_check_character() -> None:
    assert checksum_ok("000000021825009" + "7")
    assert orcid_url(ORCID_ID) == f"https://orcid.org/{ORCID_ID}"
    assert orcid_url(f"https://orcid.org/{ORCID_ID}") == f"https://orcid.org/{ORCID_ID}"
    assert orcid_url("0000-0002-1825-0098") is None
    assert orcid_url("not an iD") is None


def test_an_orcid_record_keeps_only_the_public_name() -> None:
    record = Orcid(http("ORCID")).get(f"https://orcid.org/{ORCID_ID}")
    assert record is not None
    assert record.document() == {
        "orcid": f"https://orcid.org/{ORCID_ID}",
        "given_names": "Josiah",
        "family_name": "Carberry",
        "credit_name": None,
    }


def test_an_orcid_id_with_no_record_is_not_found() -> None:
    assert Orcid(http("ORCID")).get("https://orcid.org/0000-0001-5109-3700") is None


def test_ror_gives_the_same_organisation_from_the_registry_and_the_api(tmp_path: Path) -> None:
    index = RorIndex(built_registry(tmp_path))
    api = RorApi(http("ROR"))
    assert index.get("02b5d8509") == api.get(NERC)
    found = index.find("nerc")
    assert [o.id for o in found] == [NERC]
    assert found[0].label == "Natural Environment Research Council"


def test_a_registry_that_is_not_built_is_unavailable(tmp_path: Path) -> None:
    with pytest.raises(UnavailableError, match="ROR registry"):
        RorIndex(tmp_path / "missing.jsonl").get(NERC)
