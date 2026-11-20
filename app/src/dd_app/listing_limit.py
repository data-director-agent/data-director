"""A limit on the worker threads the listing routes may hold (#1258).

A listing reads and filters stored work before it pages, so its cost grows with what is stored.
Run in the shared AnyIO thread pool (40 threads), a few slow listings take every thread and a
turn, which needs one too, queues behind them (#1255, finding 2). Listings run here in a pool of
their own, so a turn or a run start always has threads, and when more listings are waiting than
the queue allows, the request is answered `503` with `Retry-After` at once rather than after a
wait of minutes.

`DD_APP_LISTING_THREADS` is the most listings that run at once (default 8) and
`DD_APP_LISTING_QUEUE` the most that may wait for one (default 16); `DD_APP_LISTING_RETRY_S` is
the `Retry-After` a refused request is given (default 2 seconds).
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TypeVar

from anyio import CapacityLimiter, to_thread

T = TypeVar("T")

THREADS_VARIABLE = "DD_APP_LISTING_THREADS"
QUEUE_VARIABLE = "DD_APP_LISTING_QUEUE"
RETRY_VARIABLE = "DD_APP_LISTING_RETRY_S"
DEFAULT_THREADS = 8
DEFAULT_QUEUE = 16
DEFAULT_RETRY_S = 2


class ListingConfigError(ValueError):
    """A listing limit that is not a whole number of at least the minimum."""


class ListingBusyError(Exception):
    """Too many listings are waiting; the caller should try again after `retry_after` seconds."""

    def __init__(self, retry_after: int) -> None:
        super().__init__(f"too many listings are waiting; try again in {retry_after} s")
        self.retry_after = retry_after


def _whole(environ: Mapping[str, str], variable: str, default: int, minimum: int) -> int:
    raw = environ.get(variable)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        value = minimum - 1
    if value < minimum:
        raise ListingConfigError(f"{variable} must be a whole number of at least {minimum}")
    return value


@dataclass
class ListingLimiter:
    """Runs a listing in at most `threads` threads of its own, with at most `queue` more
    waiting. A queue of 0 refuses a listing whenever every thread is busy."""

    threads: int = DEFAULT_THREADS
    queue: int = DEFAULT_QUEUE
    retry_after: int = DEFAULT_RETRY_S
    _limiter: CapacityLimiter | None = field(default=None, init=False, repr=False)
    _in_flight: int = field(default=0, init=False, repr=False)

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> ListingLimiter:
        environ = os.environ if environ is None else environ
        return cls(
            threads=_whole(environ, THREADS_VARIABLE, DEFAULT_THREADS, 1),
            queue=_whole(environ, QUEUE_VARIABLE, DEFAULT_QUEUE, 0),
            retry_after=_whole(environ, RETRY_VARIABLE, DEFAULT_RETRY_S, 1),
        )

    async def run(self, work: Callable[[], T]) -> T:
        """`work`, run in a listing thread; raises `ListingBusyError` at once when `threads`
        listings are running and `queue` more are already waiting."""
        if self._limiter is None:
            self._limiter = CapacityLimiter(self.threads)
        if self._in_flight >= self.threads + self.queue:
            raise ListingBusyError(self.retry_after)
        self._in_flight += 1
        try:
            return await to_thread.run_sync(work, limiter=self._limiter)
        finally:
            self._in_flight -= 1
