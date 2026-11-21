"""The harness's client of the deposit broker (docs/specs/deposit.md, Depositing through an API).

The deposit broker holds each researcher's repository token and makes the repository's API calls.
The harness sends it a deposit grant and the exact bytes the grant names, on the broker's loopback
address, and reads back the draft it made or the reason it made none. The harness never sees a
token, and nothing it sends carries one (invariant 13).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import httpx

from dd_harness.deposit_grants import DepositGrantMinter
from dd_harness.model_grants import GrantMinter
from dd_sdk.credentials import api_key
from dd_sdk.deposit_grant import (
    DEPOSITS_PATH,
    HEADER_GRANT,
    HEADER_REASON,
    DepositAnswer,
    DepositGrantError,
    DepositReason,
    DepositRequest,
)

# Where the deposit broker is, and its public subject key (as `NAME` or `NAME_FILE`).
URL = "DD_DEPOSIT_BROKER_URL"
SUBJECT_KEY = "DD_DEPOSIT_BROKER_SUBJECT_KEY"

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


def from_env(
    env: Mapping[str, str], grants: GrantMinter | None, grant_settings: Sequence[str]
) -> DepositBroker | None:
    """The deposit broker the harness asks for drafts, or None if the deployment deposits only by
    hand. `DD_DEPOSIT_BROKER_URL` is its loopback address and `DD_DEPOSIT_BROKER_SUBJECT_KEY` its
    public P-256 key. Both, or neither; and the grants are signed with the model grants' key and
    pseudonym secret (`grant_settings`), so `grants` must exist. Raises `ValueError`, or what
    reading the key raises, naming the setting and never its value."""
    url = env.get(URL) or None
    has_key = bool(env.get(SUBJECT_KEY) or env.get(f"{SUBJECT_KEY}_FILE"))
    if url is None and not has_key:
        return None
    if url is None or not has_key:
        raise ValueError(f"depositing through an API needs {URL} and {SUBJECT_KEY}; one is unset")
    if grants is None:
        raise ValueError(
            "depositing through an API signs its grants with the model grants' key: "
            f"set {', '.join(grant_settings)}"
        )
    minter = DepositGrantMinter.from_material(grants, api_key(env, SUBJECT_KEY))
    return DepositBroker(url, minter)
