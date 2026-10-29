"""Live routes: re3data's public API, and FAIRsharing's public record route. Neither needs an
account.

- re3data search: `GET /api/beta/repositories?query=<text>` lists identifiers; each is then
  fetched with `GET /api/v1/repository/<id>` (XML, schema 2.2). A search costs one request per
  record kept, so `Query.limit` stays small (Blueprint P14, low impact on community services).
- FAIRsharing fetch: `GET https://fairsharing.org/<id>` with `Accept: application/json`.

Any transport failure raises `RegistryUnavailable`; the agent then falls back to the snapshot
and marks it stale. This module is the only importer of `httpx` (ADR-0006).
"""

from __future__ import annotations

from typing import Any

import httpx

from dd_agent_repository.records import (
    FAIRSHARING_RECORD_URL,
    RE3DATA_RECORD_URL,
    DatabaseRecord,
    Re3dataRecord,
    from_fairsharing_json,
    from_re3data_xml,
    ids_from_re3data_list,
)
from dd_agent_repository.retrieve import Hit, Query, RegistryUnavailable, SnapshotRef

RE3DATA_SEARCH = "https://www.re3data.org/api/beta/repositories"
TIMEOUT_S = 20.0
# How many name-search results are fetched to find a mandated repository by its exact name.
FIND_LIMIT = 5


def _client(client: httpx.Client | None) -> httpx.Client:
    return client or httpx.Client(timeout=TIMEOUT_S, follow_redirects=True)


class Re3dataLive:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = _client(client)

    def snapshot_ref(self) -> SnapshotRef:
        return SnapshotRef(label="re3data:live")

    def _get(self, url: str, **params: str) -> httpx.Response:
        try:
            resp = self._client.get(url, params=params or None)
        except httpx.HTTPError as exc:
            raise RegistryUnavailable(f"re3data {url}: {exc}") from exc
        if resp.status_code >= 400 and resp.status_code != 404:
            raise RegistryUnavailable(f"re3data {url}: HTTP {resp.status_code}")
        return resp

    def fetch(self, re3data_id: str) -> Re3dataRecord | None:
        resp = self._get(RE3DATA_RECORD_URL.format(id=re3data_id))
        if resp.status_code == 404:
            return None
        return from_re3data_xml(resp.content)

    def _search_ids(self, text: str) -> list[str]:
        return ids_from_re3data_list(self._get(RE3DATA_SEARCH, query=text).content)

    def search(self, query: Query) -> list[Hit]:
        ids = self._search_ids(query.text)[: query.limit]
        hits: list[Hit] = []
        # re3data returns its own relevance order and no score; a descending rank position
        # stands in for the lexical score, as in the standards advisor's live route.
        for position, rid in enumerate(ids):
            record = self.fetch(rid)
            if record is not None:
                hits.append(Hit(record=record, lexical_score=float(len(ids) - position)))
        return hits

    def find(self, name: str) -> Re3dataRecord | None:
        wanted = name.casefold().strip()
        for rid in self._search_ids(name)[:FIND_LIMIT]:
            record = self.fetch(rid)
            if record is not None and wanted in record.names():
                return record
        return None


class FairsharingLive:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = _client(client)

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
