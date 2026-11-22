"""People's names from their public ORCID records, for a page to show (docs/specs/projects.md,
Roles).

A project keeps no name for a member, only the identifier they sign in with. A page that lists
members shows each one by the name on their public ORCID record instead, read from ORCID's public
API when the page asks (`dd_harness.orcid.fetch_public_name`). The name is held here, in memory,
for at most `KEPT_S`, so that opening the page again does not ask ORCID again; it is never written
to the project's log and never given to an agent.

A page must not wait on ORCID: `PublicNames.names` asks for every name it does not hold at once
and gives up on those not answered within its deadline, leaving them unnamed. A name ORCID could
not give, because it is private, unknown or ORCID failed, is remembered as none for `MISSED_S`.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, wait
from typing import Final

import httpx

from dd_harness.orcid import OrcidUnavailableError, fetch_public_name, name_url

KEPT_S: Final = 3600.0
MISSED_S: Final = 300.0
DEADLINE_S: Final = 3.0
HELD: Final = 1024
WORKERS: Final = 8


class PublicNames:
    """Public ORCID names, held in memory for a short time. Safe to share between threads."""

    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        deadline_s: float = DEADLINE_S,
    ) -> None:
        self._transport = transport
        self._clock = clock
        self._deadline_s = deadline_s
        self._held: OrderedDict[str, tuple[float, str | None]] = OrderedDict()
        self._lock = threading.Lock()

    def names(self, principal_ids: Iterable[str]) -> dict[str, str]:
        """The public name of each of `principal_ids` that has one and could be read in time."""
        wanted = list(dict.fromkeys(p for p in principal_ids if name_url(p) is not None))
        found, missing = self._held_names(wanted)
        if missing:
            found.update(self._read(missing))
        return found

    def _held_names(self, wanted: list[str]) -> tuple[dict[str, str], list[str]]:
        now = self._clock()
        found: dict[str, str] = {}
        missing: list[str] = []
        with self._lock:
            for principal_id in wanted:
                held = self._held.get(principal_id)
                if held is None or held[0] <= now:
                    missing.append(principal_id)
                elif held[1] is not None:
                    found[principal_id] = held[1]
        return found, missing

    def _read(self, principal_ids: list[str]) -> dict[str, str]:
        pool = ThreadPoolExecutor(max_workers=min(WORKERS, len(principal_ids)))
        futures = {pool.submit(self._fetch, p): p for p in principal_ids}
        done, _ = wait(futures, timeout=self._deadline_s)
        pool.shutdown(wait=False, cancel_futures=True)
        found: dict[str, str] = {}
        for future in done:
            name = future.result()
            if name is not None:
                found[futures[future]] = name
        return found

    def _fetch(self, principal_id: str) -> str | None:
        try:
            name = fetch_public_name(principal_id, transport=self._transport)
        except OrcidUnavailableError:
            name = None
        self._hold(principal_id, name)
        return name

    def _hold(self, principal_id: str, name: str | None) -> None:
        until = self._clock() + (KEPT_S if name is not None else MISSED_S)
        with self._lock:
            self._held[principal_id] = (until, name)
            self._held.move_to_end(principal_id)
            while len(self._held) > HELD:
                self._held.popitem(last=False)
