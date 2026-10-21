"""Append-only JSONL store of envelopes, plus a per-invocation run directory.

UUIDv7 identifiers mean the file is chronologically ordered as written and needs no index. A run
is written once: `append` refuses an `invocation_id` whose envelope is already stored, and the
conductor refuses such a request before it runs (`DuplicateInvocation`).

Each class schema a run was checked against is kept once, addressed by its digest, in
`schemas/<digest>.json` (ADR-0019). An envelope names the digests, so a stored run is shown with
the schema it was checked against, whatever its agent's card says now.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from dd_sdk.contract.classes import ClassSchema

INDEX_NAME = "invocations.jsonl"
SCHEMAS_DIR = "schemas"
DIGEST = re.compile(r"[0-9a-f]{64}")


class RunStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    @property
    def index(self) -> Path:
        return self.root / INDEX_NAME

    def run_dir(self, invocation_id: str) -> Path:
        d = self.root / invocation_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def has(self, invocation_id: str) -> bool:
        return (self.root / invocation_id / "envelope.json").exists()

    def append(
        self,
        envelope: dict[str, Any],
        request: dict[str, Any] | None = None,
        schemas: Iterable[ClassSchema] = (),
    ) -> Path:
        """Store one envelope, and each class schema it was checked against under its digest.
        Raises FileExistsError if its `invocation_id` is already stored."""
        for schema in schemas:
            self._keep_schema(schema)
        run_dir = self.run_dir(envelope["invocation_id"])
        with (run_dir / "envelope.json").open("x", encoding="utf-8") as fh:
            fh.write(json.dumps(envelope, indent=2))
        if request is not None:
            (run_dir / "request.json").write_text(json.dumps(request, indent=2), encoding="utf-8")
        with self.index.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(envelope, separators=(",", ":")) + "\n")
        return run_dir

    def iter_envelopes(self) -> Iterator[dict[str, Any]]:
        if not self.index.exists():
            return
        with self.index.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    yield json.loads(line)

    def get(self, invocation_id: str) -> dict[str, Any] | None:
        path = self.root / invocation_id / "envelope.json"
        return _read_json(path)

    def get_request(self, invocation_id: str) -> dict[str, Any] | None:
        path = self.root / invocation_id / "request.json"
        return _read_json(path)

    def _keep_schema(self, schema: ClassSchema) -> None:
        """Write a class schema once, under its digest. Its bytes never change, so a schema already
        kept is left as it is."""
        path = self.root / SCHEMAS_DIR / f"{schema.digest}.json"
        if path.exists():
            return
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(dict(schema.json_schema), indent=2), encoding="utf-8")

    def get_schema(self, digest: str) -> dict[str, Any] | None:
        """The class schema kept under `digest`, or None. A digest is 64 hex characters; anything
        else names nothing, so no path outside the store can be read."""
        if not DIGEST.fullmatch(digest):
            return None
        return _read_json(self.root / SCHEMAS_DIR / f"{digest}.json")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data
