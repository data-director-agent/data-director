"""The file backend of `RunStorage` (`dd_harness.storage`, docs/specs/storage.md): an append-only
JSONL index of envelopes, plus a directory per invocation.

    invocations.jsonl                   every envelope, one per line, in the order stored
    <invocation_id>/envelope.json       the envelope
    <invocation_id>/request.json        the request
    <invocation_id>/prompts.json        the prompts its model calls sent
    <invocation_id>/<artifact>          spans.jsonl, grounding.txt, sources.txt, crate/...
    schemas/<digest>.json               each class schema, once

UUIDv7 identifiers mean the file is chronologically ordered as written and needs no index. A run
is written once: `append` refuses an `invocation_id` whose envelope is already stored, and the
conductor refuses such a request before it runs (`DuplicateInvocation`).

Each class schema a run was checked against is kept once, addressed by its digest, in
`schemas/<digest>.json` (docs/specs/contract.md). An envelope names the digests, so a stored run is
shown with the schema it was checked against, whatever its agent's card says now.

The prompts a run sent to a model are kept beside its envelope in `prompts.json`, keyed by their
`dd-prompt-json-v1` digest (docs/specs/disclosure.md). The envelope names them by digest only; a
prompt may hold what a researcher wrote, so whoever may read the run may read it, and nothing that
leaves the store (the envelope, the trace, the crate) carries it.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any

from dd_sdk.contract.classes import ClassSchema

INDEX_NAME = "invocations.jsonl"
PROMPTS_NAME = "prompts.json"
SCHEMAS_DIR = "schemas"
DIGEST = re.compile(r"[0-9a-f]{64}")
# What may name a run's directory: letters, digits and hyphens, as a UUIDv7 is written.
RUN_ID = re.compile(r"[0-9A-Za-z][0-9A-Za-z-]*")
# An artifact is a relative path of plain segments, so it stays inside its run's directory.
ARTIFACT_SEGMENT = re.compile(r"[0-9A-Za-z_][0-9A-Za-z._-]*")
# The run's own files, which only `append` writes.
RESERVED = frozenset({"envelope.json", "request.json", PROMPTS_NAME})


class RunStore:
    """Runs kept as files under `root`. `root` and `run_dir` belong to this backend, for tests of
    its layout; every other caller reaches a run through `RunStorage`."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        # Runs finish side by side; each index line must go in whole, never interleaved.
        self._index_lock = threading.Lock()

    @property
    def index(self) -> Path:
        return self.root / INDEX_NAME

    def run_dir(self, invocation_id: str) -> Path:
        d = self.root / invocation_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def has(self, invocation_id: str) -> bool:
        path = self._read(invocation_id, "envelope.json")
        return path is not None and path.exists()

    def append(
        self,
        envelope: dict[str, Any],
        request: dict[str, Any] | None = None,
        schemas: Iterable[ClassSchema] = (),
        prompts: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> None:
        """Store one envelope, each class schema it was checked against under its digest, and the
        prompts its model calls name. Raises FileExistsError if its `invocation_id` is already
        stored."""
        for schema in schemas:
            self._keep_schema(schema)
        run_dir = self.run_dir(envelope["invocation_id"])
        with (run_dir / "envelope.json").open("x", encoding="utf-8") as fh:
            fh.write(json.dumps(envelope, indent=2))
        if request is not None:
            (run_dir / "request.json").write_text(json.dumps(request, indent=2), encoding="utf-8")
        if prompts:
            (run_dir / PROMPTS_NAME).write_text(
                json.dumps({k: dict(v) for k, v in prompts.items()}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        line = json.dumps(envelope, separators=(",", ":")) + "\n"
        with self._index_lock, self.index.open("a", encoding="utf-8") as fh:
            fh.write(line)

    def iter_envelopes(self, *, conversation_id: str | None = None) -> Iterator[dict[str, Any]]:
        """Every envelope in the order stored; with `conversation_id`, only that conversation's.
        The filter reads the whole index, TODO(#524)."""
        if not self.index.exists():
            return
        with self.index.open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                envelope: dict[str, Any] = json.loads(line)
                if conversation_id is None or envelope.get("conversation_id") == conversation_id:
                    yield envelope

    def get(self, invocation_id: str) -> dict[str, Any] | None:
        return _read_json(self._read(invocation_id, "envelope.json"))

    def get_request(self, invocation_id: str) -> dict[str, Any] | None:
        return _read_json(self._read(invocation_id, "request.json"))

    def get_prompts(self, invocation_id: str) -> dict[str, Any]:
        """The prompts a stored run sent, keyed by digest; empty if it sent none."""
        return _read_json(self._read(invocation_id, PROMPTS_NAME)) or {}

    def _read(self, invocation_id: str, name: str) -> Path | None:
        """One of the run's own files, or None if the identifier is malformed, so that no path
        outside the store can be read."""
        if not RUN_ID.fullmatch(invocation_id):
            return None
        return self.root / invocation_id / name

    def put_artifact(self, invocation_id: str, name: str, data: bytes) -> None:
        """Keep `data` as `<invocation_id>/<name>`. Raises `KeyError` for a run not stored,
        `ValueError` for a malformed name and `FileExistsError` for an artifact already kept."""
        path = self._artifact_path(invocation_id, name)
        if path is None:
            raise ValueError(f"not an artifact name: {name!r}")
        if not self.has(invocation_id):
            raise KeyError(invocation_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as fh:
            fh.write(data)

    def get_artifact(self, invocation_id: str, name: str) -> bytes | None:
        """The artifact kept as `<invocation_id>/<name>`, or None. A malformed name names
        nothing, so no path outside the store can be read."""
        path = self._artifact_path(invocation_id, name)
        if path is None or not path.is_file():
            return None
        return path.read_bytes()

    def where(self, invocation_id: str) -> str:
        """The run's directory."""
        return str(self.root / invocation_id)

    def _artifact_path(self, invocation_id: str, name: str) -> Path | None:
        """Where an artifact is kept, or None if either name is malformed or the name is one of
        the run's own files."""
        segments = name.split("/")
        if (
            not RUN_ID.fullmatch(invocation_id)
            or name in RESERVED
            or not all(ARTIFACT_SEGMENT.fullmatch(s) for s in segments)
        ):
            return None
        return self.root.joinpath(invocation_id, *segments)

    def _keep_schema(self, schema: ClassSchema) -> None:
        """Write a class schema once, under its digest. Its bytes never change, so a schema already
        kept is left as it is."""
        path = self.root / SCHEMAS_DIR / f"{schema.digest}.json"
        if path.exists():
            return
        path.parent.mkdir(exist_ok=True)
        # Written aside and moved into place, so a reader never sees half a schema while another
        # run keeps the same one.
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(dict(schema.json_schema), indent=2))
            Path(tmp).replace(path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def get_schema(self, digest: str) -> dict[str, Any] | None:
        """The class schema kept under `digest`, or None. A digest is 64 hex characters; anything
        else names nothing, so no path outside the store can be read."""
        if not DIGEST.fullmatch(digest):
            return None
        return _read_json(self.root / SCHEMAS_DIR / f"{digest}.json")


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data
