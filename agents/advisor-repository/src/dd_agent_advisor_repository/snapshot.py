"""Local copies of both registries, in JSON Lines.

- re3data: the whole registry, built from the pinned monthly export (`registry.py`). It is the
  only copy of re3data the agent reads.
- FAIRsharing: a committed snapshot of the database records re3data cross-references, used by
  default and as the fallback when the live route fails.

Each line is a record's whole document, as hashed, so the harness's source check can use the same
file (docs/specs/grounding.md). re3data records are searched lexically with `rank_bm25`; this
module is its only importer (docs/specs/dependencies.md).
"""

from __future__ import annotations

import json
import re
from functools import cached_property
from pathlib import Path

from rank_bm25 import BM25Okapi

from dd_agent_advisor_repository import registry
from dd_agent_advisor_repository.records import DatabaseRecord, Re3dataRecord
from dd_agent_advisor_repository.retrieve import (
    Hit,
    Query,
    RegistryUnavailable,
    SnapshotRef,
    find_by_name,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
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


def _ref(name: str, path: Path) -> SnapshotRef:
    manifest = path.with_name("manifest.json")
    fetched_at = None
    if manifest.is_file():
        fetched_at = json.loads(manifest.read_text(encoding="utf-8")).get("fetched_at")
    label = f"{name}:snapshot:{fetched_at[:10] if fetched_at else path.name}"
    return SnapshotRef(label=label, fetched_at=fetched_at)


class Re3dataRegistry:
    """Every repository in the pinned re3data export. The registry is checked against its pin
    when first read, so the label it gives the evidence is true of the records it holds."""

    def __init__(self, path: Path = registry.REGISTRY, manifest: Path = registry.MANIFEST) -> None:
        self.path = path
        self.manifest = manifest

    @cached_property
    def pin(self) -> registry.Pin:
        try:
            return registry.Pin.load(self.manifest)
        except registry.RegistryError as exc:
            raise RegistryUnavailable(str(exc)) from None

    @cached_property
    def records(self) -> list[Re3dataRecord]:
        if (found := registry.problem(self.path, self.manifest)) is not None:
            raise RegistryUnavailable(found)
        return [Re3dataRecord.model_validate(d) for d in _lines(self.path)]

    @cached_property
    def _tokens(self) -> list[list[str]]:
        return [tokenise(r.search_text()) for r in self.records]

    @cached_property
    def _bm25(self) -> BM25Okapi:
        return BM25Okapi(self._tokens)

    @cached_property
    def _by_id(self) -> dict[str, Re3dataRecord]:
        return {r.re3data_id: r for r in self.records}

    def snapshot_ref(self) -> SnapshotRef:
        return SnapshotRef(label=self.pin.label, fetched_at=self.pin.fetched_at)

    def credit(self) -> str:
        return self.pin.credit

    def search(self, query: Query) -> list[Hit]:
        """Records that contain every word of the query, as re3data's own search requires, in
        BM25 order. A record matching only some words is not a hit: a ranking that counts any
        hit as a match must not be fed partial ones (#440)."""
        tokens = tokenise(query.text)
        if not tokens:
            return []
        wanted = set(tokens)
        scores = self._bm25.get_scores(tokens)
        hits = [
            Hit(record=r, lexical_score=float(s))
            for r, words, s in zip(self.records, self._tokens, scores, strict=True)
            if s > 0 and wanted <= set(words)
        ]
        hits.sort(key=lambda h: (-h.lexical_score, h.record.re3data_id))
        return hits[: query.limit]

    def fetch(self, re3data_id: str) -> Re3dataRecord | None:
        return self._by_id.get(re3data_id)

    def find(self, name: str) -> list[Re3dataRecord]:
        return find_by_name(self.records, name)


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
