"""How this server asks FAIRsharing: one identified `httpx` client with a short retry.

Every request names this server and where its source is, and nothing else: no e-mail address, and
never anything about the person or project a query came from.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version
from typing import Any

import httpx

SOURCE_URL = "https://github.com/data-director-agent/data-director"
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class UnavailableError(Exception):
    """FAIRsharing could not be asked, or answered something unreadable. The message says why and
    holds nothing the caller sent."""


def _agent() -> str:
    try:
        number = version("data-director-mcp-fairsharing")
    except PackageNotFoundError:  # pragma: no cover - a source tree that is not installed
        number = "0"
    return f"data-director-mcp-fairsharing/{number} (+{SOURCE_URL})"


class Http:
    """`request` retries a busy or failing service after each pause in `pauses`, then gives up.
    `transport` replaces the network in tests."""

    def __init__(
        self,
        transport: httpx.BaseTransport | None = None,
        pauses: tuple[float, ...] = (0.5, 2.0),
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client = httpx.Client(
            timeout=20.0,
            transport=transport,
            follow_redirects=True,
            headers={"User-Agent": _agent(), "Accept": "application/json"},
        )
        self.pauses = pauses
        self.sleep = sleep

    def request(self, method: str, url: str, **options: Any) -> httpx.Response:
        for attempt in range(len(self.pauses) + 1):
            last = attempt == len(self.pauses)
            try:
                resp = self.client.request(method, url, **options)
            except httpx.HTTPError as exc:
                if last:
                    raise UnavailableError(f"FAIRsharing: {type(exc).__name__}") from None
            else:
                if last or resp.status_code not in RETRY_STATUSES:
                    return resp
            self.sleep(self.pauses[attempt])
        raise AssertionError("unreachable")  # pragma: no cover

    @staticmethod
    def json(resp: httpx.Response) -> Any:
        try:
            return resp.json()
        except ValueError:
            raise UnavailableError("FAIRsharing: an answer that is not JSON") from None
