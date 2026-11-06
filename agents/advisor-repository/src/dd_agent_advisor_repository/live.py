"""The live route to FAIRsharing's public record route, which needs no account.

- FAIRsharing fetch: `GET https://fairsharing.org/<id>` with `Accept: application/json`.

re3data has no live route: every record comes from the pinned export (`registry.py`), so a run
makes no request to re3data (Blueprint P14, low impact on community services).

Any transport failure raises `RegistryUnavailable`; the agent then falls back to the snapshot
and marks it stale. This module and `registry.py` are the only importers of `httpx`
(docs/specs/dependencies.md).
"""

from __future__ import annotations

from typing import Any

import httpx

from dd_agent_advisor_repository.records import (
    FAIRSHARING_RECORD_URL,
    DatabaseRecord,
    from_fairsharing_json,
)
from dd_agent_advisor_repository.retrieve import RegistryUnavailable, SnapshotRef

TIMEOUT_S = 20.0


class FairsharingLive:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=TIMEOUT_S, follow_redirects=True)

    def snapshot_ref(self) -> SnapshotRef:
        return SnapshotRef(label="fairsharing:live")

    def fetch(self, fairsharing_id: str) -> DatabaseRecord | None:
        url = FAIRSHARING_RECORD_URL.format(id=fairsharing_id)
        try:
            resp = self._client.get(url, headers={"Accept": "application/json"})
        except httpx.HTTPError as exc:
            raise RegistryUnavailable(f"FAIRsharing {url}: {exc}") from exc
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            raise RegistryUnavailable(f"FAIRsharing {url}: HTTP {resp.status_code}")
        if "json" not in resp.headers.get("content-type", ""):
            return None  # an unknown identifier is answered with the HTML site, not JSON
        data: dict[str, Any] = resp.json()
        return from_fairsharing_json(data)
