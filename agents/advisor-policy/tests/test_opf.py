"""The Open Policy Finder and Crossref clients over a mocked transport, and the first search's
rules for journals and funders (`discover.py`)."""

from __future__ import annotations

import json
import re

import httpx
import pytest
from opf_fixture import (
    ELSEVIER_OPF,
    KEY,
    NERC_OPF,
    STOTEN,
    STOTEN_CROSSREF,
    STOTEN_OPF,
    crossref,
    crossref_handler,
    opf,
    opf_handler,
    refusal,
)

from dd_agent_advisor_policy import discover
from dd_agent_advisor_policy.classes import Actor, ActorRole
from dd_agent_advisor_policy.opf import MAX_CONDITIONS, filter_for, from_item
from dd_mcp_doaj.journals import normal_issn
from dd_sdk.evidence import DOCUMENT_CANONICALISATION, verify
from dd_sdk.registry import RegistryUnavailable

# --- the Open Policy Finder client ------------------------------------------------------------


def test_a_search_sends_the_key_in_a_header_and_never_in_the_address() -> None:
    seen: list[httpx.Request] = []
    [record] = opf(opf_handler(seen)).search("funder", "Natural Environment Research Council")
    [request] = seen
    assert request.headers["x-api-key"] == KEY
    assert KEY not in str(request.url)
    assert request.url.params["item-type"] == "funder"
    assert request.url.params["format"] == "Json"
    assert refusal(request) is None
    assert "data-director-advisor-policy" in request.headers["user-agent"]
    assert record.source_id == NERC_OPF
    assert (record.name, record.acronyms, record.country) == (
        "Natural Environment Research Council",
        ["NERC"],
        "gb",
    )


@pytest.mark.parametrize(
    ("item_type", "text"),
    [
        ("funder", "Natural Environment Research Council"),
        ("funder", "Deutsche Forschungsgemeinschaft"),
        ("publication", "The Journal of the Society for the Study of Things and Others"),
        ("publisher", "Elsevier"),
    ],
)
def test_a_filter_asks_for_whole_words_of_the_name_in_documented_terms(
    item_type: str, text: str
) -> None:
    found = json.loads(filter_for(item_type, text))  # type: ignore[arg-type]
    assert 1 <= len(found) <= MAX_CONDITIONS
    name_words = {w.casefold() for w in re.findall(r"\w+", text)}
    for field, operator, value in found:
        assert field in ("name", "title") and operator == "contains word"
        assert value.casefold() in name_words and value.casefold() not in {"the", "of", "for"}


def test_a_single_word_in_capitals_is_looked_for_among_acronyms() -> None:
    [record] = opf().search("funder", "NERC")
    assert record.source_id == NERC_OPF
    [[field, _, value]] = json.loads(filter_for("funder", "NERC"))
    assert (field, value) == ("acronym", "NERC")


def test_a_refused_filter_is_unavailable_not_empty() -> None:
    refuse = httpx.Response(400, json={"error": "unsupported operator"})
    with pytest.raises(RegistryUnavailable, match="HTTP 400"):
        opf(lambda _: refuse).search("funder", "NERC")


def test_a_journal_is_read_by_issn_with_its_publisher_and_policies() -> None:
    record = opf().journal_by_issn("0048-9697")
    assert record is not None and record.source_id == STOTEN_OPF
    assert record.kind == "journal"
    assert record.issns == ["0048-9697", "1879-1026"]
    assert [(p.id, p.name) for p in record.publishers] == [("30", "Elsevier")]
    [policy] = record.policies
    # Numbers and booleans are strings, so the document hashes alike after the A2A transport.
    assert policy["permitted_oa"][0]["embargo"] == {"amount": "24", "units": "months"}
    assert policy["open_access_prohibited"] == "no"


def test_a_record_is_evidence_hashed_whole() -> None:
    record = from_item(STOTEN["items"][0], "publication")
    assert record is not None
    assert verify(record.document(), DOCUMENT_CANONICALISATION, record.content_hash())
    assert "cc_by_nc_nd" in record.prompt_text()


def test_an_unknown_identifier_is_none() -> None:
    assert opf().fetch("publisher", "999") is None


@pytest.mark.parametrize(("status", "said"), [(500, "HTTP 500"), (401, "OPEN_POLICY_FINDER")])
def test_an_error_status_is_unavailable_not_empty(status: int, said: str) -> None:
    with pytest.raises(RegistryUnavailable, match=said):
        opf(opf_handler(status=status)).search("funder", "NERC")


