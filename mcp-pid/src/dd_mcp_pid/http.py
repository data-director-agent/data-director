"""How this server asks the registries: one `httpx` client per registry, identified, with a short
retry on a busy or failing service.

Every request names this server and where its source is, and never anything about the person or
project the identifier came from. A deployment may also give its operators' contact address
(`DD_REGISTRY_CONTACT`), which the DataCite and Crossref clients add as `mailto:` so that those
registries count the server in their identified, faster pool. With none, no address is sent.
"""

from __future__ import annotations

import re
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
# A plain address: nothing that could end the User-Agent's comment or start another header.
ADDRESS = re.compile(r"[^\s@<>();,\"\\]+@[^\s@<>();,\"\\]+\.[^\s@<>();,\"\\]+")


def contact_address(value: str) -> str | None:
    """`value` as a contact address, or None when it is blank. Raises `ValueError` when it is
    not one plain address."""
    text = value.strip()
    if not text:
        return None
    if not ADDRESS.fullmatch(text):
        raise ValueError(f"{text!r} is not an e-mail address")
    return text


def user_agent(contact: str | None = None) -> str:
    """This server's User-Agent, with `mailto:contact` when a contact address is given."""
    try:
        ver = version("data-director-mcp-pid")
    except PackageNotFoundError:  # pragma: no cover - run from a source tree without installing
        ver = "0"
    mailto = f"; mailto:{contact}" if contact else ""
    return f"data-director-mcp-pid/{ver} (+{SOURCE_URL}{mailto})"


class UnavailableError(Exception):
    """A registry could not be asked, or gave an answer that cannot be read. The message says
    which registry and why, and holds nothing the caller sent but the identifier."""


@dataclass
class Http:
    """A registry's HTTP client. `transport` replaces the network in tests; `given` replaces the
    client altogether. `pauses` are the waits before each retry: none means no retry. `contact`
    is the operators' address the User-Agent carries, if any."""

    name: str
    headers: dict[str, str] = field(default_factory=dict)
    contact: str | None = None
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
                headers={"User-Agent": user_agent(self.contact), **self.headers},
                transport=self.transport,
                follow_redirects=True,
            )
        return self._client

    def get(
        self,
        url: str,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """The answer to `GET url`, after retrying a busy or failing service. Raises
        `UnavailableError` when the service cannot be reached or keeps failing."""
        for pause in (*self.pauses, None):
            try:
                resp = self.client().get(url, params=params, headers=headers)
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
