"""The pool of connections a PostgreSQL store keeps, and how a store recovers a dropped one."""

from __future__ import annotations

import functools
import weakref
from collections.abc import Callable
from typing import Any, Concatenate, Self

import psycopg
from psycopg_pool import ConnectionPool

# The most connections one store keeps, unless `DD_POSTGRES_POOL_SIZE` says otherwise.
DEFAULT_POOL_SIZE = 10

type Pool = ConnectionPool[psycopg.Connection[Any]]


def connect(owner: object, location: str, where: str, size: int) -> Pool:
    """A pool of at most `size` connections to `location`, closed when `owner` is collected or the
    process ends. A borrow makes no round trip: a connection the server dropped (a restart) is
    found when it is used, replaced by the pool, and a read is retried once on a fresh one
    (`recovering`). The pool is named by `where`, which holds no credential, so its log records
    hold none either."""
    if size < 1:
        raise ValueError(f"a pool holds at least one connection, not {size}")
    pool: Pool = ConnectionPool(
        location,
        min_size=1,
        max_size=size,
        open=True,
        name=where,
    )
    weakref.finalize(owner, pool.close)
    return pool


def recovering[S: Pooled, **P, R](
    read: Callable[Concatenate[S, P], R],
) -> Callable[Concatenate[S, P], R]:
    """Run a read again, once, if its connection turns out to be broken. The pool does not check a
    connection as it is borrowed, so one the server dropped fails on first use. The store then
    checks every connection the pool holds, which discards the broken ones (a restart drops them
    all), and the second attempt is given a good one or a new one. Only reads are repeated: a
    write that failed while committing may have been kept."""

    def attempt(self: S, /, *args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return read(self, *args, **kwargs)
        except psycopg.OperationalError:
            self._pool.check()
            return read(self, *args, **kwargs)

    functools.update_wrapper(attempt, read)
    return attempt


class Pooled:
    """What both stores share: a pool, released by `close` or at the end of a `with` block."""

    _pool: Pool

    @property
    def pool_size(self) -> int:
        """The most connections the store keeps open at once."""
        return self._pool.max_size

    def close(self) -> None:
        """Close the store's connections. A call after this raises."""
        self._pool.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
