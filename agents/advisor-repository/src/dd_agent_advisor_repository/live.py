"""The live route to FAIRsharing's public record route, which needs no account.

- FAIRsharing fetch: `GET https://fairsharing.org/<id>` with `Accept: application/json`.

re3data has no live route: every record comes from the pinned export (`registry.py`), so a run
makes no request to re3data (Blueprint P14, low impact on community services).

Any transport failure raises `RegistryUnavailable`; the agent then falls back to the snapshot
and marks it stale. The request goes through the SDK's FAIRsharing client
(`dd_sdk.registry.fairsharing`).
"""

from __future__ import annotations

import httpx

from dd_agent_advisor_repository.records import (
    FAIRSHARING_RECORD_URL,
    DatabaseRecord,
    from_fairsharing_json,
)
from dd_sdk.registry import SnapshotRef
from dd_sdk.registry.fairsharing import FairsharingClient


class FairsharingLive:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._api = FairsharingClient(client, follow_redirects=True)

    def snapshot_ref(self) -> SnapshotRef:
        return SnapshotRef(label="fairsharing:live")

    def fetch(self, fairsharing_id: str) -> DatabaseRecord | None:
        data = self._api.get_json(FAIRSHARING_RECORD_URL.format(id=fairsharing_id))
        return from_fairsharing_json(data) if data is not None else None
