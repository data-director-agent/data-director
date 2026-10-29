"""Snapshot backend: a committed JSON Lines copy of FAIRsharing policy records.

Used in CI and offline, and as the fallback when the live route fails. Each line is a record's
whole document, as hashed, so the harness's source check can use the same file (ADR-0016).
Records are searched lexically with `rank_bm25`; this module is its only importer (ADR-0006).
"""

from __future__ import annotations

import json
import re
from functools import cached_property
from pathlib import Path

from rank_bm25 import BM25Okapi

from dd_agent_policy.records import PolicyRecord
from dd_agent_policy.retrieve import Query, RegistryUnavailable, SnapshotRef

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "fairsharing"
SNAPSHOT = DATA_DIR / "snapshot.jsonl"
# The label names the registry and the kind of record, so the source check can tell this copy
# from the repository advisor's copy of FAIRsharing's database records.
REGISTRY = "fairsharing-policy"

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    ["the", "a", "an", "of", "and", "or", "for", "to", "in", "on", "by", "data", "policy"]
)


def tokenise(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP and len(t) > 1]


class PolicySnapshot:
    def __init__(self, path: Path = SNAPSHOT) -> None:
        self.path = path

    @cached_property
    def records(self) -> list[PolicyRecord]:
        if not self.path.is_file():
            raise RegistryUnavailable(f"snapshot not found at {self.path}")
        with self.path.open(encoding="utf-8") as fh:
            out = [PolicyRecord.model_validate(json.loads(line)) for line in fh if line.strip()]
        if not out:
            raise RegistryUnavailable(f"snapshot at {self.path} is empty")
        return out

    @cached_property
    def _bm25(self) -> BM25Okapi:
        return BM25Okapi([tokenise(r.search_text()) for r in self.records])

    def snapshot_ref(self) -> SnapshotRef:
        manifest = self.path.with_name("manifest.json")
        fetched_at = None
        if manifest.is_file():
            fetched_at = json.loads(manifest.read_text(encoding="utf-8")).get("fetched_at")
        label = f"{REGISTRY}:snapshot:{fetched_at[:10] if fetched_at else self.path.name}"
        return SnapshotRef(label=label, fetched_at=fetched_at)

    def search(self, query: Query) -> list[PolicyRecord]:
        tokens = tokenise(query.text)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        ranked = sorted(
            ((float(s), r) for s, r in zip(scores, self.records, strict=True) if s > 0),
            key=lambda pair: (-pair[0], pair[1].fairsharing_id),
        )
        return [r for _, r in ranked[: query.limit]]

    def fetch(self, fairsharing_id: str) -> PolicyRecord | None:
        return next((r for r in self.records if r.fairsharing_id == fairsharing_id), None)
