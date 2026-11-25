"""The cache in front of the registries and the offline mode: a record read again within its time
to live is not asked for again and is the same record; a miss is kept for less long; an error is
never kept; offline, only the ROR dump and the cache answer."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import httpx
import pytest
from pid_support import DATACITE_DOI, NERC, ORCID_ID, built_registry, recorded, registries

from dd_mcp_pid.caching import DEFAULT_TTL, Lookups, lookups
from dd_mcp_pid.cli import SettingsError, cache, ror_client_id, ror_sources
from dd_mcp_pid.ror import RorApi
from dd_mcp_pid.tools import Registry
from dd_registry_cache import Ttl
from dd_sdk.evidence import DOCUMENT_CANONICALISATION, content_hash

UNKNOWN_DOI = "10.15497/unknown"


class Clock:
    def __init__(self) -> None:
        self.at = 1_800_000_000.0

    def __call__(self) -> float:
        return self.at


class Upstream:
    """The recorded registries, counting requests by host, which can be made to fail."""

    def __init__(self) -> None:
        self.asked: Counter[str] = Counter()
        self.down = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.asked[request.url.host] += 1
        if self.down:
            return httpx.Response(503)
        return recorded(request)


def servers(
    upstream: Upstream, cached: Lookups, registry: Path | None = None
) -> dict[str, Registry]:
    return {r.name: r for r in registries(registry, upstream, lookups=cached)}


def call(registry: Registry, tool: str, **arguments: Any) -> tuple[list[dict[str, Any]], str]:
    result = registry.call(tool, arguments)
    assert not result.is_error, result.content
    assert result.structured_content is not None
    return result.structured_content["records"], result.content[0].text  # type: ignore[union-attr]


def text_of(registry: Registry, tool: str, **arguments: Any) -> tuple[bool, str]:
    result = registry.call(tool, arguments)
    assert not result.structured_content
    return bool(result.is_error), result.content[0].text  # type: ignore[union-attr]


@pytest.fixture
def clock() -> Clock:
    return Clock()


def test_a_doi_read_again_within_its_time_to_live_is_not_asked_for(
    tmp_path: Path, clock: Clock
) -> None:
    upstream = Upstream()
    datacite = servers(upstream, lookups(tmp_path, now=clock))["datacite"]
    first, first_text = call(datacite, "get_doi", doi=DATACITE_DOI)
    clock.at += DEFAULT_TTL.found - 1
    again, again_text = call(datacite, "get_doi", doi=f"https://doi.org/{DATACITE_DOI.upper()}")
    assert upstream.asked["api.datacite.org"] == 1
    assert again == first
    hashes = {content_hash(r[0], DOCUMENT_CANONICALISATION) for r in (first, again)}
    assert len(hashes) == 1
    assert "cache" not in first_text
    assert "cache" in again_text


def test_a_record_past_its_time_to_live_is_asked_for_again(clock: Clock) -> None:
    upstream = Upstream()
    orcid = servers(upstream, lookups(None, now=clock))["orcid"]
    call(orcid, "get_orcid", orcid=ORCID_ID)
    clock.at += DEFAULT_TTL.found + 1
    _, refreshed = call(orcid, "get_orcid", orcid=ORCID_ID)
    assert upstream.asked["pub.orcid.org"] == 2
    assert "cache" not in refreshed


def test_a_miss_is_kept_for_its_own_shorter_time(clock: Clock) -> None:
    upstream = Upstream()
    ttl = Ttl(found=1000, missing=10)
    crossref = servers(upstream, lookups(None, ttl, now=clock))["crossref"]
    for _ in range(2):
        assert call(crossref, "get_doi", doi=UNKNOWN_DOI)[0] == []
    assert upstream.asked["api.crossref.org"] == 1
    clock.at += 11
    assert call(crossref, "get_doi", doi=UNKNOWN_DOI)[0] == []
    assert upstream.asked["api.crossref.org"] == 2


def test_an_error_is_never_kept(clock: Clock) -> None:
    upstream = Upstream()
    upstream.down = True
    datacite = servers(upstream, lookups(None, now=clock))["datacite"]
    assert text_of(datacite, "get_doi", doi=DATACITE_DOI)[0]
    upstream.down = False
    records, _ = call(datacite, "get_doi", doi=DATACITE_DOI)
    assert [r["doi"] for r in records] == [DATACITE_DOI]


def test_an_expired_record_answers_while_the_registry_is_down_and_says_so(clock: Clock) -> None:
    upstream = Upstream()
    datacite = servers(upstream, lookups(None, now=clock))["datacite"]
    first, _ = call(datacite, "get_doi", doi=DATACITE_DOI)
    clock.at += DEFAULT_TTL.found + 1
    upstream.down = True
    again, summary = call(datacite, "get_doi", doi=DATACITE_DOI)
    assert again == first
    assert "expired" in summary


def test_the_cache_survives_a_restart(tmp_path: Path, clock: Clock) -> None:
    upstream = Upstream()
    call(servers(upstream, lookups(tmp_path, now=clock))["datacite"], "get_doi", doi=DATACITE_DOI)
    restarted = servers(upstream, lookups(tmp_path, now=clock))["datacite"]
    call(restarted, "get_doi", doi=DATACITE_DOI)
    assert upstream.asked["api.datacite.org"] == 1


def test_a_ror_identifier_the_api_gave_is_cached(clock: Clock) -> None:
    upstream = Upstream()
    ror = servers(upstream, lookups(None, now=clock))["ror"]
    first, first_text = call(ror, "get_organisation", id=NERC)
    again, again_text = call(ror, "get_organisation", id=NERC)
    assert upstream.asked["api.ror.org"] == 1
    assert again == first
    assert "API" in first_text
    assert "cache" in again_text


def test_offline_answers_from_the_dump_and_the_cache_and_asks_nothing(
    tmp_path: Path, clock: Clock
) -> None:
    upstream = Upstream()
    call(servers(upstream, lookups(tmp_path, now=clock))["datacite"], "get_doi", doi=DATACITE_DOI)
    upstream.asked.clear()

    offline = servers(
        upstream, lookups(tmp_path, offline=True, now=clock), built_registry(tmp_path)
    )
    [org], _ = call(offline["ror"], "get_organisation", id=NERC)
    assert org["id"] == NERC
    [record], _ = call(offline["datacite"], "get_doi", doi=DATACITE_DOI)
    assert record["doi"] == DATACITE_DOI
    clock.at += DEFAULT_TTL.found + 1
    assert call(offline["datacite"], "get_doi", doi=DATACITE_DOI)[0] == [record]

    for name, tool, arguments in [
        ("crossref", "get_doi", {"doi": DATACITE_DOI}),
        ("orcid", "get_orcid", {"orcid": ORCID_ID}),
        ("grants", "resolve_grant", {"award": "NE/X007197/1"}),
    ]:
        error, message = text_of(offline[name], tool, **arguments)
        assert error
        assert "DD_PID_OFFLINE" in message
    assert sum(upstream.asked.values()) == 0


def test_offline_without_a_dump_cannot_search_ror(clock: Clock) -> None:
    upstream = Upstream()
    ror = servers(upstream, lookups(None, offline=True, now=clock))["ror"]
    error, message = text_of(ror, "search_organisations", name="NERC")
    assert error
    assert "DD_PID_OFFLINE" in message
    assert sum(upstream.asked.values()) == 0


def ror_headers(client_id: str | None) -> httpx.Headers:
    seen: list[httpx.Headers] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers)
        return recorded(request)

    api = RorApi(client_id=client_id)
    api.http.transport = httpx.MockTransport(handler)
    api.get(NERC)
    return seen[0]


def test_ror_is_sent_its_client_id_only_when_one_is_given() -> None:
    assert ror_headers("abc123")["Client-Id"] == "abc123"
    assert "Client-Id" not in ror_headers(None)


def test_the_client_id_is_read_from_a_credential_file(tmp_path: Path) -> None:
    (tmp_path / "ror-client-id").write_text("abc123\n", encoding="utf-8")
    env = {"DD_PID_ROR_CLIENT_ID_FILE": "ror-client-id", "CREDENTIALS_DIRECTORY": str(tmp_path)}
    assert ror_client_id(env) == "abc123"
    assert ror_client_id({}) is None


@pytest.mark.parametrize(
    "env",
    [
        {"DD_PID_ROR_CLIENT_ID_FILE": "ror-client-id"},
        {"DD_PID_ROR_CLIENT_ID_FILE": "/nonexistent/ror-client-id"},
    ],
)
def test_a_client_id_file_that_cannot_be_read_stops_start_up(env: dict[str, str]) -> None:
    with pytest.raises(SettingsError):
        ror_client_id(env)


@pytest.mark.parametrize(
    "env",
    [
        {"DD_PID_CACHE_TTL_FOUND": "a week"},
        {"DD_PID_CACHE_TTL_MISSING": "-1"},
        {"DD_PID_OFFLINE": "yes"},
    ],
)
def test_bad_cache_settings_stop_start_up(env: dict[str, str]) -> None:
    with pytest.raises(SettingsError):
        cache(env)


def test_offline_cannot_ask_ror_live() -> None:
    env = {"DD_PID_OFFLINE": "1", "DD_PID_ROR": "live"}
    with pytest.raises(SettingsError):
        ror_sources(env, cache(env))


def test_offline_ror_has_no_api(tmp_path: Path) -> None:
    env = {"DD_PID_OFFLINE": "1", "DD_PID_CACHE_DIR": str(tmp_path)}
    sources = ror_sources(env, cache(env))
    assert sources.api is None
    assert sources.lookups.offline
