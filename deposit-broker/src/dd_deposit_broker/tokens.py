"""Checking a deposit grant and a repository enrolment ticket.

This is governance and the deposit broker's own code. A grant or a ticket is accepted only if:

- its signature is the harness's, checked against the harness's published keys (JWKS) with one of
  `dd_sdk.deposit_grant.SIGNING_ALGORITHMS`;
- its JOSE `typ` is the grant's or the ticket's, as the request expects;
- it is addressed to the deposit broker and within its lifetime, allowing `LEEWAY_S` of skew;
- it has the grant's or the ticket's shape (`DepositGrantClaims`, `RepositoryTicketClaims`);
- its sealed pseudonym opens with the deposit broker's subject key;
- its `jti` has not been accepted before: each is accepted once.

The checks of the signature, the time and the sealed pseudonym are those every service that holds
people's credentials shares (`dd_sdk.harness_tokens`). A model grant or a model enrolment ticket
has another audience and `typ`, and is refused.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from joserfc.jwk import ECKey

from dd_deposit_broker.reasons import Refused
from dd_deposit_broker.store import Store
from dd_sdk import harness_tokens
from dd_sdk.deposit_grant import (
    DEPOSIT_BROKER_AUDIENCE,
    GRANT_TYPE,
    TICKET_TYPE,
    DepositGrantClaims,
    DepositGrantError,
    DepositReason,
    RepositoryTicketClaims,
)
from dd_sdk.harness_tokens import LEEWAY_S
from dd_sdk.harness_tokens import HarnessKeys as HarnessKeys
from dd_sdk.harness_tokens import fetch_file as fetch_file
from dd_sdk.harness_tokens import fetch_url as fetch_url
from dd_sdk.harness_tokens import subject_key as subject_key


@dataclass(frozen=True)
class VerifiedGrant:
    claims: DepositGrantClaims
    # Known only to the broker: never logged, never returned.
    pseudonym: str = field(repr=False)


@dataclass(frozen=True)
class Verifier:
    """Checks the deposit grants and repository enrolment tickets the harness signs, each once."""

    keys: HarnessKeys
    subject_key: ECKey = field(repr=False)
    store: Store
    now: Callable[[], float] = time.time

    def grant(self, token: str | None) -> VerifiedGrant:
        """The grant's claims and the pseudonym it names. Raises `Refused`."""
        if not token:
            raise Refused(401, DepositReason.GRANT_MISSING)
        decoded = self._decode(
            token, GRANT_TYPE, DepositReason.GRANT_INVALID, DepositReason.GRANT_EXPIRED
        )
        try:
            claims = DepositGrantClaims.from_claims(decoded)
        except DepositGrantError:
            raise Refused(401, DepositReason.GRANT_INVALID) from None
        pseudonym = self._open(claims.subject, DepositReason.GRANT_INVALID)
        if not self.store.use_once(claims.grant_id, claims.expires_at + LEEWAY_S):
            raise Refused(401, DepositReason.GRANT_USED)
        return VerifiedGrant(claims, pseudonym)

    def ticket(self, token: str | None) -> str:
        """The pseudonym a repository enrolment ticket names. Raises `Refused`."""
        if not token:
            raise Refused(401, DepositReason.TICKET_MISSING)
        decoded = self._decode(
            token, TICKET_TYPE, DepositReason.TICKET_INVALID, DepositReason.TICKET_EXPIRED
        )
        try:
            claims = RepositoryTicketClaims.from_claims(decoded)
        except DepositGrantError:
            raise Refused(401, DepositReason.TICKET_INVALID) from None
        pseudonym = self._open(claims.subject, DepositReason.TICKET_INVALID)
        if not self.store.use_once(claims.ticket_id, claims.expires_at + LEEWAY_S):
            raise Refused(401, DepositReason.TICKET_USED)
        return pseudonym

    def _decode(
        self, token: str, typ: str, invalid: DepositReason, expired: DepositReason
    ) -> dict[str, Any]:
        try:
            return harness_tokens.decode(
                token,
                self.keys,
                self.now,
                audience=DEPOSIT_BROKER_AUDIENCE,
                typ_allowed=lambda found: found == typ,
            )
        except harness_tokens.KeysUnavailable:
            raise Refused(503, invalid) from None
        except harness_tokens.TokenRejected as rejected:
            raise Refused(401, expired if rejected.expired else invalid) from None

    def _open(self, subject: str, invalid: DepositReason) -> str:
        try:
            return harness_tokens.open_subject(self.subject_key, subject)
        except harness_tokens.TokenRejected:
            raise Refused(401, invalid) from None
