"""Each conversation's turn lock, held where its turns are stored (docs/specs/storage.md, "Turn
locks").

A conversation's turn reads its history, runs the orchestrator and stores the turn; a second
turn of the same conversation in that time would be shown a history without the first, and the
conversation would fork (docs/specs/orchestration.md, invariant 4). The app holds the
conversation's lock from reading the history until the turn is stored, and refuses a turn whose
lock is held. The lock is the store's, not the app process's, so two app processes over one store
are held to one turn at a time as one process is.

`conversation_locks` (`dd_harness.settings`) opens the locks beside the runs that `DD_RUNS_DIR`
names: `FileConversationLocks` on files, `dd_harness.postgres.locks.PostgresConversationLocks` on
PostgreSQL. `LocalConversationLocks` holds within one process only, for an app built without a
store location, as in a test. `dd_harness.testing.check_conversation_locks` holds a backend to the
guarantees below.
"""

from __future__ import annotations

import fcntl
import hashlib
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

type Release = Callable[[], None]

LOCKS_DIR = "locks"


class ConversationLocks(Protocol):
    """A lock per conversation that a turn holds while it runs.

    A backend keeps these guarantees:

    1. One holder per conversation. While a conversation's lock is held, `try_hold` on any
       instance over the same location, in any process, returns None at once; nothing waits.
    2. Conversations are independent: holding one conversation's lock holds no other's.
    3. A released lock may be held again, through any instance. Releasing twice does nothing.
    4. A holder that ends without releasing (its process exits, its connection drops) releases
       its locks, so a crashed turn never leaves its conversation refused for good.
    5. A conversation id never reaches anything outside the store as a name; one that is
       malformed is a lock like any other.
    """

    def try_hold(self, conversation_id: str) -> Release | None:
        """Hold `conversation_id`'s lock and return what releases it, or None if it is held."""
        ...


def _once(release: Callable[[], None]) -> Release:
    """`release`, run at most once however often it is called (guarantee 3)."""
    done = threading.Lock()

    def released() -> None:
        if done.acquire(blocking=False):
            release()

    return released


class FileConversationLocks:
    """Locks kept as files under `<root>/locks/`, one per conversation, named by the SHA-256 of its
    id. Each is held with `flock`, which belongs to the open file and not to the process, so it
    holds between processes and between two instances in one process alike; the system releases
    it when the holder's process ends. A lock file is never removed: removing one while another
    holder opens it would let two hold it."""

    def __init__(self, root: Path) -> None:
        self._dir = root / LOCKS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    def try_hold(self, conversation_id: str) -> Release | None:
        name = hashlib.sha256(conversation_id.encode()).hexdigest()
        fd = os.open(self._dir / f"{name}.lock", os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            return None
        except BaseException:
            os.close(fd)
            raise
        return _once(lambda: os.close(fd))  # closing the file releases its lock


class LocalConversationLocks:
    """Locks held within this process alone. They keep guarantees 1 to 5 only among the turns of
    one process, so they serve an app built without a store location (a test), never a
    deployment."""

    def __init__(self) -> None:
        self._held: set[str] = set()
        self._guard = threading.Lock()

    def try_hold(self, conversation_id: str) -> Release | None:
        with self._guard:
            if conversation_id in self._held:
                return None
            self._held.add(conversation_id)

        def release() -> None:
            with self._guard:
                self._held.discard(conversation_id)

        return _once(release)

    def held(self) -> frozenset[str]:
        """The conversations whose locks are held now."""
        with self._guard:
            return frozenset(self._held)
