"""How this server asks the registries: one `httpx` client per registry, identified, with a short
retry on a busy or failing service.

Every request names this server and where its source is, and nothing else: no e-mail address, and
never anything about the person or project the identifier came from. Crossref and DataCite
describe a contact address as optional; this server sends none.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from typing import Any

import httpx

SOURCE_URL = "https://github.com/data-director-agent/data-director"
TIMEOUT_S = 20.0
# Pauses before each retry, in seconds: two retries, then the lookup is reported as failed.
RETRY_PAUSES = (0.5, 2.0)
RETRIED = frozenset({429, 500, 502, 503, 504})


def user_agent() -> str:
    try:
        ver = version("data-director-mcp-fairsharing")
    except PackageNotFoundError:  # pragma: no cover - run from a source tree without installing
        ver = "0"
    return f"data-director-mcp-fairsharing/{ver} (+{SOURCE_URL})"


class UnavailableError(Exception):
    """A registry could not be asked, or gave an answer that cannot be read. The message says
    which registry and why, and holds nothing the caller sent but the identifier."""


@dataclass
class Http:
    """A registry's HTTP client. `transport` replaces the network in tests; `given` replaces the
    client altogether. `pauses` are the waits before each retry: none means no retry."""

    name: str
    headers: dict[str, str] = field(default_factory=dict)
    transport: httpx.BaseTransport | None = None
    pauses: tuple[float, ...] = RETRY_PAUSES
    sleep: Callable[[float], None] = time.sleep
    given: httpx.Client | None = field(default=None, repr=False)
    _client: httpx.Client | None = field(default=None, init=False, repr=False)

    def client(self) -> httpx.Client:
        if self.given is not None:
            return self.given
        if self._client is None:
            self._client = httpx.Client(
                timeout=TIMEOUT_S,
                headers={"User-Agent": user_agent(), **self.headers},
                transport=self.transport,
                follow_redirects=True,
            )
        return self._client

    def get(self, url: str, params: dict[str, str] | None = None) -> httpx.Response:
        """The answer to `GET url`, after retrying a busy or failing service. Raises
        `UnavailableError` when the service cannot be reached or keeps failing."""
        for pause in (*self.pauses, None):
            try:
                resp = self.client().get(url, params=params)
            except httpx.HTTPError as exc:
                if pause is None:
                    raise UnavailableError(f"{self.name}: {type(exc).__name__}") from None
                self.sleep(pause)
                continue
            if resp.status_code in RETRIED and pause is not None:
                self.sleep(pause)
                continue
            return resp
        raise AssertionError("unreachable")  # pragma: no cover

    def json(self, resp: httpx.Response) -> Any:
        try:
            return resp.json()
        except ValueError:
            raise UnavailableError(f"{self.name}: an answer that is not JSON") from None

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
