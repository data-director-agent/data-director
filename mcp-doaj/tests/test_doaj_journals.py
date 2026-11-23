"""The client against DOAJ's recorded answers: a journal read by ISSN and searched by title, each
projected to a record with no integers; a miss; and every way DOAJ can fail to answer."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from dd_mcp_doaj.journals import Doaj, DoajUnavailableError, journal_record, normal_issn, user_agent

DATA = Path(__file__).with_name("data")


def recorded(name: str) -> dict[str, Any]:
    body: dict[str, Any] = json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))
    return body


def doaj(handler: Callable[[httpx.Request], httpx.Response]) -> Doaj:
    return Doaj(client=httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda _: None)


def answering(name: str, seen: list[httpx.Request] | None = None) -> Doaj:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(200, json=recorded(name))

    return doaj(handler)


def _integers(value: object) -> bool:
    if isinstance(value, dict):
        return any(_integers(v) for v in value.values())
    if isinstance(value, list):
        return any(_integers(v) for v in value)
    return isinstance(value, int) and not isinstance(value, bool)


def test_a_journal_is_read_by_its_issn() -> None:
    seen: list[httpx.Request] = []
    record = answering("ncomms", seen).by_issn("20411723")
    assert record is not None
    assert record["eissn"] == "2041-1723"
    assert record["url"] == "https://doaj.org/toc/2041-1723"
    assert {licence["type"] for licence in record["licences"]} >= {"CC BY"}
    assert record["deposit_policy"]["has_policy"] is True
    assert record["deposit_policy"]["url"]
    assert record["pages"]["license_terms"].startswith("https://")
    [request] = seen
    assert request.url.path.endswith("/issn:2041-1723")
    assert request.headers["User-Agent"].startswith("data-director-mcp-doaj/")


def test_a_record_holds_no_integers_and_its_lists_are_sorted() -> None:
    record = answering("ncomms").by_issn("2041-1723")
    assert record is not None and not _integers(record)
    assert record["oa_start"] is not None and record["apc"]["highest"]
    lists = (record["subjects"], record["preservation"]["services"], record["apc"]["highest"])
    for values in lists:
        assert values == sorted(values)


def test_an_issn_another_journal_holds_is_not_taken() -> None:
    assert answering("plos").by_issn("2041-1723") is None


def test_an_issn_doaj_does_not_list_is_none() -> None:
    empty = doaj(lambda _: httpx.Response(200, json={"total": 0, "results": []}))
    assert empty.by_issn("0000-0000") is None


def test_something_that_is_not_an_issn_asks_nothing() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("DOAJ was asked")

    assert doaj(handler).by_issn("not an issn") is None


def test_a_title_is_searched_as_a_phrase() -> None:
    seen: list[httpx.Request] = []
    found = answering("plos", seen).search('PLOS "ONE"')
    assert [r["alternative_title"] for r in found] == ["PLOS ONE"]
    [request] = seen
    assert "bibjson.title" in request.url.path
    assert request.url.params["pageSize"]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"message": "no results"}),
    ],
)
def test_an_answer_that_cannot_be_read_is_unavailable(response: httpx.Response) -> None:
    with pytest.raises(DoajUnavailableError):
        doaj(lambda _: response).by_issn("2041-1723")


def test_a_transport_failure_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(DoajUnavailableError):
        doaj(handler).search("PLOS ONE")


def test_a_busy_answer_is_retried_once() -> None:
    answers = [httpx.Response(429), httpx.Response(200, json=recorded("ncomms"))]
    assert doaj(lambda _: answers.pop(0)).by_issn("2041-1723") is not None
    busy = [httpx.Response(429), httpx.Response(429)]
    with pytest.raises(DoajUnavailableError):
        doaj(lambda _: busy.pop(0)).by_issn("2041-1723")


def test_a_result_without_title_or_issn_is_not_a_record() -> None:
    assert journal_record({"id": "x", "bibjson": {"title": "No ISSN"}}) is None
    assert journal_record({"id": "x", "bibjson": {"eissn": "1932-6203"}}) is None
    assert journal_record({"id": "x"}) is None


def test_issns_and_contact_addresses_are_checked() -> None:
    assert normal_issn("1932620x") == "1932-620X"
    assert normal_issn("19326") is None
    assert "mailto:ops@example.org" in user_agent("ops@example.org")
    with pytest.raises(ValueError):
        user_agent("ops@example.org) X-Injected: 1")
