"""FAIRsharing's API: the sign-in, the authenticated search and record reads, through a local
cache (`dd_registry_cache`, configured by `dd_sdk.registry.caching`).

- Search needs a JWT: `POST https://api.fairsharing.org/users/sign_in` with
  `{"user": {"login", "password"}}`, then `POST /search/fairsharing_records` with the filters in
  the query string and `Authorization: Bearer <jwt>`. Credentials come from `FAIRSHARING_LOGIN`
  and `FAIRSHARING_PASSWORD`; the sign-in body is filtered from cassettes. The token is kept until
  shortly before the expiry its `exp` claim gives, and a request it no longer opens (401) signs in
  once more and is sent again. Neither the token nor the credentials are ever cached.
- A record's public route (`https://fairsharing.org/<id>`) needs no account.

Every answer goes through the cache, as FAIRsharing sends `Cache-Control: max-age=0` and an HTTP
cache would keep nothing (#327). A record is answered from the cache within its time to live,
then revalidated with `If-None-Match` against the weak `ETag` FAIRsharing gives, which a 304
confirms. "No such record" is kept too, for a shorter time. A search is a POST, so it is cached
under its normalised filters. When FAIRsharing cannot be asked, an expired entry answers, marked
stale; only when there is none does `RegistryUnavailable` reach the agent, which then falls back
to its snapshot and marks that stale.

The client returns FAIRsharing's JSON, with where each answer came from (`Fetched`); each agent
projects the records it cites itself, chooses its own filters, and notes each record's origin
for its evidence (`dd_sdk.registry.provenance`).
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import time
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlencode

import httpx

from dd_registry_cache import Cache, Entry, Fresh, Missing, NotModified
from dd_sdk.registry import pinned
from dd_sdk.registry.caching import Ttls, cache_from_env, memory_cache, ttls_from_env
from dd_sdk.registry.provenance import Fetched
from dd_sdk.registry.retrieve import RegistryUnavailable

API_BASE = "https://api.fairsharing.org"
SIGN_IN = f"{API_BASE}/users/sign_in"
SEARCH = f"{API_BASE}/search/fairsharing_records"
RECORD = f"{API_BASE}/fairsharing_records/{{id}}"
PUBLIC_RECORD = "https://fairsharing.org/{id}"
TIMEOUT_S = 20.0
JSON = {"Accept": "application/json"}
DISTRIBUTION = "data-director-sdk"
# A token this close to its expiry is renewed before it is sent.
RENEW_BEFORE_S = 60.0


def token_expiry(jwt: str) -> float | None:
    """The `exp` claim of a JWT, in POSIX seconds, read without verifying the token (it is our
    own, from FAIRsharing's sign-in); None if it has none or cannot be read."""
    try:
        payload = jwt.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except IndexError, ValueError, binascii.Error:
        return None
    exp = claims.get("exp") if isinstance(claims, dict) else None
    return float(exp) if isinstance(exp, int | float) else None


def search_key(params: Mapping[str, str]) -> dict[str, str]:
    """The filters of a search with the query text's whitespace collapsed, so that searches that
    differ only in spacing share a cache entry. They are also what is sent."""
    return {k: " ".join(v.split()) if k == "q" else v for k, v in sorted(params.items())}


class FairsharingClient:
    def __init__(
        self,
        client: httpx.Client | None = None,
        login: str | None = None,
        password: str | None = None,
        *,
        follow_redirects: bool = False,
        cache: Cache | None = None,
        ttls: Ttls | None = None,
        now: Callable[[], float] = time.time,
    ) -> None:
        # Named, as every other registry the project asks is told who is asking (never a person).
        self._client = client or httpx.Client(
            timeout=TIMEOUT_S,
            follow_redirects=follow_redirects,
            headers={**JSON, "User-Agent": pinned.user_agent(DISTRIBUTION, DISTRIBUTION)},
        )
        self._login = login or os.environ.get("FAIRSHARING_LOGIN")
        self._password = password or os.environ.get("FAIRSHARING_PASSWORD")
        self._cache = cache or memory_cache(now)
        self._ttls = ttls or Ttls()
        self._now = now
        self._jwt: str | None = None
        self._jwt_expires = float("inf")

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str],
        *,
        login: str | None = None,
        password: str | None = None,
        follow_redirects: bool = False,
    ) -> FairsharingClient:
        """A client whose cache is configured by the agent's environment
        (`dd_sdk.registry.caching`)."""
        return cls(
            login=login,
            password=password,
            follow_redirects=follow_redirects,
            cache=cache_from_env(environ, "fairsharing"),
            ttls=ttls_from_env(environ),
        )

    @property
    def signed_in(self) -> bool:
        """Whether there are credentials to sign in with."""
        return bool(self._login and self._password)

    def _token(self) -> str:
        if self._jwt and self._now() < self._jwt_expires - RENEW_BEFORE_S:
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
        self._jwt_expires = token_expiry(self._jwt) or float("inf")
        return self._jwt

    def _once(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        authorised: bool,
        params: Mapping[str, str] | None,
    ) -> httpx.Response:
        sent = {**headers, **({"Authorization": f"Bearer {self._token()}"} if authorised else {})}
        try:
            return self._client.request(method, url, headers=sent, params=params)
        except httpx.HTTPError as exc:
            raise RegistryUnavailable(f"{method} {url}: {exc}") from exc

    def _send(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] = JSON,
        authorised: bool = False,
        params: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        """One request; signed in if `authorised`, and sent again once, after signing in again,
        if FAIRsharing no longer accepts the token."""

        def once() -> httpx.Response:
            return self._once(method, url, headers=headers, authorised=authorised, params=params)

        resp = once()
        if authorised and resp.status_code == 401:
            self._jwt = None
            resp = once()
        return resp

    def search(self, params: Mapping[str, str]) -> Fetched[list[Any]]:
        """The `data` array of one search, in FAIRsharing's relevance order."""
        sent = search_key(params)

        def fetch(_previous: Entry | None) -> Fresh:
            resp = self._send("POST", SEARCH, authorised=True, params=sent)
            if resp.status_code >= 400:
                raise RegistryUnavailable(f"search: HTTP {resp.status_code}")
            try:
                body = resp.json()
            except ValueError as exc:
                raise RegistryUnavailable(f"search returned no JSON: {exc}") from exc
            items = body.get("data") if isinstance(body, dict) else None
            if not isinstance(items, list):
                raise RegistryUnavailable("search returned no data array; check credentials")
            return Fresh(json.dumps(items).encode(), "application/json")

        answer = self._cache.lookup(f"POST {SEARCH}?{urlencode(sent)}", self._ttls.searches, fetch)
        items = json.loads(answer.body) if answer.body is not None else []
        return Fetched.of(items, answer)

    def get_json(self, url: str, *, authorised: bool = False) -> Fetched[dict[str, Any] | None]:
        """The JSON object at `url`, or None when FAIRsharing has no such record. `authorised`
        signs the request in; the token is never part of the cache key or entry."""

        def fetch(previous: Entry | None) -> Fresh | Missing | NotModified:
            headers = dict(JSON)
            if previous is not None and previous.etag and not previous.missing:
                headers["If-None-Match"] = previous.etag
            resp = self._send("GET", url, headers=headers, authorised=authorised)
            if resp.status_code == 304 and "If-None-Match" in headers:
                return NotModified()
            if resp.status_code == 404:
                return Missing()
            if resp.status_code >= 400:
                raise RegistryUnavailable(f"fetch {url}: HTTP {resp.status_code}")
            content_type = resp.headers.get("content-type", "")
            if "json" not in content_type:
                return Missing()  # an unknown identifier is answered with the HTML site
            try:
                data = resp.json()
            except ValueError as exc:
                raise RegistryUnavailable(f"fetch {url}: not JSON: {exc}") from exc
            if not isinstance(data, dict):
                return Missing()
            return Fresh(resp.content, content_type, resp.headers.get("etag"))

        answer = self._cache.lookup(f"GET {url}", self._ttls.records, fetch)
        data = json.loads(answer.body) if answer.body is not None else None
        return Fetched.of(data if isinstance(data, dict) else None, answer)
