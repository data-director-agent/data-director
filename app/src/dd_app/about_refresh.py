"""How often `GET /api/about`, which is open to anyone, retries the agents still missing (#726).

A caller with no session must not make the server read the agents' cards on every request, so the
registry is refreshed at most once per interval, and a request that arrives while another is
refreshing answers from what the registry last saw instead of waiting.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

# How long the server waits between retries of the agents still missing.
ABOUT_REFRESH_INTERVAL_S = 30.0


@dataclass
class AboutRefresh:
    """When the missing agents were last retried, and the clock it reads (a test's own)."""

    interval_s: float = ABOUT_REFRESH_INTERVAL_S
    clock: Callable[[], float] = field(default=time.monotonic, repr=False)
    _refreshed_at: float | None = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def run(self, refresh: Callable[[], None]) -> None:
        """Call `refresh`, unless it was called within the interval or is being called now."""
        if not self._lock.acquire(blocking=False):
            return
        try:
            now = self.clock()
            last = self._refreshed_at
            if last is not None and now - last < self.interval_s:
                return
            # Stamped first, so a refresh that fails is not retried at once either.
            self._refreshed_at = now
            refresh()
        finally:
            self._lock.release()
