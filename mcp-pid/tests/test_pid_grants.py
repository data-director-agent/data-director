"""The `grants` server against recorded Crossref and OpenAIRE answers: what a grant record keeps,
how candidates from both sources are told apart, narrowed and listed, and what is sent upstream."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from pid_support import (
    UKRI_AWARD,
    WELLCOME_AWARD,
    WELLCOME_GRANT_DOI,
    grants,
    http,
    recorded,
)

from dd_mcp_pid.cli import cache, grant_sources
from dd_mcp_pid.grant_server import grant_registry
from dd_mcp_pid.grants import AccessToken, CrossrefGrants, OpenAireGraph, award_number


def call(arguments: dict[str, Any], **sources: Any) -> tuple[list[dict[str, Any]], str, bool]:
    result = grant_registry(grants(**sources)).call("resolve_grant", arguments)
    structured = result.structured_content or {}
    return structured.get("records", []), result.content[0].text, bool(result.is_error)  # type: ignore[union-attr]


def failing(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(503)


def test_a_crossref_grant_is_cut_to_its_record() -> None:
    record = CrossrefGrants(http("Crossref", recorded)).by_doi(WELLCOME_GRANT_DOI)
    assert record is not None
    assert record.source == "Crossref"
    assert record.id == f"https://doi.org/{WELLCOME_GRANT_DOI}"
    assert record.doi == WELLCOME_GRANT_DOI
    assert record.award == WELLCOME_AWARD
    assert record.funder == "Wellcome Trust"
    assert record.funder_ids == ["https://doi.org/10.13039/100010269"]
    assert record.title is not None
    assert record.start_date == "2013-08-16"


def test_an_openaire_project_is_cut_to_the_same_shape() -> None:
    [record] = OpenAireGraph(http("OpenAIRE", recorded)).by_award(UKRI_AWARD)
    assert record.source == "OpenAIRE"
    assert record.award == UKRI_AWARD
    assert record.funder_short_name == "UKRI"
    assert record.funding_stream == "NERC"
    assert record.doi is None
    assert record.openaire_id is not None
    assert record.id.startswith("https://explore.openaire.eu/search/project?projectId=")


def test_a_grant_doi_is_asked_of_crossref_alone() -> None:
    asked: list[str] = []

    def openaire(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        return recorded(request)

    records, _, error = call({"award": f"https://doi.org/{WELLCOME_GRANT_DOI}"}, openaire=openaire)
    assert not error
    assert [r["doi"] for r in records] == [WELLCOME_GRANT_DOI]
    assert asked == []


def test_an_award_with_no_grant_doi_is_found_in_openaire() -> None:
    records, _, error = call({"award": UKRI_AWARD})
    assert not error
    assert [(r["source"], r["funding_stream"]) for r in records] == [("OpenAIRE", "NERC")]


def test_an_ambiguous_award_lists_each_grant_once_preferring_crossref() -> None:
    records, summary, error = call({"award": WELLCOME_AWARD})
    assert not error
    sources = {r["funder"]: r["source"] for r in records}
    assert sources == {
        "Wellcome Trust": "Crossref",
        "Swiss National Science Foundation": "OpenAIRE",
    }
    assert "ask which" in summary


@pytest.mark.parametrize("funder", ["Wellcome", "wellcome trust", "WT"])
def test_a_funder_narrows_the_candidates_without_being_sent(funder: str) -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return recorded(request)

    records, _, _ = call({"award": WELLCOME_AWARD, "funder": funder}, handler=handler)
    assert [r["funder"] for r in records] == ["Wellcome Trust"]
    assert sent
    for request in sent:
        assert all(funder.lower() not in v.lower() for v in request.url.params.values())


def test_a_funder_that_matches_none_keeps_every_candidate() -> None:
    records, summary, _ = call({"award": WELLCOME_AWARD, "funder": "Leverhulme Trust"})
    assert len(records) == 2
    assert "Leverhulme Trust" in summary


def test_an_award_neither_source_holds_has_no_records() -> None:
    records, _, error = call({"award": "ZZ/NOPE/1"})
    assert records == [] and not error


def test_one_failing_source_leaves_the_others_grants_and_says_so() -> None:
    records, summary, error = call({"award": WELLCOME_AWARD}, openaire=failing)
    assert not error
    assert [r["source"] for r in records] == ["Crossref"]
    assert "OpenAIRE" in summary


def test_both_failing_is_an_error() -> None:
    _, _, error = call({"award": WELLCOME_AWARD}, handler=failing)
    assert error


@pytest.mark.parametrize("award", ["", "   ", "a,b", "a|b", "x" * 101])
def test_what_cannot_be_an_award_is_refused(award: str) -> None:
    assert award_number(award) is None
    _, _, error = call({"award": award})
    assert error


def test_no_record_holds_an_integer() -> None:
    def ints(value: object) -> bool:
        if isinstance(value, dict):
            return any(ints(v) for v in value.values())
        if isinstance(value, list):
            return any(ints(v) for v in value)
        return isinstance(value, int) and not isinstance(value, bool)

    for award in (WELLCOME_AWARD, UKRI_AWARD):
        records, _, _ = call({"award": award})
        assert records and not ints(records)


def test_only_the_award_is_sent_upstream() -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return recorded(request)

    call({"award": UKRI_AWARD, "funder": "NERC"}, handler=handler)
    assert {r.url.host for r in sent} == {"api.crossref.org", "api.openaire.eu"}
    for request in sent:
        assert UKRI_AWARD in request.url.params["filter"]
        assert "mailto" not in request.url.params
        assert "Authorization" not in request.headers


def test_openaire_is_sent_the_contact_and_an_access_token_when_configured() -> None:
    sent: list[httpx.Request] = []
    now = [0.0]

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        if request.url.host == "services.openaire.eu":
            return httpx.Response(200, json={"access_token": "issued", "expires_in": "3600"})
        return recorded(request)

    token = AccessToken("refresh-secret", http=http("tokens", handler), clock=lambda: now[0])
    graph = OpenAireGraph(http("OpenAIRE", handler), contact="ops@example.org", token=token)
    graph.by_award(UKRI_AWARD)
    graph.by_award(UKRI_AWARD)
    issued = [r for r in sent if r.url.host == "services.openaire.eu"]
    asked = [r for r in sent if r.url.host == "api.openaire.eu"]
    assert len(issued) == 1  # the token is kept while it lasts
    assert all(r.headers["Authorization"] == "Bearer issued" for r in asked)
    assert all(r.url.params["mailto"] == "ops@example.org" for r in asked)
    now[0] = 4000.0
    graph.by_award(UKRI_AWARD)
    assert len([r for r in sent if r.url.host == "services.openaire.eu"]) == 2


def test_openaire_is_asked_anonymously_when_no_token_can_be_issued() -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        if request.url.host == "services.openaire.eu":
            return httpx.Response(401, json={"error": "invalid"})
        return recorded(request)

    token = AccessToken("expired", http=http("tokens", handler))
    graph = OpenAireGraph(http("OpenAIRE", handler), token=token)
    assert graph.by_award(UKRI_AWARD)
    assert graph.anonymous
    assert all("Authorization" not in r.headers for r in sent if r.url.host == "api.openaire.eu")


def test_the_refresh_token_is_a_setting_and_never_shown() -> None:
    sources = grant_sources({"DD_OPENAIRE_REFRESH_TOKEN": " refresh-secret "}, None, cache({}))
    assert sources.openaire is not None and sources.openaire.token is not None
    assert "refresh-secret" not in repr(sources)
    assert grant_sources({}, None, cache({})).openaire.token is None  # type: ignore[union-attr]
