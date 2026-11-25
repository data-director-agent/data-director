"""The Open Policy Finder client over a mocked transport: what is sent, and how an answer becomes
a record."""

from __future__ import annotations

import json
import re

import httpx
import pytest
from opf_records import KEY, NERC_PAGE, STOTEN, STOTEN_PAGE, opf, opf_handler, refusal

from dd_mcp_opf.client import (
    MAX_CONDITIONS,
    OpenPolicyFinder,
    OpfUnavailableError,
    filter_for,
    normal_issn,
    record_from_item,
    user_agent,
)


def test_a_search_sends_the_key_in_a_header_and_never_in_the_address() -> None:
    seen: list[httpx.Request] = []
    [record] = opf(opf_handler(seen)).search("funder", "Natural Environment Research Council")
    [request] = seen
    assert request.headers["x-api-key"] == KEY
    assert KEY not in str(request.url)
    assert request.url.params["item-type"] == "funder"
    assert request.url.params["format"] == "Json"
    assert refusal(request) is None
    assert "data-director-mcp-opf" in request.headers["user-agent"]
    assert record["page"] == NERC_PAGE
    assert (record["names"], record["acronyms"], record["country"]) == (
        ["Natural Environment Research Council"],
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
    assert record["page"] == NERC_PAGE
    [[field, _, value]] = json.loads(filter_for("funder", "NERC"))
    assert (field, value) == ("acronym", "NERC")


def test_a_refused_filter_is_unavailable_not_empty() -> None:
    refuse = httpx.Response(400, json={"error": "unsupported operator"})
    with pytest.raises(OpfUnavailableError, match="HTTP 400"):
        opf(lambda _: refuse).search("funder", "NERC")


def test_a_journal_is_read_by_issn_with_its_publisher_and_policies() -> None:
    record = opf().fetch("publication", "0048-9697")
    assert record is not None and record["page"] == STOTEN_PAGE
    assert record["issns"] == ["0048-9697", "1879-1026"]
    assert [(p["id"], p["name"]) for p in record["publishers"]] == [("30", "Elsevier")]
    [policy] = record["policies"]
    # Numbers and booleans are strings, so the record hashes alike after any transport.
    assert policy["permitted_oa"][0]["embargo"] == {"amount": "24", "units": "months"}
    assert policy["open_access_prohibited"] == "no"


def test_a_record_holds_no_numbers_or_flags() -> None:
    record = record_from_item(STOTEN["items"][0], "publication")
    assert record is not None

    def kinds(value: object) -> set[type]:
        if isinstance(value, dict):
            return set().union(*(kinds(v) for v in value.values()), set())
        if isinstance(value, list):
            return set().union(*(kinds(v) for v in value), set())
        return {type(value)}

    assert kinds(record) <= {str, type(None)}


def test_an_item_with_no_identifier_is_no_record() -> None:
    assert record_from_item({"title": [{"title": "Nameless"}]}, "publication") is None


def test_an_unknown_identifier_is_none() -> None:
    assert opf().fetch("publisher", "999") is None


@pytest.mark.parametrize(("status", "said"), [(500, "HTTP 500"), (401, "OPEN_POLICY_FINDER")])
def test_an_error_status_is_unavailable_not_empty(status: int, said: str) -> None:
    with pytest.raises(OpfUnavailableError, match=said):
        opf(opf_handler(status=status)).search("funder", "NERC")


def test_a_transport_failure_or_unreadable_answer_is_unavailable_and_names_no_key() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"no route to {request.url}")

    with pytest.raises(OpfUnavailableError) as caught:
        opf(down).search("funder", "NERC")
    assert KEY not in str(caught.value)
    with pytest.raises(OpfUnavailableError, match="not JSON"):
        opf(lambda _: httpx.Response(200, text="<html>")).search("funder", "NERC")
    with pytest.raises(OpfUnavailableError, match="no items"):
        opf(lambda _: httpx.Response(200, json={"error": "x"})).search("funder", "NERC")


def test_a_client_needs_a_key() -> None:
    with pytest.raises(ValueError, match="API key"):
        OpenPolicyFinder("")


def test_the_user_agent_names_the_package_and_takes_one_contact_address() -> None:
    assert "mailto:" not in user_agent()
    assert user_agent("ops@example.org").endswith("; mailto:ops@example.org)")
    with pytest.raises(ValueError, match="e-mail"):
        user_agent("a@b.org); X-Evil: 1")


def test_an_issn_is_normalised_or_refused() -> None:
    assert normal_issn("00489697") == "0048-9697"
    assert normal_issn("1932-620x") == "1932-620X"
    assert normal_issn("not an issn") is None
