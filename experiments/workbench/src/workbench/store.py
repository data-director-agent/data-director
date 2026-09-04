"""Append-only JSONL store of envelopes, plus a per-invocation run directory.

UUIDv7 identifiers mean the file is chronologically ordered as written and needs no index.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

INDEX_NAME = "invocations.jsonl"


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

    def append(self, envelope: dict[str, Any], request: dict[str, Any] | None = None) -> Path:
        run_dir = self.run_dir(envelope["invocation_id"])
        (run_dir / "envelope.json").write_text(json.dumps(envelope, indent=2), encoding="utf-8")
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


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data
