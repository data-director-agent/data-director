"""The file backend of `ProjectLog` (`dd_harness.storage`, docs/specs/storage.md).

It keeps each project under its root:

    <project_id>/events.jsonl                one event per line, in the order they happened
    <project_id>/blobs/sha256/<digest>       content an event added, kept once by digest

It stores and reads, and decides nothing: the project rules are `dd_harness.projects.Projects`,
which works over any `ProjectLog`. Its exclusive section is a lock per project, which holds within
one harness process only.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from dd_sdk.contract.models import UUID7_PATTERN

EVENTS_NAME = "events.jsonl"
BLOBS_DIR = ("blobs", "sha256")
_PROJECT_ID = re.compile(UUID7_PATTERN)
_DIGEST = re.compile(r"[0-9a-f]{64}")
_CONVERSATION_STARTED = "conversation_started"


class FileSection:
    """A project's exclusive section in the file log: its lock is held while the section is."""

    def __init__(self, log: FileProjectLog, project_id: str) -> None:
        self._log = log
        self._project_id = project_id

    def events(self) -> list[dict[str, Any]]:
        return self._log.events(self._project_id)

    def append(self, events: list[dict[str, Any]]) -> None:
        self._log._write(self._project_id, events)


class FileProjectLog:
    """Each project's log and blobs under `root`. `root` belongs to this backend, for tests of
    its layout."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        # Events of one project go in whole and in order, never interleaved, and a reader never
        # sees half of one. Each project has its own lock, so projects do not wait on each other.
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()
        # The project of each conversation found so far. A conversation's project never changes
        # once recorded, so only what was found is kept; one not found is looked for again, in
        # case another log over the same root has started it since (docs/specs/storage.md,
        # invariant 12). Each miss reads every log, TODO(#524).
        self._conversations: dict[str, str] = {}
        self._conversations_guard = threading.Lock()

    def create(self, project_id: str, event: dict[str, Any]) -> None:
        if not _PROJECT_ID.fullmatch(project_id):
            raise ValueError(f"{project_id!r} is not a project identifier")
        (self.root / project_id).mkdir()
        self._write(project_id, [event])

    def exists(self, project_id: str) -> bool:
        return bool(_PROJECT_ID.fullmatch(project_id)) and self._events_path(project_id).is_file()

    def events(self, project_id: str) -> list[dict[str, Any]]:
        self._require(project_id)
        # Under the project's lock, so that an append being written is never read in part.
        with self._lock(project_id), self._events_path(project_id).open(encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    @contextmanager
    def section(self, project_id: str) -> Iterator[FileSection]:
        self._require(project_id)
        with self._lock(project_id):
            yield FileSection(self, project_id)

    def keep_blob(self, project_id: str, digest: str, content: bytes) -> None:
        """Write content once, under its digest; content already kept is left as it is."""
        self._require(project_id)
        if not _DIGEST.fullmatch(digest):
            raise ValueError("a digest is a SHA-256 in lower-case hex")
        path = self._blob_path(project_id, digest)
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        # Written aside and moved into place, so a reader never sees half a blob.
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(content)
            Path(tmp).replace(path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def blob(self, project_id: str, digest: str) -> bytes | None:
        if not self.exists(project_id) or not _DIGEST.fullmatch(digest):
            return None
        path = self._blob_path(project_id, digest)
        return path.read_bytes() if path.is_file() else None

    def project_of(self, conversation_id: str) -> str | None:
        with self._conversations_guard:
            found = self._conversations.get(conversation_id)
        if found is not None:
            return found
        for path in self.root.glob(f"*/{EVENTS_NAME}"):
            project_id = path.parent.name
            if not self.exists(project_id):
                continue
            for event in self.events(project_id):
                if (
                    event["event"] == _CONVERSATION_STARTED
                    and event["conversation_id"] == conversation_id
                ):
                    with self._conversations_guard:
                        self._conversations[conversation_id] = project_id
                    return project_id
        return None

    def project_ids(self) -> list[str]:
        # UUIDv7s sort by the time they were made, so this is the order the projects were created.
        return sorted(
            path.name for path in self.root.iterdir() if path.is_dir() and self.exists(path.name)
        )

    def _require(self, project_id: str) -> None:
        if not self.exists(project_id):
            raise KeyError(project_id)

    def _lock(self, project_id: str) -> threading.RLock:
        with self._locks_guard:
            return self._locks.setdefault(project_id, threading.RLock())

    def _events_path(self, project_id: str) -> Path:
        return self.root / project_id / EVENTS_NAME

    def _blob_path(self, project_id: str, digest: str) -> Path:
        return self.root.joinpath(project_id, *BLOBS_DIR, digest)

    def _write(self, project_id: str, events: list[dict[str, Any]]) -> None:
        """Append `events` in one write, flushed to disk before returning, so that events made
        together, such as an edit and its approval, go in together."""
        text = "".join(
            json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n" for event in events
        )
        path = self._events_path(project_id)
        with self._lock(project_id), path.open("a", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
