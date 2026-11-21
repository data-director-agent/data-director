"""FAIRsharing's API: the public record route, and the signed-in search.

- A record by identifier needs no account: `GET https://fairsharing.org/<id>`.
- Search needs a JWT: `POST https://api.fairsharing.org/users/sign_in` with
  `{"user": {"login", "password"}}`, then `POST /search/fairsharing_records` with the filters in
  the query string and `Authorization: Bearer <jwt>`. The credentials are the server's own
  (`FAIRSHARING_LOGIN`, `FAIRSHARING_PASSWORD`) and never reach a client or an answer.

Only a record identifier, or the words searched for, ever leave this server.
"""

from __future__ import annotations

import os
import re
from typing import Any

from dd_mcp_fairsharing.http import Http, UnavailableError
from dd_mcp_fairsharing.records import PUBLIC_RECORD_URL, Record, from_api_json, from_public_json

API_BASE = "https://api.fairsharing.org"
SIGN_IN = f"{API_BASE}/users/sign_in"
SEARCH = f"{API_BASE}/search/fairsharing_records"
MAX_LIMIT = 25

_IDENTIFIER = re.compile(
    r"^(?:https?://fairsharing\.org/|https?://doi\.org/10\.25504/|10\.25504/)?"
    r"(FAIRsharing\.[A-Za-z0-9]{4,8}|\d{1,6})/?$",
    re.IGNORECASE,
)


def record_id(value: str) -> str | None:
    """`value` as a FAIRsharing identifier (`FAIRsharing.xxxxx` or a numeric id), accepting the
    fairsharing.org URL and DOI forms; None when it is none of these."""
    found = _IDENTIFIER.match(value.strip())
    if not found:
        return None
    ident = found.group(1)
    return "FAIRsharing." + ident.split(".", 1)[1] if "." in ident else ident


class NoAccountError(UnavailableError):
    """Search was asked for and the server has no FAIRsharing account."""


class Fairsharing:
    def __init__(
        self, http: Http | None = None, login: str | None = None, password: str | None = None
    ) -> None:
        self.http = http or Http()
        self._login = login or os.environ.get("FAIRSHARING_LOGIN")
        self._password = password or os.environ.get("FAIRSHARING_PASSWORD")
        self._jwt: str | None = None

    @property
    def can_search(self) -> bool:
        return bool(self._login and self._password)

    def get(self, ident: str) -> Record | None:
        """The record, or None when FAIRsharing has no such identifier."""
        resp = self.http.request("GET", PUBLIC_RECORD_URL.format(id=ident))
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise UnavailableError(f"FAIRsharing: HTTP {resp.status_code}")
        if "json" not in resp.headers.get("content-type", ""):
            return None  # an unknown identifier is answered with the HTML site
        data = self.http.json(resp)
        return from_public_json(data) if isinstance(data, dict) else None

    def _token(self) -> str:
        if self._jwt:
            return self._jwt
        if not self.can_search:
            raise NoAccountError("FAIRsharing: search needs an account, and this server has none")
        resp = self.http.request(
            "POST", SIGN_IN, json={"user": {"login": self._login, "password": self._password}}
        )
        if resp.status_code != 200:
            raise UnavailableError(f"FAIRsharing sign-in: HTTP {resp.status_code}")
        body = self.http.json(resp)
        jwt = body.get("jwt") if isinstance(body, dict) else None
        if not jwt:
            raise UnavailableError("FAIRsharing sign-in: no token")
        self._jwt = str(jwt)
        return self._jwt

    def search(self, text: str, record_type: str | None = None, limit: int = 10) -> list[Record]:
        """Records matching `text`, in FAIRsharing's relevance order."""
        params = {
            "q": text,
            "page[number]": "1",
            "page[size]": str(max(1, min(limit, MAX_LIMIT))),
        }
        if record_type:
            params["record_type"] = record_type
        token = self._token()
        resp = self.http.request(
            "POST", SEARCH, params=params, headers={"Authorization": f"Bearer {token}"}
        )
        if resp.status_code == 401:
            self._jwt = None  # expired: sign in afresh on the next call
        if resp.status_code != 200:
            raise UnavailableError(f"FAIRsharing search: HTTP {resp.status_code}")
        body: Any = self.http.json(resp)
        items = body.get("data") if isinstance(body, dict) else None
        if not isinstance(items, list):
            raise UnavailableError("FAIRsharing search: no data array")
        return [from_api_json(i) for i in items if isinstance(i, dict)]
