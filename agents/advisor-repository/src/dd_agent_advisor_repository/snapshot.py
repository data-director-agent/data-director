"""Snapshot backends: committed JSON Lines copies of both registries.

Used in CI and offline, and as the fallback when a live route fails. Each line is a record's
whole document, as hashed, so the harness's source check can use the same file (ADR-0016).
re3data records are searched lexically with `rank_bm25`; this module is its only importer
(ADR-0006).
"""

from __future__ import annotations

import json
import re
from functools import cached_property
from pathlib import Path

from rank_bm25 import BM25Okapi

from dd_agent_advisor_repository.records import DatabaseRecord, Re3dataRecord
from dd_agent_advisor_repository.retrieve import Hit, Query, RegistryUnavailable, SnapshotRef

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
RE3DATA_SNAPSHOT = DATA_DIR / "re3data" / "snapshot.jsonl"
FAIRSHARING_SNAPSHOT = DATA_DIR / "fairsharing" / "snapshot.jsonl"

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    [
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
        "its",
        "it",
        "data",
    ]
)


def tokenise(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP and len(t) > 1]


def _lines(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        raise RegistryUnavailable(f"snapshot not found at {path}")
    with path.open(encoding="utf-8") as fh:
        out = [json.loads(line) for line in fh if line.strip()]
    if not out:
        raise RegistryUnavailable(f"snapshot at {path} is empty")
    return out


def _ref(registry: str, path: Path) -> SnapshotRef:
    manifest = path.with_name("manifest.json")
    fetched_at = None
    if manifest.is_file():
        fetched_at = json.loads(manifest.read_text(encoding="utf-8")).get("fetched_at")
    label = f"{registry}:snapshot:{fetched_at[:10] if fetched_at else path.name}"
    return SnapshotRef(label=label, fetched_at=fetched_at)


class Re3dataSnapshot:
    def __init__(self, path: Path = RE3DATA_SNAPSHOT) -> None:
        self.path = path

    @cached_property
    def records(self) -> list[Re3dataRecord]:
        return [Re3dataRecord.model_validate(d) for d in _lines(self.path)]

    @cached_property
    def _bm25(self) -> BM25Okapi:
        return BM25Okapi([tokenise(r.search_text()) for r in self.records])

    def snapshot_ref(self) -> SnapshotRef:
        return _ref("re3data", self.path)

    def search(self, query: Query) -> list[Hit]:
        tokens = tokenise(query.text)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        hits = [
            Hit(record=r, lexical_score=float(s))
            for r, s in zip(self.records, scores, strict=True)
            if s > 0
        ]
        hits.sort(key=lambda h: (-h.lexical_score, h.record.re3data_id))
        return hits[: query.limit]

    def fetch(self, re3data_id: str) -> Re3dataRecord | None:
        return next((r for r in self.records if r.re3data_id == re3data_id), None)

    def find(self, name: str) -> Re3dataRecord | None:
        wanted = name.casefold().strip()
        return next((r for r in self.records if wanted in r.names()), None)


class FairsharingSnapshot:
    def __init__(self, path: Path = FAIRSHARING_SNAPSHOT) -> None:
        self.path = path

    @cached_property
    def records(self) -> dict[str, DatabaseRecord]:
        records = [DatabaseRecord.model_validate(d) for d in _lines(self.path)]
        return {r.fairsharing_id: r for r in records}

    def snapshot_ref(self) -> SnapshotRef:
        return _ref("fairsharing", self.path)

    def fetch(self, fairsharing_id: str) -> DatabaseRecord | None:
        return self.records.get(fairsharing_id)
