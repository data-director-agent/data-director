"""A pinned copy of a source, read into records by identifier (harness/src/dd_harness/sources.py).

A file is never read without its `sha256` pin, and each is read and checked once per process while
its size and modification time stay the same.
"""

from __future__ import annotations

import functools
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

__all__ = ["RecordsFile", "SourceConfigError"]


class SourceConfigError(Exception):
    """`sources.yaml` is malformed, or a file it lists does not match its pin, or is missing and
    names no command that builds it."""


@dataclass(frozen=True)
class RecordsFile:
    """The records of one pinned file, indexed by `id_field`. Read only: a loaded file is shared
    by every caller in the process."""

    records: Mapping[str, dict[str, Any]]

    @classmethod
    def load(cls, path: Path, id_field: str, sha256: str) -> RecordsFile:
        """The file's records, once its bytes match `sha256`. Each file is read and checked once
        per process while its size and modification time stay the same: every `Governance` loads
        every source, and the built re3data export alone takes seconds to parse."""
        try:
            stat = path.stat()
        except OSError as exc:
            raise SourceConfigError(f"source file {path}: {exc}") from None
        return _load_records(path.resolve(), stat.st_size, stat.st_mtime_ns, id_field, sha256)

    def record(self, source_id: str) -> dict[str, Any] | None:
        return self.records.get(source_id)


@functools.lru_cache(maxsize=32)
def _load_records(path: Path, size: int, mtime_ns: int, id_field: str, sha256: str) -> RecordsFile:
    """`RecordsFile.load`, cached on the file's identity and pin. `size` and `mtime_ns` are only
    part of the key, so that a file changed on disk is read and checked again."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise SourceConfigError(f"source file {path}: {exc}") from None
    actual = hashlib.sha256(raw).hexdigest()
    if actual != sha256:
        raise SourceConfigError(f"source file {path} has sha256 {actual}, not the pinned {sha256}")
    text = raw.decode("utf-8")
    if text.lstrip().startswith("["):
        rows = json.loads(text)
    else:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get(id_field), str):
            raise SourceConfigError(f"source file {path}: a record has no string {id_field!r}")
        index[row[id_field]] = row
    return RecordsFile(records=MappingProxyType(index))
