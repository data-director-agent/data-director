"""Live route: FAIRsharing's authenticated API for search, and its record routes for fetches.

- Search needs a JWT: `POST https://api.fairsharing.org/users/sign_in` with
  `{"user": {"login", "password"}}`, then `POST /search/fairsharing_records` with
  `fairsharing_registry=policy` and the query in the query string, and
  `Authorization: Bearer <jwt>`. Credentials come from `FAIRSHARING_LOGIN` /
  `FAIRSHARING_PASSWORD`.
- Fetch by `FAIRsharing.xxxxx` uses the public record route, which needs no account but carries
  no relations. With an account, the record is then read again from
  `GET /fairsharing_records/<numeric id>`, so it is projected from the same shape as a search hit
  and keeps its relations.

The sign-in and search are a copy of the standards advisor's client, since an agent may not
import another (ADR-0031). TODO(#280)

Any transport failure raises `RegistryUnavailable`; the agent then falls back to the snapshot
and marks it stale. This module is the only importer of `httpx` (ADR-0006).
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from dd_agent_advisor_policy.records import (
    PUBLIC_RECORD_URL,
    PolicyRecord,
    from_api_json,
    from_public_json,
)
from dd_agent_advisor_policy.retrieve import Query, RegistryUnavailable, SnapshotRef

API_BASE = "https://api.fairsharing.org"
SIGN_IN = f"{API_BASE}/users/sign_in"
SEARCH = f"{API_BASE}/search/fairsharing_records"
RECORD = f"{API_BASE}/fairsharing_records/{{id}}"
TIMEOUT_S = 20.0


class PolicyLive:
    def __init__(
        self,
        client: httpx.Client | None = None,
        login: str | None = None,
        password: str | None = None,
    ) -> None:
        self._client = client or httpx.Client(
            timeout=TIMEOUT_S, follow_redirects=True, headers={"Accept": "application/json"}
        )
        self._login = login or os.environ.get("FAIRSHARING_LOGIN")
        self._password = password or os.environ.get("FAIRSHARING_PASSWORD")
        self._jwt: str | None = None

    @property
    def signed_in(self) -> bool:
        return bool(self._login and self._password)

    def snapshot_ref(self) -> SnapshotRef:
        return SnapshotRef(label="fairsharing-policy:live")

    def _token(self) -> str:
        if self._jwt:
            return self._jwt
        if not self.signed_in:
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

    def _authorised(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token()}", "Accept": "application/json"}

    def search(self, query: Query) -> list[PolicyRecord]:
        params = {
            "q": query.text,
            "fairsharing_registry": "policy",
            "page[number]": "1",
            "page[size]": str(query.limit),
        }
        try:
            resp = self._client.post(SEARCH, params=params, headers=self._authorised())
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise RegistryUnavailable(f"search: {exc}") from exc
        body = resp.json()
        items = body.get("data") if isinstance(body, dict) else None
        if not isinstance(items, list):
            raise RegistryUnavailable("search returned no data array; check credentials")
        records = [from_api_json(item) for item in items if isinstance(item, dict)]
        return [r for r in records if r is not None]

    def _get_json(self, url: str, headers: dict[str, str]) -> dict[str, Any] | None:
        try:
            resp = self._client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise RegistryUnavailable(f"fetch {url}: {exc}") from exc
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            raise RegistryUnavailable(f"fetch {url}: HTTP {resp.status_code}")
        if "json" not in resp.headers.get("content-type", ""):
            return None  # an unknown identifier is answered with the HTML site, not JSON
        data = resp.json()
        return data if isinstance(data, dict) else None

    def fetch(self, fairsharing_id: str) -> PolicyRecord | None:
        public = self._get_json(
            PUBLIC_RECORD_URL.format(id=fairsharing_id), {"Accept": "application/json"}
        )
        record = from_public_json(public) if public else None
        if record is None or not (self.signed_in and record.numeric_id):
            return record
        api = self._get_json(RECORD.format(id=record.numeric_id), self._authorised())
        item = api.get("data") if api else None
        return (from_api_json(item) if isinstance(item, dict) else None) or record
