"""The FAIRsharing client's local cache (#327): records within their time to live are not asked
for again, then revalidated by ETag; searches are cached by their filters; an outage is answered
from an expired entry; the sign-in token is renewed. No network, an injected clock."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pytest

from dd_registry_cache import Origin
from dd_sdk.registry import RegistryUnavailable, SnapshotRef, provenance
from dd_sdk.registry.caching import (
    CACHE_DIR,
    TTL_RECORD,
    Ttls,
    cache_from_env,
    memory_cache,
    ttls_from_env,
)
from dd_sdk.registry.fairsharing import (
    SEARCH,
    SIGN_IN,
    FairsharingClient,
    search_key,
    token_expiry,
)

URL = "https://fairsharing.org/FAIRsharing.x"
TTLS = Ttls(record=100.0, search=50.0, missing=10.0)


def _jwt(exp: float | None) -> str:
    claims = {} if exp is None else {"exp": exp}
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"h.{payload}.s"


@dataclass
class Clock:
    t: float = 1_000_000.0

    def __call__(self) -> float:
        return self.t


@dataclass
class Fairsharing:
    """A fake FAIRsharing: answers each request with the next of `answers`, and records it."""

    answers: list[httpx.Response | Exception]
    jwts: list[str] = field(default_factory=lambda: ["t1", "t2", "t3"])
    seen: list[httpx.Request] = field(default_factory=list)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if str(request.url) == SIGN_IN:
            self.seen.append(request)
            return httpx.Response(200, json={"jwt": self.jwts.pop(0)})
        self.seen.append(request)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    def asked(self, url: str = "") -> list[httpx.Request]:
        return [r for r in self.seen if str(r.url) != SIGN_IN and str(r.url).startswith(url)]

    def signed_in(self) -> int:
        return sum(1 for r in self.seen if str(r.url) == SIGN_IN)


def _client(fake: Fairsharing, clock: Clock) -> FairsharingClient:
    return FairsharingClient(
        httpx.Client(transport=httpx.MockTransport(fake)),
        login="l",
        password="p",
        cache=memory_cache(clock),
        ttls=TTLS,
        now=clock,
    )


def _record(name: str, etag: str = 'W/"e1"') -> httpx.Response:
    return httpx.Response(200, json={"name": name}, headers={"etag": etag})


DOWN = httpx.ConnectError("no route")


# --- records (#329) ---------------------------------------------------------------------------


def test_a_record_within_its_time_to_live_is_not_asked_for_again() -> None:
    clock, fake = Clock(), Fairsharing([_record("x")])
    client = _client(fake, clock)
    first = client.get_json(URL)
    clock.t += 99
    again = client.get_json(URL)
    assert (first.origin, again.origin) == (Origin.LIVE, Origin.CACHE)
    assert again.value == first.value == {"name": "x"}
    assert again.checked_at == first.checked_at
    assert len(fake.asked()) == 1


def test_an_expired_record_is_revalidated_and_a_304_keeps_it() -> None:
    clock, fake = Clock(), Fairsharing([_record("x"), httpx.Response(304)])
    client = _client(fake, clock)
    first = client.get_json(URL)
    clock.t += 101
    again = client.get_json(URL)
    assert again.origin is Origin.REVALIDATED
    assert again.value == {"name": "x"}
    assert again.checked_at > first.checked_at
    assert fake.asked()[1].headers["If-None-Match"] == 'W/"e1"'


def test_a_changed_record_replaces_the_cached_one() -> None:
    clock, fake = Clock(), Fairsharing([_record("x"), _record("y", 'W/"e2"')])
    client = _client(fake, clock)
    client.get_json(URL)
    clock.t += 101
    again = client.get_json(URL)
    assert (again.origin, again.value) == (Origin.LIVE, {"name": "y"})


@pytest.mark.parametrize(
    "absent",
    [
        httpx.Response(404),
        httpx.Response(200, text="<html>", headers={"content-type": "text/html"}),
    ],
)
def test_not_found_is_cached_for_a_shorter_time(absent: httpx.Response) -> None:
    clock, fake = Clock(), Fairsharing([absent, httpx.Response(404)])
    client = _client(fake, clock)
    assert client.get_json(URL).value is None
    clock.t += 9
    assert client.get_json(URL).origin is Origin.CACHE
    clock.t += 2
    assert client.get_json(URL).origin is Origin.LIVE
    assert "If-None-Match" not in fake.asked()[1].headers


@pytest.mark.parametrize("outage", [DOWN, httpx.Response(503)])
def test_an_outage_is_answered_from_an_expired_record(outage: httpx.Response | Exception) -> None:
    clock, fake = Clock(), Fairsharing([_record("x"), outage])
    client = _client(fake, clock)
    first = client.get_json(URL)
    clock.t += 10_000
    stale = client.get_json(URL)
    assert (stale.origin, stale.value) == (Origin.STALE, {"name": "x"})
    assert stale.checked_at == first.checked_at


def test_an_outage_with_nothing_cached_is_unavailable() -> None:
    client = _client(Fairsharing([DOWN]), Clock())
    with pytest.raises(RegistryUnavailable):
        client.get_json(URL)


def test_a_signed_in_read_does_not_cache_the_token() -> None:
    clock, fake = Clock(), Fairsharing([_record("x")])
    client = _client(fake, clock)
    client.get_json(URL, authorised=True)
    assert fake.asked()[0].headers["Authorization"] == "Bearer t1"
    entry = client._cache.store.get(f"GET {URL}")
    assert entry is not None
    assert b"t1" not in entry.body and "t1" not in entry.key


# --- searches and the token (#330) -------------------------------------------------------------


def _found(*ids: int) -> httpx.Response:
    return httpx.Response(200, json={"data": [{"id": i} for i in ids]})


def test_a_repeated_search_asks_nothing_not_even_a_sign_in() -> None:
    clock, fake = Clock(), Fairsharing([_found(1)])
    client = _client(fake, clock)
    first = client.search({"q": "soil  science", "page[size]": "5"})
    again = client.search({"page[size]": "5", "q": " soil science "})
    assert (first.origin, again.origin) == (Origin.LIVE, Origin.CACHE)
    assert again.value == [{"id": 1}]
    assert fake.signed_in() == 1
    assert len(fake.asked(SEARCH)) == 1


def test_an_expired_search_is_asked_again() -> None:
    clock, fake = Clock(), Fairsharing([_found(1), _found(2)])
    client = _client(fake, clock)
    client.search({"q": "soil"})
    clock.t += 51
    again = client.search({"q": "soil"})
    assert (again.origin, again.value) == (Origin.LIVE, [{"id": 2}])


def test_a_search_outage_is_answered_from_an_expired_search() -> None:
    clock, fake = Clock(), Fairsharing([_found(1), httpx.Response(502)])
    client = _client(fake, clock)
    client.search({"q": "soil"})
    clock.t += 10_000
    stale = client.search({"q": "soil"})
    assert (stale.origin, stale.value) == (Origin.STALE, [{"id": 1}])


def test_a_rejected_token_signs_in_once_more_and_is_sent_again() -> None:
    clock, fake = Clock(), Fairsharing([httpx.Response(401), _found(1)])
    got = _client(fake, clock).search({"q": "soil"})
    assert got.value == [{"id": 1}]
    assert fake.signed_in() == 2
    assert [r.headers["Authorization"] for r in fake.asked(SEARCH)] == ["Bearer t1", "Bearer t2"]


def test_a_token_rejected_twice_is_unavailable() -> None:
    fake = Fairsharing([httpx.Response(401), httpx.Response(401)])
    with pytest.raises(RegistryUnavailable):
        _client(fake, Clock()).search({"q": "soil"})


def test_a_token_is_renewed_before_it_expires() -> None:
    clock = Clock()
    fake = Fairsharing([_found(1), _found(2)], jwts=[_jwt(clock.t + 100), _jwt(clock.t + 10_000)])
    client = _client(fake, clock)
    client.search({"q": "soil"})
    clock.t += 50  # within a minute of expiry
    client.search({"q": "rock"})
    assert fake.signed_in() == 2


def test_a_token_without_an_expiry_is_kept_until_rejected() -> None:
    clock, fake = Clock(), Fairsharing([_found(1), _found(2)], jwts=[_jwt(None)])
    client = _client(fake, clock)
    client.search({"q": "soil"})
    clock.t += 1_000_000
    client.search({"q": "rock"})
    assert fake.signed_in() == 1


def test_token_expiry_reads_the_exp_claim_or_none() -> None:
    assert token_expiry(_jwt(1234.0)) == 1234.0
    assert token_expiry(_jwt(None)) is None
    assert token_expiry("not a jwt") is None


def test_the_search_key_collapses_whitespace_and_orders_filters() -> None:
    assert search_key({"q": " a  b ", "x": "1"}) == search_key({"x": "1", "q": "a b"})


# --- configuration -----------------------------------------------------------------------------


def test_the_cache_is_in_memory_unless_a_directory_is_given(tmp_path: Path) -> None:
    assert cache_from_env({}, "fairsharing").store.path is None
    cache = cache_from_env({CACHE_DIR: str(tmp_path)}, "fairsharing")
    assert cache.store.path == tmp_path / "fairsharing.sqlite3"


def test_times_to_live_come_from_the_environment() -> None:
    assert ttls_from_env({}) == Ttls()
    assert ttls_from_env({TTL_RECORD: "0"}).record == 0
    with pytest.raises(ValueError):
        ttls_from_env({TTL_RECORD: "a week"})
    with pytest.raises(ValueError):
        ttls_from_env({TTL_RECORD: "-1"})


# --- provenance --------------------------------------------------------------------------------


def test_provenance_labels_a_cached_record_and_marks_an_expired_one_stale() -> None:
    clock, fake = Clock(), Fairsharing([_record("x"), DOWN])
    client = _client(fake, clock)
    live = SnapshotRef(label="fairsharing:live")
    with provenance.observed() as origins:
        first = client.get_json(URL)
        provenance.note("FAIRsharing.live", first)
        provenance.note("FAIRsharing.cached", client.get_json(URL))
        clock.t += 10_000
        provenance.note("FAIRsharing.stale", client.get_json(URL))
    fresh = origins.ref("FAIRsharing.live", live)
    cached = origins.ref("FAIRsharing.cached", live)
    stale = origins.ref("FAIRsharing.stale", live)
    assert (fresh.label, fresh.stale) == ("fairsharing:live", False)
    assert (cached.label, cached.stale) == ("fairsharing:cache", False)
    assert (stale.label, stale.stale) == ("fairsharing:cache", True)
    assert stale.retrieved_at == cached.retrieved_at == first.checked_at
    assert origins.ref("FAIRsharing.other", live) is live


def test_notes_outside_an_observed_run_are_dropped() -> None:
    clock = Clock()
    got = _client(Fairsharing([_record("x")]), clock).get_json(URL)
    provenance.note("FAIRsharing.x", got)
    with provenance.observed() as origins:
        pass
    live = SnapshotRef(label="live")
    assert origins.ref("FAIRsharing.x", live) is live


def test_a_record_from_two_answers_takes_the_weaker() -> None:
    clock, fake = Clock(), Fairsharing([_record("x"), _record("y")])
    client = _client(fake, clock)
    cached = client.get_json(URL)
    cached = client.get_json(URL)
    live = client.get_json("https://fairsharing.org/FAIRsharing.y")
    assert live.weakest(cached).origin is Origin.CACHE
    assert provenance.cache_label("live") == "cache"
