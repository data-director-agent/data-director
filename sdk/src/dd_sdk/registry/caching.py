"""How an agent's local cache of a live registry route is configured (`dd_registry_cache`).

An agent reads no path outside itself (docs/specs/system.md), so where its cache is kept comes
from its own environment. These say how the agent works, not what it may do, so they are
environment variables rather than profile keys:

- `DD_REGISTRY_CACHE_DIR`: the directory for the agent's cache files. Unset, the cache is kept
  in memory and lasts as long as the agent's process. The systemd unit sets it to the agent's
  `CacheDirectory=`.
- `DD_REGISTRY_CACHE_TTL_RECORD`, `DD_REGISTRY_CACHE_TTL_SEARCH`, `DD_REGISTRY_CACHE_TTL_MISSING`:
  how many seconds a record, a search's results and a "no such record" answer are used without
  asking again. `0` asks every time, but still keeps the answer for when the registry is down.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from dd_registry_cache import Cache, Store, Ttl
from dd_sdk.registry.retrieve import RegistryUnavailable

CACHE_DIR = "DD_REGISTRY_CACHE_DIR"
TTL_RECORD = "DD_REGISTRY_CACHE_TTL_RECORD"
TTL_SEARCH = "DD_REGISTRY_CACHE_TTL_SEARCH"
TTL_MISSING = "DD_REGISTRY_CACHE_TTL_MISSING"

HOUR = 3600.0
DAY = 24 * HOUR


@dataclass(frozen=True)
class Ttls:
    """How long each kind of entry is used without asking, in seconds. The defaults are a first
    choice, to be confirmed against how often the registries change, TODO(#1471)."""

    record: float = 7 * DAY
    search: float = DAY
    missing: float = HOUR

    @property
    def records(self) -> Ttl:
        return Ttl(found=self.record, missing=self.missing)

    @property
    def searches(self) -> Ttl:
        return Ttl(found=self.search, missing=self.missing)


def _seconds(environ: Mapping[str, str], name: str, default: float) -> float:
    raw = environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"{name} must be a number of seconds, not {raw!r}") from None
    if value < 0:
        raise ValueError(f"{name} must not be negative")
    return value


def ttls_from_env(environ: Mapping[str, str]) -> Ttls:
    d = Ttls()
    return Ttls(
        record=_seconds(environ, TTL_RECORD, d.record),
        search=_seconds(environ, TTL_SEARCH, d.search),
        missing=_seconds(environ, TTL_MISSING, d.missing),
    )


def memory_cache(now: Callable[[], float] = time.time) -> Cache:
    """A cache that lasts as long as the process."""
    return Cache(Store(), now=now, unavailable=(RegistryUnavailable,))


def cache_from_env(environ: Mapping[str, str], name: str) -> Cache:
    """The cache file `<DD_REGISTRY_CACHE_DIR>/<name>.sqlite3`, or one in memory if unset."""
    directory = environ.get(CACHE_DIR, "").strip()
    if not directory:
        return memory_cache()
    store = Store(Path(directory) / f"{name}.sqlite3")
    return Cache(store, unavailable=(RegistryUnavailable,))
