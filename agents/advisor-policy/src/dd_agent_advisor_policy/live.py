"""Live route: FAIRsharing's authenticated API for search, and its record routes for fetches.

- Search signs in and searches with `fairsharing_registry=policy`, through the SDK's FAIRsharing
  client (`dd_sdk.registry.fairsharing`). Credentials come from `FAIRSHARING_LOGIN` /
  `FAIRSHARING_PASSWORD`.
- Fetch by `FAIRsharing.xxxxx` uses the public record route, which needs no account but carries
  no relations. With an account, the record is then read again from
  `GET /fairsharing_records/<numeric id>`, so it is projected from the same shape as a search hit
  and keeps its relations.

Both go through the client's local cache, and each record returned is noted with where it came
from (`dd_sdk.registry.provenance`); a record read twice is noted under the weaker of the two
answers. When FAIRsharing cannot be asked and the cache holds no expired copy,
`RegistryUnavailable` is raised; the agent then falls back to the snapshot and marks it stale.
"""

from __future__ import annotations

import httpx

from dd_agent_advisor_policy.records import (
    PUBLIC_RECORD_URL,
    PolicyRecord,
    from_api_json,
    from_public_json,
)
from dd_sdk.registry import Query, SnapshotRef, provenance
from dd_sdk.registry.fairsharing import RECORD, FairsharingClient


class PolicyLive:
    def __init__(
        self,
        client: httpx.Client | None = None,
        login: str | None = None,
        password: str | None = None,
        *,
        api: FairsharingClient | None = None,
    ) -> None:
        self._api = api or FairsharingClient(client, login, password, follow_redirects=True)

    @property
    def signed_in(self) -> bool:
        return self._api.signed_in

    def snapshot_ref(self) -> SnapshotRef:
        return SnapshotRef(label="fairsharing-policy:live")

    def search(self, query: Query) -> list[PolicyRecord]:
        got = self._api.search(
            {
                "q": query.text,
                "fairsharing_registry": "policy",
                "page[number]": "1",
                "page[size]": str(query.limit),
            }
        )
        records = [from_api_json(item) for item in got.value if isinstance(item, dict)]
        found = [r for r in records if r is not None]
        for record in found:
            provenance.note(record.source_id, got)
        return found

    def fetch(self, fairsharing_id: str) -> PolicyRecord | None:
        public = self._api.get_json(PUBLIC_RECORD_URL.format(id=fairsharing_id))
        record = from_public_json(public.value) if public.value else None
        if record is None or not (self.signed_in and record.numeric_id):
            if record is not None:
                provenance.note(record.source_id, public)
            return record
        api = self._api.get_json(RECORD.format(id=record.numeric_id), authorised=True)
        item = api.value.get("data") if api.value else None
        reread = from_api_json(item) if isinstance(item, dict) else None
        if reread is None:
            provenance.note(record.source_id, public)
            return record
        provenance.note(reread.source_id, public.weakest(api))
        return reread
