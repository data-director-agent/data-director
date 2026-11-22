"""Live backend: the public record route for fetches, the authenticated API for search.

- Record fetch needs no account: `GET https://fairsharing.org/<id>` with
  `Accept: application/json` (verified 2026-09-04).
- Search needs an account. The sign-in and search go through the SDK's FAIRsharing client
  (`dd_sdk.registry.fairsharing`); credentials come from `FAIRSHARING_LOGIN` /
  `FAIRSHARING_PASSWORD`, and the sign-in body is filtered from cassettes.

Both go through the client's local cache. Each record returned is noted with where it came from
(`dd_sdk.registry.provenance`), for its evidence. When FAIRsharing cannot be asked and the cache
holds no expired copy either, the caller (`StandardsAgent`) falls back to the snapshot and marks
the snapshot reference stale.
"""

from __future__ import annotations

from dd_agent_advisor_standards.fairsharing.records import (
    PUBLIC_RECORD_URL,
    Record,
    from_api_json,
    from_public_json,
)
from dd_sdk.registry import Hit, Query, SnapshotRef, provenance
from dd_sdk.registry.fairsharing import SEARCH, FairsharingClient


class LiveBackend:
    name = "live"

    def __init__(self, api: FairsharingClient | None = None) -> None:
        """`api` is the FAIRsharing client, with its cache; by default one with credentials from
        the environment and a cache in memory."""
        self._api = api or FairsharingClient()

    def snapshot_ref(self) -> SnapshotRef:
        return SnapshotRef(label="live")

    def fetch(self, fairsharing_id: str) -> Record | None:
        """A record by its identifier, from the public route (no account)."""
        url = PUBLIC_RECORD_URL.format(id=fairsharing_id)
        got = self._api.get_json(url)
        data = got.value
        if data is None or "name" not in data:  # FAIRsharing returns 200-shaped errors as JSON
            return None
        record = from_public_json(data, source_uri=url)
        provenance.note(record.fairsharing_id, got)
        return record

    def search(self, query: Query) -> list[Hit[Record]]:
        """One search (account required), in FAIRsharing's relevance order."""
        params: dict[str, str] = {
            "q": query.text,
            "page[number]": "1",
            "page[size]": str(query.limit),
        }
        if query.record_type:
            params["record_type"] = query.record_type
        got = self._api.search(params)
        items = got.value
        # The API returns results in its own relevance order and exposes no score; a descending
        # rank position stands in for the lexical score so the ranker can treat both routes alike.
        hits = [
            Hit(
                record=from_api_json(item, source_uri=f"{SEARCH}?q={query.text}"),
                lexical_score=float(len(items) - position),
            )
            for position, item in enumerate(items)
        ]
        for hit in hits:
            provenance.note(hit.record.fairsharing_id, got)
        return hits
