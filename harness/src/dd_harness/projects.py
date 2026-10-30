"""The project record: an append-only log of what changed in a project (ADR-0034 decision 2).

A project is a record of its own that outlives any conversation. The harness keeps it under
`DD_PROJECTS_DIR`:

    <project_id>/events.jsonl                one event per line, in the order they happened
    <project_id>/blobs/sha256/<digest>       content an event added, kept once by digest

An event is never changed or removed. Each names whom it acted for and what caused it: the run
or request, or the command a person ran. The run store is separate: conversations are still
derived from it (ADR-0012 decision 4), and the project is not.

What a project holds of its research data is a `FileInventory`, never the files. An inventory is
checked against the core class schema before it is added, and kept as its `dd-input-json-v1`
canonical bytes, so its digest is the input hash the conductor records when an agent is given it.

Only `project_created` and `inventory_added` exist so far; documents (ADR-0035), approvals
(ADR-0036) and membership (ADR-0037) will be events of the same log. Giving an agent the
project's facts, and naming the run that caused an event, is TODO(#394); adding an inventory
from the app is TODO(#395).
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import UUID7_PATTERN, FileInventory, Principal, new_invocation_id, now
from dd_sdk.evidence import INPUT_CANONICALISATION, canonicalise, input_hash

EVENTS_NAME = "events.jsonl"
BLOBS_DIR = ("blobs", "sha256")
PROJECT_CREATED = "project_created"
INVENTORY_ADDED = "inventory_added"
PROJECT_ID = re.compile(UUID7_PATTERN)


class ProjectError(ValueError):
    """The project does not exist, or what was to be added to it was refused."""


class ProjectStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        # Events of one project must go in whole and in order, never interleaved.
        self._lock = threading.Lock()
        self._inventory_schema = ClassSchema.of(FileInventory)

    def create(self, *, acted_for: Principal, caused_by: str) -> str:
        """A new project, and its `project_created` event. Returns its `project_id` (UUIDv7)."""
        project_id = new_invocation_id()
        (self.root / project_id).mkdir()
        self._append(project_id, PROJECT_CREATED, acted_for, caused_by, {})
        return project_id

    def exists(self, project_id: str) -> bool:
        return bool(PROJECT_ID.fullmatch(project_id)) and self._events_path(project_id).is_file()

    def add_inventory(
        self,
        project_id: str,
        inventory: Mapping[str, Any],
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> str:
        """Add a `FileInventory` to the project. Returns its digest.

        Raises `ProjectError` for an unknown project or a document the class schema refuses."""
        self._require(project_id)
        document = dict(inventory)
        errors = self._inventory_schema.errors(document)
        if errors:
            raise ProjectError(f"not a FileInventory: {'; '.join(errors)}")
        digest = input_hash(document)
        self._keep_blob(project_id, digest, canonicalise(document, INPUT_CANONICALISATION))
        files = document.get("inventory_files") or []
        self._append(
            project_id,
            INVENTORY_ADDED,
            acted_for,
            caused_by,
            {
                "digest": digest,
                "canonicalisation": INPUT_CANONICALISATION,
                "file_count": len(files),
                "inventory_made_at": document["inventory_made_at"],
            },
        )
        return digest

    def events(self, project_id: str) -> list[dict[str, Any]]:
        """Every event of the project, oldest first. Raises `ProjectError` for an unknown one."""
        self._require(project_id)
        with self._events_path(project_id).open(encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def inventory(self, project_id: str) -> dict[str, Any] | None:
        """The inventory added last, or None if none has been."""
        added = [e for e in self.events(project_id) if e["event"] == INVENTORY_ADDED]
        if not added:
            return None
        blob = self._blob_path(project_id, added[-1]["digest"])
        data: dict[str, Any] = json.loads(blob.read_bytes())
        return data

    def _require(self, project_id: str) -> None:
        if not self.exists(project_id):
            raise ProjectError(f"no project {project_id!r}")

    def _events_path(self, project_id: str) -> Path:
        return self.root / project_id / EVENTS_NAME

    def _blob_path(self, project_id: str, digest: str) -> Path:
        return self.root.joinpath(project_id, *BLOBS_DIR, digest)

    def _append(
        self,
        project_id: str,
        kind: str,
        acted_for: Principal,
        caused_by: str,
        detail: dict[str, Any],
    ) -> None:
        event = {
            "event": kind,
            "event_id": new_invocation_id(),
            "project_id": project_id,
            "at": now().isoformat(),
            "acted_for": acted_for.model_dump(mode="json", exclude_none=True),
            "caused_by": caused_by,
            **detail,
        }
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
        with self._lock, self._events_path(project_id).open("a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())

    def _keep_blob(self, project_id: str, digest: str, content: bytes) -> None:
        """Write content once, under its digest; content already kept is left as it is."""
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
