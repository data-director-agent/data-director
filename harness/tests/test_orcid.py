"""Reading a researcher's public ORCID record and keeping what they choose
(docs/specs/projects.md, `dd_harness.orcid`)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from dd_harness import orcid
from dd_harness.testing import SAMPLE_ID, FakeOrcidRegistry, sample_record

ISSUER = "https://sandbox.orcid.org"
PRINCIPAL = f"{ISSUER}/{SAMPLE_ID}"
WHEN = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


def offered() -> dict[str, Any]:
    return orcid.normalise(
        sample_record(),
        principal_id=PRINCIPAL,
        retrieved_at=WHEN,
        source=orcid.record_url(PRINCIPAL, ISSUER),
    )


def test_only_an_orcid_issuer_has_a_public_api() -> None:
    assert orcid.public_api("https://orcid.org/") == "https://pub.orcid.org/v3.0"
    assert orcid.public_api(ISSUER).startswith("https://pub.sandbox.orcid.org/")
    with pytest.raises(orcid.OrcidError):
        orcid.public_api("https://accounts.example.org")


@pytest.mark.parametrize(
    "principal",
    [
        f"https://orcid.org/{SAMPLE_ID}",  # another issuer's
        f"{ISSUER}/0000-0002-1825-009",  # not an iD
        f"{ISSUER}/{SAMPLE_ID}/record",  # a path beyond the iD
        "mailto:someone@example.org",
    ],
)
def test_only_an_id_of_the_issuer_is_read(principal: str) -> None:
    with pytest.raises(orcid.OrcidError):
        orcid.record_url(principal, ISSUER)


def test_the_record_is_read_from_the_public_api() -> None:
    registry = FakeOrcidRegistry()
    raw = orcid.fetch_record(PRINCIPAL, ISSUER, transport=registry.transport())
    assert raw["orcid-identifier"]["path"] == SAMPLE_ID
    assert registry.requests == 1


@pytest.mark.parametrize("failing", [404, 500, 503])
def test_an_unreadable_record_is_unavailable(failing: int) -> None:
    registry = FakeOrcidRegistry(failing=failing)
    with pytest.raises(orcid.OrcidUnavailableError):
        orcid.fetch_record(PRINCIPAL, ISSUER, transport=registry.transport())


def test_an_unknown_id_is_unavailable() -> None:
    registry = FakeOrcidRegistry(records={})
    with pytest.raises(orcid.OrcidUnavailableError):
        orcid.fetch_record(PRINCIPAL, ISSUER, transport=registry.transport())


def test_the_record_offers_every_public_section() -> None:
    record = offered()
    assert record["orcid_id"] == PRINCIPAL
    assert record["researcher_name"] == "Josiah Carberry"
    for section in (*orcid.SECTIONS, *orcid.ITEMISED):
        assert record.get(section), section
    assert record["record_source"].endswith(f"/{SAMPLE_ID}/record")


def test_no_email_address_is_ever_taken() -> None:
    assert "@" not in json.dumps(offered())


def test_an_item_that_is_not_public_is_skipped() -> None:
    record = offered()
    assert "kept for trusted parties" not in record["keywords"]
    assert "102" not in {a["put_code"] for a in record["affiliations"]}


def test_a_malformed_web_address_is_left_out() -> None:
    urls = [link["link_url"] for link in offered()["researcher_links"]]
    assert urls and all(url.startswith("https://") for url in urls)


def test_organisations_keep_their_identifiers() -> None:
    record = offered()
    employment = next(a for a in record["affiliations"] if a["affiliation_kind"] == "employment")
    assert employment["organisation_identifier"] == "https://ror.org/05gq02987"
    assert employment["organisation_identifier_scheme"] == "ROR"
    funding = record["fundings"][0]
    assert funding["funder_identifier_scheme"] == "FUNDREF"
    assert funding["award_identifier"] == "NSF-1234567"


def test_current_affiliations_come_first_and_recent_works_first() -> None:
    record = offered()
    assert "end_year" not in record["affiliations"][0]
    years = [w.get("publication_year", 0) for w in record["works"]]
    assert years == sorted(years, reverse=True)


def test_works_beyond_those_offered_are_counted() -> None:
    raw = sample_record()
    groups = raw["activities-summary"]["works"]["group"]
    template = groups[0]["work-summary"][0]
    many = orcid.WORKS_OFFERED + 3
    raw["activities-summary"]["works"]["group"] = [
        {"work-summary": [{**template, "put-code": 1000 + n}]} for n in range(many)
    ]
    record = orcid.normalise(raw, principal_id=PRINCIPAL, retrieved_at=WHEN, source="https://x.org")
    assert len(record["works"]) == orcid.WORKS_OFFERED
    assert record["works_omitted"] == many - orcid.WORKS_OFFERED


def test_a_private_name_is_left_out() -> None:
    raw = sample_record()
    raw["person"]["name"] = None
    record = orcid.normalise(raw, principal_id=PRINCIPAL, retrieved_at=WHEN, source="https://x.org")
    assert "researcher_name" not in record


def test_only_what_is_chosen_is_kept() -> None:
    record = offered()
    work = record["works"][0]["put_code"]
    kept = orcid.select(record, {"sections": ["researcher_name", "keywords"], "works": [work]})
    assert set(kept) == {
        "orcid_id",
        "record_retrieved_at",
        "record_source",
        "researcher_name",
        "keywords",
        "works",
    }
    assert [w["put_code"] for w in kept["works"]] == [work]


def test_choosing_nothing_keeps_only_whose_record_it_is() -> None:
    assert set(orcid.select(offered(), {})) == {"orcid_id", "record_retrieved_at", "record_source"}


@pytest.mark.parametrize(
    "keep",
    [
        {"sections": ["emails"]},
        {"works": ["999"]},
        {"addresses": []},
        {"sections": "keywords"},
        {"works": [201]},
    ],
)
def test_a_choice_that_is_not_the_records_is_refused(keep: dict[str, Any]) -> None:
    with pytest.raises(orcid.OrcidError):
        orcid.select(offered(), keep)
