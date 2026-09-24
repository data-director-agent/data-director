"""Live backend: the public record route for fetches, the authenticated API for search.

- Record fetch needs no account: `GET https://fairsharing.org/<id>` with
  `Accept: application/json` (verified 2026-09-04).
- Search needs a JWT: `POST https://api.fairsharing.org/users/sign_in` with
  `{"user": {"login", "password"}}`, then `POST /search/fairsharing_records` with the filters in
  the query string and `Authorization: Bearer <jwt>`. Credentials come from
  `FAIRSHARING_LOGIN` / `FAIRSHARING_PASSWORD`; the sign-in body is filtered from cassettes.

On any transport failure the caller (`R3Agent`) falls back to the snapshot and marks the
snapshot reference stale. This module is the only importer of `httpx` (ADR-0006).
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from workbench.agents.r3.fairsharing.records import (
    PUBLIC_RECORD_URL,
    Record,
    from_api_json,
    from_public_json,
)
from workbench.agents.r3.retrieve import Hit, Query, RegistryUnavailable, SnapshotRef

API_BASE = "https://api.fairsharing.org"
SIGN_IN = f"{API_BASE}/users/sign_in"
SEARCH = f"{API_BASE}/search/fairsharing_records"
TIMEOUT_S = 20.0


class LiveBackend:
    name = "live"

    def __init__(
        self,
        client: httpx.Client | None = None,
        login: str | None = None,
        password: str | None = None,
    ) -> None:
        self._client = client or httpx.Client(
            timeout=TIMEOUT_S, headers={"Accept": "application/json"}
        )
        self._login = login or os.environ.get("FAIRSHARING_LOGIN")
        self._password = password or os.environ.get("FAIRSHARING_PASSWORD")
        self._jwt: str | None = None

    def snapshot_ref(self) -> SnapshotRef:
        return SnapshotRef(label="live")

    # --- fetch (no account) ---------------------------------------------------------------

    def fetch(self, fairsharing_id: str) -> Record | None:
        url = PUBLIC_RECORD_URL.format(id=fairsharing_id)
        try:
            resp = self._client.get(url, headers={"Accept": "application/json"})
        except httpx.HTTPError as exc:
            raise RegistryUnavailable(f"fetch {url}: {exc}") from exc
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            raise RegistryUnavailable(f"fetch {url}: HTTP {resp.status_code}")
        if "json" not in resp.headers.get("content-type", ""):
            return None  # an unknown identifier is answered with the HTML site, not JSON
        data: dict[str, Any] = resp.json()
        if "name" not in data:  # FAIRsharing returns 200-shaped errors as JSON too
            return None
        return from_public_json(data, source_uri=url)

    # --- search (account required) --------------------------------------------------------

    def _token(self) -> str:
        if self._jwt:
            return self._jwt
        if not (self._login and self._password):
            raise RegistryUnavailable(
                "FAIRsharing search needs an account: set FAIRSHARING_LOGIN and "
                "FAIRSHARING_PASSWORD"
            )
        try:
            resp = self._client.post(
                SIGN_IN,
                json={"user": {"login": self._login, "password": self._password}},
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise RegistryUnavailable(f"sign in: {exc}") from exc
        jwt = resp.json().get("jwt")
        if not jwt:
            raise RegistryUnavailable("sign in returned no jwt; check credentials")
        self._jwt = str(jwt)
        return self._jwt

    def search(self, query: Query) -> list[Hit]:
        params: dict[str, str] = {
            "q": query.text,
            "page[number]": "1",
            "page[size]": str(query.limit),
        }
        if query.record_type:
            params["record_type"] = query.record_type
        try:
            resp = self._client.post(
                SEARCH,
                params=params,
                headers={"Authorization": f"Bearer {self._token()}", "Accept": "application/json"},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise RegistryUnavailable(f"search: {exc}") from exc
        body = resp.json()
        items = body.get("data") if isinstance(body, dict) else None
        if not isinstance(items, list):
            raise RegistryUnavailable("search returned no data array; check credentials")
        hits: list[Hit] = []
        # The API returns results in its own relevance order and exposes no score; a descending
        # rank position stands in for the lexical score so the ranker can treat both routes alike.
        for position, item in enumerate(items):
            record = from_api_json(item, source_uri=f"{SEARCH}?q={query.text}")
            hits.append(Hit(record=record, lexical_score=float(len(items) - position)))
        return hits
