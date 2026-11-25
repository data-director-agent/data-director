"""A cache in front of the registries' APIs, and the offline mode that answers from it alone.

Found records and misses are kept, keyed by registry and normalised identifier, each for its own
time to live; an error is never kept (`dd_registry_cache`). A record is stored as its document, in
canonical JSON, and read back through its model, so a cached record is the same document as a
fresh one and hashes the same.

When a registry cannot be asked, an expired entry answers and says so. Offline
(`DD_PID_OFFLINE=1`), no registry is asked: any entry answers, and an identifier with none is
unavailable, never not found.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from dd_mcp_pid.http import UnavailableError
from dd_registry_cache import Cache, Fresh, Missing, Origin, Store, Ttl

HOUR = 3600.0
DAY = 24 * HOUR
# A first choice, to be confirmed against how often the registries change, TODO(#1471).
DEFAULT_TTL = Ttl(found=7 * DAY, missing=HOUR)
CACHE_FILE = "pid.sqlite3"


class OfflineError(UnavailableError):
    """The server is offline and holds no answer for this identifier."""


class Record(Protocol):
    def document(self) -> dict[str, Any]: ...


class RecordModel[R: Record](Protocol):
    def model_validate_json(self, data: bytes) -> R: ...


def _when(at: float) -> str:
    return datetime.fromtimestamp(at, UTC).strftime("%Y-%m-%d %H:%M UTC")


@dataclass(frozen=True)
class Lookups:
    """Every registry's cache, in one store. `offline` asks no registry."""

    cache: Cache = field(default_factory=lambda: Cache(Store(), unavailable=(UnavailableError,)))
    ttl: Ttl = DEFAULT_TTL
    offline: bool = False

    def get[R: Record](
        self, registry: str, key: str, model: RecordModel[R], fetch: Callable[[], R | None]
    ) -> tuple[R | None, str]:
        """The record (None when the registry has none) and where it came from: empty when the
        registry was asked, otherwise a phrase naming the cache. Raises `UnavailableError` when
        the registry cannot be asked and nothing is cached."""

        def ask(_entry: object) -> Fresh | Missing:
            if self.offline:
                raise OfflineError(
                    f"{registry}: {key} is not in the cache, and this server is offline "
                    "(DD_PID_OFFLINE), so it was not asked"
                )
            record = fetch()
            if record is None:
                return Missing()
            body = json.dumps(record.document(), sort_keys=True, ensure_ascii=False)
            return Fresh(body.encode("utf-8"), "application/json")

        answer = self.cache.lookup(f"{registry.lower()} {key}", self.ttl, ask)
        found = None if answer.body is None else model.model_validate_json(answer.body)
        checked = _when(answer.checked_at)
        if answer.origin is Origin.CACHE:
            return found, f"from the cache (checked {checked})"
        if answer.origin is Origin.STALE:
            why = "offline" if self.offline else f"{registry} cannot be asked"
            return found, f"from the cache, expired (checked {checked}; {why})"
        return found, ""


def lookups(
    directory: Path | None,
    ttl: Ttl = DEFAULT_TTL,
    *,
    offline: bool = False,
    now: Callable[[], float] = time.time,
) -> Lookups:
    """The cache in `directory/pid.sqlite3`, or in memory for the life of the process."""
    store = Store(directory / CACHE_FILE if directory else None)
    return Lookups(Cache(store, now=now, unavailable=(UnavailableError,)), ttl, offline)
