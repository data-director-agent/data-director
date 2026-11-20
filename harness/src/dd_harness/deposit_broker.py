"""The harness's client of the deposit broker (docs/specs/deposit.md, Depositing through an API).

The deposit broker holds each researcher's repository token and makes the repository's API calls.
The harness sends it a deposit grant and the exact bytes the grant names, on the broker's loopback
address, and reads back the draft it made or the reason it made none. The harness never sees a
token, and nothing it sends carries one (invariant 13).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from dd_harness.deposit_grants import DepositGrantMinter
from dd_sdk.deposit_grant import (
    DEPOSITS_PATH,
    HEADER_GRANT,
    HEADER_REASON,
    DepositAnswer,
    DepositGrantError,
    DepositReason,
    DepositRequest,
)

# Creating a draft is two or three calls to the repository, and the broker allows each its own
# timeout; this bounds the whole.
TIMEOUT_S = 120.0


@dataclass(frozen=True)
class DepositRefusal:
    """Why no draft was made: the broker's or the repository's status and a reason code, never
    a message that might quote what was sent."""

    status: int
    reason: DepositReason


@dataclass(frozen=True)
class DepositBroker:
    """Where the deposit broker is, and the minter of the grants it accepts."""

    url: str
    minter: DepositGrantMinter = field(repr=False)
    transport: httpx.BaseTransport | None = field(default=None, repr=False)

    def create(self, grant: str, request: DepositRequest) -> DepositAnswer | DepositRefusal:
        """Ask the broker for one draft. Never raises for the broker's or the repository's
        failure: that is an outcome to record (invariant 15)."""
        try:
            with httpx.Client(timeout=TIMEOUT_S, transport=self.transport) as client:
                response = client.post(
                    self.url.rstrip("/") + DEPOSITS_PATH,
                    json=request.to_json(),
                    headers={HEADER_GRANT: grant},
                )
        except httpx.HTTPError:
            return DepositRefusal(503, DepositReason.BROKER_UNAVAILABLE)
        if response.status_code == 201:
            try:
                return DepositAnswer.from_json(response.json())
            except ValueError, DepositGrantError:
                return DepositRefusal(502, DepositReason.BROKER_UNAVAILABLE)
        try:
            reason = DepositReason(response.headers.get(HEADER_REASON, ""))
        except ValueError:
            reason = DepositReason.BROKER_UNAVAILABLE
        return DepositRefusal(response.status_code, reason)
