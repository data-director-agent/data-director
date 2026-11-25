"""How many turns are running now, so that a deployment can wait for them (`GET /server-status`,
deploy/deploy.sh)."""

from __future__ import annotations

import threading
from collections.abc import Callable

from dd_harness.turn_locks import Release


class ActiveTurns:
    """A count of the turns holding a conversation's turn lock in this process."""

    def __init__(self) -> None:
        self._count = 0
        self._guard = threading.Lock()

    @property
    def count(self) -> int:
        return self._count

    def hold(self, release: Release) -> Callable[[], None]:
        """Count a turn from now until the returned release, which gives up `release`, is called.
        `release` is once-only already (`ConversationLocks.try_hold`), so a second call counts
        nothing more."""
        with self._guard:
            self._count += 1
        released = threading.Event()

        def done() -> None:
            try:
                release()
            finally:
                with self._guard:
                    if not released.is_set():
                        released.set()
                        self._count -= 1

        return done
