"""FAIRsharing's API: the sign-in, the authenticated search and record reads.

- Search needs a JWT: `POST https://api.fairsharing.org/users/sign_in` with
  `{"user": {"login", "password"}}`, then `POST /search/fairsharing_records` with the filters in
  the query string and `Authorization: Bearer <jwt>`. Credentials come from `FAIRSHARING_LOGIN`
  and `FAIRSHARING_PASSWORD`; the sign-in body is filtered from cassettes.
- A record's public route (`https://fairsharing.org/<id>`) needs no account.

The client returns FAIRsharing's JSON; each agent projects the records it cites itself, and
chooses its own filters. Any transport failure raises `RegistryUnavailable`, and the agent falls
back to its snapshot and marks it stale. One token is kept per client.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from dd_sdk.registry.retrieve import RegistryUnavailable

API_BASE = "https://api.fairsharing.org"
SIGN_IN = f"{API_BASE}/users/sign_in"
SEARCH = f"{API_BASE}/search/fairsharing_records"
RECORD = f"{API_BASE}/fairsharing_records/{{id}}"
PUBLIC_RECORD = "https://fairsharing.org/{id}"
TIMEOUT_S = 20.0
JSON = {"Accept": "application/json"}


class FairsharingClient:
    def __init__(
        self,
        client: httpx.Client | None = None,
        login: str | None = None,
        password: str | None = None,
        *,
        follow_redirects: bool = False,
    ) -> None:
        self._client = client or httpx.Client(
            timeout=TIMEOUT_S, follow_redirects=follow_redirects, headers=JSON
        )
        self._login = login or os.environ.get("FAIRSHARING_LOGIN")
        self._password = password or os.environ.get("FAIRSHARING_PASSWORD")
        self._jwt: str | None = None

    @property
    def signed_in(self) -> bool:
        """Whether there are credentials to sign in with."""
        return bool(self._login and self._password)

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

    def authorised(self) -> dict[str, str]:
        """Headers for an authenticated request, signing in first if need be."""
        return {"Authorization": f"Bearer {self._token()}", "Accept": "application/json"}

    def search(self, params: dict[str, str]) -> list[Any]:
        """The `data` array of one search, in FAIRsharing's relevance order."""
        try:
            resp = self._client.post(SEARCH, params=params, headers=self.authorised())
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise RegistryUnavailable(f"search: {exc}") from exc
        body = resp.json()
        items = body.get("data") if isinstance(body, dict) else None
        if not isinstance(items, list):
            raise RegistryUnavailable("search returned no data array; check credentials")
        return items

    def get_json(self, url: str, headers: dict[str, str] | None = None) -> dict[str, Any] | None:
        """The JSON object at `url`, or None when FAIRsharing has no such record."""
        try:
            resp = self._client.get(url, headers=headers or JSON)
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
