"""The cache in front of a registry: answer from a fresh entry, ask the registry otherwise, and
fall back to an expired entry when the registry cannot be asked.

A registry that says `Cache-Control: max-age=0` (re3data and FAIRsharing both do) would leave a
standards-compliant HTTP cache with nothing to reuse, so the time to live here is the caller's
own decision. The caller also says how to ask the registry: `lookup` hands its `fetch` the entry
it holds, if any, so that `fetch` can revalidate it (`If-None-Match`) and answer `NotModified`.

In order, a lookup answers with:

1. the stored entry, if it is younger than its time to live (`Origin.CACHE`), asking nothing;
2. what the registry says (`Origin.LIVE`), or the stored entry confirmed current
   (`Origin.REVALIDATED`);
3. the stored entry however old (`Origin.STALE`), when `fetch` raises one of the exceptions the
   cache was told mean "the registry cannot be asked";
4. otherwise that exception, raised again.

Each lookup is logged on the `dd_registry_cache` logger, so hits and misses can be counted.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum

from dd_registry_cache.store import Entry, Store

log = logging.getLogger("dd_registry_cache")


class Origin(StrEnum):
    """Where an answer came from."""

    LIVE = "live"
    CACHE = "cache"
    REVALIDATED = "revalidated"
    STALE = "stale"


@dataclass(frozen=True)
class Fresh:
    """The registry's answer: the body to store, its media type and its validator, if any."""

    body: bytes
    content_type: str = ""
    etag: str | None = None


@dataclass(frozen=True)
class Missing:
    """The registry has no such record. It is stored too, under its own time to live."""


@dataclass(frozen=True)
class NotModified:
    """The registry confirmed the stored entry is current (HTTP 304)."""


type Fetch = Callable[[Entry | None], Fresh | Missing | NotModified]


@dataclass(frozen=True)
class Ttl:
    """How long, in seconds, an entry is answered without asking: one that holds a record, and
    one that says there is none. Zero asks every time, but still keeps the answer for an
    outage."""

    found: float
    missing: float

    def of(self, entry: Entry) -> float:
        return self.missing if entry.missing else self.found


@dataclass(frozen=True)
class Answer:
    """One lookup's answer. `body` is None when the registry has no such record. `checked_at`
    is when the registry last sent or confirmed it, in POSIX seconds."""

    body: bytes | None
    content_type: str
    checked_at: float
    origin: Origin

    @property
    def missing(self) -> bool:
        return self.body is None


def _answer(entry: Entry, origin: Origin) -> Answer:
    body = None if entry.missing else entry.body
    return Answer(body, entry.content_type, entry.checked_at, origin)


class Cache:
    def __init__(
        self,
        store: Store | None = None,
        *,
        now: Callable[[], float] = time.time,
        unavailable: tuple[type[BaseException], ...] = (OSError,),
    ) -> None:
        self.store = store or Store()
        self.now = now
        self.unavailable = unavailable

    def lookup(self, key: str, ttl: Ttl, fetch: Fetch) -> Answer:
        entry = self.store.get(key)
        if entry is not None and self.now() - entry.checked_at < ttl.of(entry):
            log.debug("hit %s", key)
            return _answer(entry, Origin.CACHE)
        try:
            got = fetch(entry)
        except self.unavailable as exc:
            if entry is None:
                raise
            log.info("stale %s: %s", key, exc)
            return _answer(entry, Origin.STALE)
        at = self.now()
        if isinstance(got, NotModified):
            if entry is None:
                raise ValueError(f"{key}: NotModified with nothing stored to revalidate")
            self.store.touch(key, at)
            log.debug("revalidated %s", key)
            return _answer(replace(entry, checked_at=at), Origin.REVALIDATED)
        if isinstance(got, Missing):
            new = Entry(
                key,
                missing=True,
                body=b"",
                content_type="",
                etag=None,
                fetched_at=at,
                checked_at=at,
            )
        else:
            new = Entry(
                key,
                missing=False,
                body=got.body,
                content_type=got.content_type,
                etag=got.etag,
                fetched_at=at,
                checked_at=at,
            )
        self.store.put(new)
        log.debug("miss %s", key)
        return _answer(new, Origin.LIVE)