def test_a_transport_failure_or_unreadable_answer_is_unavailable_and_names_no_key() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"no route to {request.url}")

    with pytest.raises(RegistryUnavailable) as caught:
        opf(down).search("funder", "NERC")
    assert KEY not in str(caught.value)
    with pytest.raises(RegistryUnavailable, match="not JSON"):
        opf(lambda _: httpx.Response(200, text="<html>")).search("funder", "NERC")
    with pytest.raises(RegistryUnavailable, match="no items"):
        opf(lambda _: httpx.Response(200, json={"error": "x"})).search("funder", "NERC")


# --- the Crossref client ----------------------------------------------------------------------


def test_crossref_names_a_journals_publisher_by_issn_or_title() -> None:
    seen: list[httpx.Request] = []
    journals = crossref(crossref_handler(seen))
    journal = journals.by_issn("00489697")
    assert journal is not None and journal.source_id == STOTEN_CROSSREF
    assert (journal.title, journal.publisher) == ("Science of The Total Environment", "Elsevier BV")
    assert [j.publisher for j in journals.search("Science of the Total Environment")] == [
        "Elsevier BV"
    ]
    assert journals.by_issn("not an issn") is None
    assert journals.by_issn("1234-5678") is None
    assert all("data-director-advisor-policy" in r.headers["user-agent"] for r in seen)
    with pytest.raises(RegistryUnavailable, match="HTTP 503"):
        crossref(crossref_handler(status=503)).by_issn("0048-9697")


def test_an_issn_is_written_one_way() -> None:
    assert normal_issn("1879102x") == "1879-102X"
    assert normal_issn(" 0048-9697 ") == "0048-9697"
    assert normal_issn("0048-969") is None


# --- the first search's rules -----------------------------------------------------------------


def test_a_journal_by_title_reaches_its_publisher() -> None:
    actor = Actor(role=ActorRole.JOURNAL, name="The Science of the Total Environment")
    found = discover.journal(actor, opf(), crossref())
    assert found.record is not None and found.record.source_id == STOTEN_OPF
    assert [p.source_id for p in found.publishers] == [ELSEVIER_OPF]
    assert found.publisher == "Elsevier" and found.issn == "0048-9697"
    assert "Elsevier" in found.publisher_names
    assert found.candidates == [] and found.problems == []


def test_without_open_policy_finder_crossref_names_the_publisher() -> None:
    actor = Actor(role=ActorRole.JOURNAL, name="Science of the Total Environment")
    found = discover.journal(actor, None, crossref())
    assert found.crossref is not None and found.publisher == "Elsevier BV"
    # The legal form is set aside, so FAIRsharing's "Elsevier - …" records match.
    assert found.publisher_names == ["Elsevier BV", "Elsevier"]


def test_two_journals_with_the_title_are_not_guessed_between() -> None:
    twin = {
        "items": [
            {"id": 1, "title": [{"title": "Journal of Ecology"}]},
            {"id": 2, "title": [{"title": "Journal of Ecology"}]},
            {"id": 3, "title": [{"title": "Journal of Ecology and Environment"}]},
        ]
    }
    source = opf(opf_handler(extra={("publication", "journal of ecology"): twin}))
    found = discover.journal(Actor(role=ActorRole.JOURNAL, name="Journal of Ecology"), source, None)
    assert [c.source_id.rsplit("/", 1)[-1] for c in found.candidates] == ["1", "2"]
    assert found.record is None and found.publisher_names == []


def test_an_unknown_title_finds_nothing_and_a_failure_is_noted() -> None:
    actor = Actor(role=ActorRole.JOURNAL, name="Journal of Nothing")
    found = discover.journal(actor, opf(), crossref())
    assert (found.record, found.crossref, found.publishers, found.candidates) == (
        None,
        None,
        [],
        [],
    )
    down = discover.journal(actor, opf(opf_handler(status=500)), crossref())
    assert down.problems and "HTTP 500" in down.problems[0]


def test_a_funder_is_kept_only_when_a_name_or_acronym_names_it() -> None:
    nerc = Actor(role=ActorRole.FUNDER, name="NERC")
    found, asked = discover.funders(nerc, ["NERC", "Natural Environment Research Council"], opf())
    assert [r.source_id for r in found] == [NERC_OPF]
    assert asked == [
        "open policy finder funder: 'NERC'",
        "open policy finder funder: 'Natural Environment Research Council'",
    ]
    nowhere = Actor(role=ActorRole.FUNDER, name="Ministry of Nowhere")
    assert discover.funders(nowhere, [], opf())[0] == []
