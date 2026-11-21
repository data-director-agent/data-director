"""Checking a model grant (docs/specs/model-accounts.md, invariant 7) and an enrolment ticket.

This is governance and the broker's own code. A grant is accepted only if:

- its signature is the harness's, checked against the harness's published keys (JWKS) with one
  of `dd_sdk.model_grant.SIGNING_ALGORITHMS`;
- it is addressed to the broker and is within its lifetime, allowing `LEEWAY_S` of clock skew;
- it has the model grant's shape (`ModelGrantClaims`);
- it names the agent whose own credential made the call;
- its sealed pseudonym opens with the broker's subject key.

Whether the model asked for is one the grant allows is checked per call, by `VerifiedGrant.allows`.

An enrolment ticket (`TicketVerifier`) is checked the same way, except that it names no agent, has
the ticket's `typ` and purpose, and is accepted once: its `jti` is recorded until it expires.

The harness signs grants and tickets (`dd_harness.model_grants`) and publishes its public keys at
`/.well-known/jwks.json`. The broker reads them from `DD_BROKER_HARNESS_JWKS_URL`, normally that
address, or from `DD_BROKER_HARNESS_JWKS_FILE`.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from joserfc.jwk import ECKey

from dd_broker.reasons import Reason, Refused
from dd_broker.store import Store
from dd_sdk import harness_tokens
from dd_sdk.harness_tokens import LEEWAY_S as LEEWAY_S
from dd_sdk.harness_tokens import HarnessKeys as HarnessKeys
from dd_sdk.harness_tokens import fetch_file as fetch_file
from dd_sdk.harness_tokens import fetch_url as fetch_url
from dd_sdk.harness_tokens import subject_key as subject_key
from dd_sdk.model_grant import (
    BROKER_AUDIENCE,
    TICKET_TYPE,
    EnrolmentTicketClaims,
    ModelGrantClaims,
    ModelGrantError,
)


@dataclass(frozen=True)
class VerifiedGrant:
    claims: ModelGrantClaims
    # Known only to the broker: never logged, never returned.
    pseudonym: str = field(repr=False)

    def allows(self, model: str) -> bool:
        return model in self.claims.models


class GrantVerifier:
    def __init__(
        self,
        keys: HarnessKeys,
        subject_key: ECKey,
        *,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._keys = keys
        self._subject_key = subject_key
        self._now = now

    def verify(self, token: str | None, agent_id: str) -> VerifiedGrant:
        if not token:
            raise Refused(401, Reason.GRANT_MISSING)
        decoded = _decode(
            token,
            self._keys,
            self._now,
            typ_allowed=lambda typ: typ != TICKET_TYPE,
            invalid=Reason.GRANT_INVALID,
            expired=Reason.GRANT_EXPIRED,
        )
        try:
            claims = ModelGrantClaims.from_claims(decoded)
        except ModelGrantError:
            raise Refused(401, Reason.GRANT_INVALID) from None
        if claims.agent != agent_id:
            raise Refused(403, Reason.GRANT_AGENT_MISMATCH)
        pseudonym = open_subject(self._subject_key, claims.subject, Reason.GRANT_INVALID)
        return VerifiedGrant(claims=claims, pseudonym=pseudonym)


class TicketVerifier:
    """Checks an enrolment ticket and accepts it once (docs/specs/model-accounts.md, Enrolment)."""

    def __init__(
        self,
        keys: HarnessKeys,
        subject_key: ECKey,
        store: Store,
        *,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._keys = keys
        self._subject_key = subject_key
        self._store = store
        self._now = now

    def verify(self, token: str | None) -> str:
        """The pseudonym the ticket names. Raises `Refused` for a missing, invalid, expired or
        already-used ticket."""
        if not token:
            raise Refused(401, Reason.TICKET_MISSING)
        decoded = _decode(
            token,
            self._keys,
            self._now,
            typ_allowed=lambda typ: typ == TICKET_TYPE,
            invalid=Reason.TICKET_INVALID,
            expired=Reason.TICKET_EXPIRED,
        )
        try:
            claims = EnrolmentTicketClaims.from_claims(decoded)
        except ModelGrantError:
            raise Refused(401, Reason.TICKET_INVALID) from None
        pseudonym = open_subject(self._subject_key, claims.subject, Reason.TICKET_INVALID)
        # Recorded only once the ticket is known to be good, so nonsense cannot fill the table.
        if not self._store.use_ticket(claims.ticket_id, claims.expires_at + LEEWAY_S):
            raise Refused(401, Reason.TICKET_USED)
        return pseudonym


def _decode(
    token: str,
    keys: HarnessKeys,
    now: Callable[[], float],
    *,
    typ_allowed: Callable[[Any], bool],
    invalid: Reason,
    expired: Reason,
) -> dict[str, Any]:
    """The claims of a token the harness signed for the broker, within its lifetime."""
    try:
        return harness_tokens.decode(
            token, keys, now, audience=BROKER_AUDIENCE, typ_allowed=typ_allowed
        )
    except harness_tokens.KeysUnavailable:
        raise Refused(503, invalid) from None
    except harness_tokens.TokenRejected as rejected:
        raise Refused(401, expired if rejected.expired else invalid) from None


def open_subject(key: ECKey, subject: str, invalid: Reason) -> str:
    """The pseudonym sealed to the broker in a grant's or a ticket's `dd_subject`."""
    try:
        return harness_tokens.open_subject(key, subject)
    except harness_tokens.TokenRejected:
        raise Refused(401, invalid) from None
