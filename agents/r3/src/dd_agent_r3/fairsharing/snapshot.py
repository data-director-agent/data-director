"""Snapshot backend: a committed JSONL file of projected records, searched lexically.

Used in CI and offline, and as the fallback when the live route fails. Lexical scoring uses
`rank_bm25`; ranking proper is bespoke and lives in `agents/r3/rank.py`. This module is the
only importer of `rank_bm25` (ADR-0006).
"""

from __future__ import annotations

import json
import re
from functools import cached_property
from pathlib import Path

from rank_bm25 import BM25Okapi

from dd_agent_r3.fairsharing.records import Record
from dd_agent_r3.retrieve import Hit, Query, RegistryUnavailable, SnapshotRef

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "fairsharing"
DEFAULT_SNAPSHOT = DATA_DIR / "snapshot.jsonl"
DEFAULT_MANIFEST = DATA_DIR / "manifest.json"

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    {
        "the",
        "a",
        "an",
        "of",
        "and",
        "or",
        "for",
        "to",
        "in",
        "on",
        "with",
        "by",
        "from",
        "at",
        "as",
        "is",
        "are",
        "be",
        "this",
        "that",
        "these",
        "those",
        "its",
        "it",
    }
)


def tokenise(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP and len(t) > 1]


class SnapshotBackend:
    name = "snapshot"

    def __init__(
        self, path: Path = DEFAULT_SNAPSHOT, manifest: Path = DEFAULT_MANIFEST, stale: bool = False
    ) -> None:
        self.path = path
        self.manifest_path = manifest
        self._stale = stale

    @cached_property
    def records(self) -> list[Record]:
        if not self.path.is_file():
            raise RegistryUnavailable(f"snapshot not found at {self.path}")
        out: list[Record] = []
        with self.path.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    out.append(Record.model_validate(json.loads(line)))
        if not out:
            raise RegistryUnavailable(f"snapshot at {self.path} is empty")
        return out

    @cached_property
    def _by_id(self) -> dict[str, Record]:
        index = {r.fairsharing_id: r for r in self.records}
        index.update({r.numeric_id: r for r in self.records if r.numeric_id})
        return index

    @cached_property
    def _bm25(self) -> BM25Okapi:
        return BM25Okapi([tokenise(r.search_text()) for r in self.records])

    def snapshot_ref(self) -> SnapshotRef:
        fetched_at = None
        if self.manifest_path.is_file():
            fetched_at = json.loads(self.manifest_path.read_text(encoding="utf-8")).get(
                "fetched_at"
            )
        label = f"snapshot:{fetched_at[:10]}" if fetched_at else f"snapshot:{self.path.name}"
        return SnapshotRef(label=label, stale=self._stale, fetched_at=fetched_at)

    def search(self, query: Query) -> list[Hit]:
        tokens = tokenise(query.text)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        hits = [
            Hit(record=r, lexical_score=float(s))
            for r, s in zip(self.records, scores, strict=True)
            if s > 0 and (query.record_type is None or r.record_type == query.record_type)
        ]
        hits.sort(key=lambda h: (-h.lexical_score, h.record.fairsharing_id))
        return hits[: query.limit]

    def fetch(self, fairsharing_id: str) -> Record | None:
        return self._by_id.get(fairsharing_id)
