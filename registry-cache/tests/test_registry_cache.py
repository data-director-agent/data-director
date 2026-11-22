"""dd_registry_cache: a fresh entry answers without asking, an expired one is asked again or
revalidated, and an outage is answered from an expired entry."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from dd_registry_cache import Cache, Entry, Fresh, Missing, NotModified, Origin, Store, Ttl
from dd_registry_cache.cli import main

TTL = Ttl(found=100.0, missing=10.0)


class DownError(Exception):
    pass


@dataclass
class Clock:
    t: float = 1000.0

    def __call__(self) -> float:
        return self.t


@dataclass
class Registry:
    """A fake registry: answers in turn, recording what each call was given."""

    answers: list[Fresh | Missing | NotModified | Exception]
    given: list[Entry | None] = field(default_factory=list)

    def __call__(self, entry: Entry | None) -> Fresh | Missing | NotModified:
        self.given.append(entry)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def _cache(clock: Clock, store: Store | None = None) -> Cache:
    return Cache(store or Store(), now=clock, unavailable=(DownError,))


def test_a_miss_asks_and_a_fresh_entry_does_not() -> None:
    clock, registry = Clock(), Registry([Fresh(b"one", "application/json", '"e1"')])
    cache = _cache(clock)
    first = cache.lookup("k", TTL, registry)
    clock.t += 50
    second = cache.lookup("k", TTL, registry)
    assert first.origin is Origin.LIVE
    assert second.origin is Origin.CACHE
    assert second.body == first.body == b"one"
    assert second.checked_at == first.checked_at
    assert len(registry.given) == 1


def test_an_expired_entry_is_asked_again_and_replaced() -> None:
    clock, registry = Clock(), Registry([Fresh(b"one"), Fresh(b"two")])
    cache = _cache(clock)
    cache.lookup("k", TTL, registry)
    clock.t += 101
    again = cache.lookup("k", TTL, registry)
    assert again.origin is Origin.LIVE
    assert again.body == b"two"
    assert again.checked_at == clock.t
    assert registry.given[1] is not None


def test_not_modified_keeps_the_body_and_resets_the_clock() -> None:
    clock = Clock()
    registry = Registry([Fresh(b"one", etag='W/"e1"'), NotModified()])
    cache = _cache(clock)
    cache.lookup("k", TTL, registry)
    clock.t += 101
    again = cache.lookup("k", TTL, registry)
    assert again.origin is Origin.REVALIDATED
    assert again.body == b"one"
    assert again.checked_at == clock.t
    previous = registry.given[1]
    assert previous is not None and previous.etag == 'W/"e1"'
    clock.t += 50
    assert cache.lookup("k", TTL, registry).origin is Origin.CACHE


def test_not_found_is_kept_under_its_own_time_to_live() -> None:
    clock, registry = Clock(), Registry([Missing(), Missing()])
    cache = _cache(clock)
    assert cache.lookup("k", TTL, registry).missing
    clock.t += 5
    assert cache.lookup("k", TTL, registry).origin is Origin.CACHE
    clock.t += 6
    assert cache.lookup("k", TTL, registry).origin is Origin.LIVE
    assert len(registry.given) == 2


def test_an_outage_is_answered_from_an_expired_entry() -> None:
    clock, registry = Clock(), Registry([Fresh(b"one"), DownError("no route")])
    cache = _cache(clock)
    first = cache.lookup("k", TTL, registry)
    clock.t += 1000
    stale = cache.lookup("k", TTL, registry)
    assert stale.origin is Origin.STALE
    assert stale.body == b"one"
    assert stale.checked_at == first.checked_at


def test_an_outage_with_nothing_stored_is_raised() -> None:
    cache = _cache(Clock())
    with pytest.raises(DownError):
        cache.lookup("k", TTL, Registry([DownError("no route")]))
    assert cache.store.count() == 0


def test_an_unexpected_error_is_not_answered_from_the_cache() -> None:
    clock, registry = Clock(), Registry([Fresh(b"one"), ValueError("bug")])
    cache = _cache(clock)
    cache.lookup("k", TTL, registry)
    clock.t += 1000
    with pytest.raises(ValueError):
        cache.lookup("k", TTL, registry)


def test_a_zero_time_to_live_asks_every_time_but_keeps_the_answer_for_an_outage() -> None:
    clock = Clock()
    registry = Registry([Fresh(b"one"), Fresh(b"two"), DownError("no route")])
    cache = _cache(clock)
    zero = Ttl(found=0, missing=0)
    cache.lookup("k", zero, registry)
    assert cache.lookup("k", zero, registry).origin is Origin.LIVE
    assert cache.lookup("k", zero, registry).origin is Origin.STALE


def test_a_file_store_survives_a_reopen(tmp_path: Path) -> None:
    clock, path = Clock(), tmp_path / "cache" / "fairsharing.sqlite3"
    _cache(clock, Store(path)).lookup("k", TTL, Registry([Fresh(b"one")]))
    again = _cache(clock, Store(path)).lookup("k", TTL, Registry([]))
    assert again.origin is Origin.CACHE
    assert again.body == b"one"


def test_clear_removes_all_or_a_prefix(tmp_path: Path) -> None:
    store = Store(tmp_path / "c.sqlite3")
    cache = _cache(Clock(), store)
    for key in ("GET a", "GET b", "POST s"):
        cache.lookup(key, TTL, Registry([Fresh(b"x")]))
    assert store.clear("GET ") == 2
    assert store.count() == 1
    assert store.clear() == 1
    assert store.count() == 0


def test_the_command_clears_a_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "c.sqlite3"
    _cache(Clock(), Store(path)).lookup("GET a", TTL, Registry([Fresh(b"x")]))
    assert main(["clear", str(path)]) == 0
    assert Store(path).count() == 0
    assert main(["clear", str(tmp_path / "absent.sqlite3")]) == 1
    capsys.readouterr()
