"""Which copy answered for each record a run read from a live registry route: the registry
itself, a local cached copy, or an expired cached copy served because the registry could not be
asked (docs/specs/grounding.md).

The live route notes each record it returns (`note`); the agent opens one `Provenance` for its
run (`observed`) and asks it for each record's `SnapshotRef` when it writes the evidence. The
notes are kept in a context variable, so the backends an agent shares between runs keep their
signatures, and concurrent runs, each in its own context, never see one another's notes.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from dd_registry_cache import Answer, Origin
from dd_sdk.registry.retrieve import SnapshotRef

CACHED_NOTE = "served from the local cache of the live route"
STALE_NOTE = "the registry could not be asked; served from an expired copy in the local cache"

# How much each origin can be trusted to be current, weakest first.
_STRENGTH = {Origin.STALE: 0, Origin.CACHE: 1, Origin.REVALIDATED: 2, Origin.LIVE: 3}


@dataclass(frozen=True)
class Fetched[T]:
    """A value read through the cache, with when the registry last sent or confirmed it and
    where this answer came from."""

    value: T
    checked_at: datetime
    origin: Origin

    @classmethod
    def of(cls, value: T, answer: Answer) -> Fetched[T]:
        return cls(value, datetime.fromtimestamp(answer.checked_at, UTC), answer.origin)

    def weakest(self, other: Fetched[Any]) -> Fetched[T]:
        """This value, under the weaker of two answers' origins and the older of their times:
        for a record assembled from two requests."""
        origin = min(self.origin, other.origin, key=_STRENGTH.__getitem__)
        return replace(self, origin=origin, checked_at=min(self.checked_at, other.checked_at))


def cache_label(live: str) -> str:
    """The label of the cache in front of a live route: `fairsharing:live` → `fairsharing:cache`,
    `live` → `cache`."""
    return live.removesuffix("live") + "cache" if live.endswith("live") else f"{live}:cache"


def snapshot_ref(fetched: Fetched[Any], live: SnapshotRef) -> SnapshotRef:
    """The `SnapshotRef` of one answer from the live route labelled `live`. A record the
    registry sent in this run keeps that label; one from the cache, confirmed or not, takes the
    cache's, marked stale when it was served because the registry could not be asked."""
    if fetched.origin is Origin.LIVE:
        return replace(live, retrieved_at=fetched.checked_at)
    stale = fetched.origin is Origin.STALE
    return SnapshotRef(
        label=cache_label(live.label),
        stale=stale,
        fetched_at=fetched.checked_at.isoformat(timespec="seconds"),
        notes=[STALE_NOTE if stale else CACHED_NOTE],
        retrieved_at=fetched.checked_at,
    )


class Provenance:
    """One run's notes: for each record id, the first answer it was read from."""

    def __init__(self) -> None:
        self._notes: dict[str, Fetched[Any]] = {}

    def note(self, record_id: str, fetched: Fetched[Any]) -> None:
        self._notes.setdefault(record_id, fetched)

    def ref(self, record_id: str, live: SnapshotRef) -> SnapshotRef:
        """The record's `SnapshotRef`, if the live route labelled `live` noted it; else `live`."""
        fetched = self._notes.get(record_id)
        return live if fetched is None else snapshot_ref(fetched, live)


_CURRENT: ContextVar[Provenance | None] = ContextVar("dd_registry_provenance", default=None)


@contextmanager
def observed(provenance: Provenance | None = None) -> Iterator[Provenance]:
    """Collect the notes the live routes make while the block runs."""
    seen = provenance if provenance is not None else Provenance()
    token = _CURRENT.set(seen)
    try:
        yield seen
    finally:
        _CURRENT.reset(token)


def note(record_id: str, fetched: Fetched[Any]) -> None:
    """Note where a record came from, for the run being observed, if any."""
    seen = _CURRENT.get()
    if seen is not None:
        seen.note(record_id, fetched)
