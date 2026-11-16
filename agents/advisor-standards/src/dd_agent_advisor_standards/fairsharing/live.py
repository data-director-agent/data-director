"""Live backend: the public record route for fetches, the authenticated API for search.

- Record fetch needs no account: `GET https://fairsharing.org/<id>` with
  `Accept: application/json` (verified 2026-09-04).
- Search needs an account. The sign-in and search go through the SDK's FAIRsharing client
  (`dd_sdk.registry.fairsharing`); credentials come from `FAIRSHARING_LOGIN` /
  `FAIRSHARING_PASSWORD`, and the sign-in body is filtered from cassettes.

On any transport failure the caller (`StandardsAgent`) falls back to the snapshot and marks the
snapshot reference stale.
"""

from __future__ import annotations

import httpx

from dd_agent_advisor_standards.fairsharing.records import (
    PUBLIC_RECORD_URL,
    Record,
    from_api_json,
    from_public_json,
)
from dd_sdk.registry import Hit, Query, SnapshotRef
from dd_sdk.registry.fairsharing import SEARCH, FairsharingClient


class LiveBackend:
    name = "live"

    def __init__(
        self,
        client: httpx.Client | None = None,
        login: str | None = None,
        password: str | None = None,
    ) -> None:
        self._api = FairsharingClient(client, login, password)

    def snapshot_ref(self) -> SnapshotRef:
        return SnapshotRef(label="live")

    def fetch(self, fairsharing_id: str) -> Record | None:
        """A record by its identifier, from the public route (no account)."""
        url = PUBLIC_RECORD_URL.format(id=fairsharing_id)
        data = self._api.get_json(url)
        if data is None or "name" not in data:  # FAIRsharing returns 200-shaped errors as JSON
            return None
        return from_public_json(data, source_uri=url)

    def search(self, query: Query) -> list[Hit[Record]]:
        """One search (account required), in FAIRsharing's relevance order."""
        params: dict[str, str] = {
            "q": query.text,
            "page[number]": "1",
            "page[size]": str(query.limit),
        }
        if query.record_type:
            params["record_type"] = query.record_type
        items = self._api.search(params)
        # The API returns results in its own relevance order and exposes no score; a descending
        # rank position stands in for the lexical score so the ranker can treat both routes alike.
        return [
            Hit(
                record=from_api_json(item, source_uri=f"{SEARCH}?q={query.text}"),
                lexical_score=float(len(items) - position),
            )
            for position, item in enumerate(items)
        ]
