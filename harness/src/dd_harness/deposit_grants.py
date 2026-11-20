"""Deposit grants and repository enrolment tickets: the harness's authority for the deposit broker
to make one draft as one person, and for the browser to connect that person's repository account
(docs/specs/deposit.md, Depositing through an API; the format is `dd_sdk.deposit_grant`).

They are signed with the model grants' key, so the deposit broker reads the same published JWKS,
and name the person by the same pseudonym, sealed to the deposit broker's own key. Their audience
and `typ` are the deposit broker's, so neither broker accepts the other's.
"""

from __future__ import annotations

import math
import secrets
from dataclasses import dataclass

from joserfc import jwe, jwt
from joserfc.jwk import ECKey

from dd_harness.model_grants import GrantMinter, broker_subject_key
from dd_sdk.contract.models import DepositConnector, Principal
from dd_sdk.deposit_grant import (
    CLAIM_APPROVAL,
    CLAIM_AUDIENCE,
    CLAIM_BASE_URL,
    CLAIM_EXPIRES,
    CLAIM_ISSUED_AT,
    CLAIM_ITEM_DIGEST,
    CLAIM_PACKAGE_DIGEST,
    CLAIM_PURPOSE,
    CLAIM_REPOSITORY,
    CLAIM_SUBJECT,
    CLAIM_TARGET,
    CLAIM_TICKET_ID,
    CLAIM_TRANSPORT,
    DEPOSIT_BROKER_AUDIENCE,
    GRANT_LIFETIME_S,
    GRANT_TYPE,
    SUBJECT_ENCRYPTION,
    SUBJECT_KEY_ALGORITHM,
    TICKET_LIFETIME_S,
    TICKET_PURPOSE,
    TICKET_TYPE,
)


@dataclass(frozen=True)
class DepositGrantMinter:
    """Mints deposit grants and repository enrolment tickets with the model grants' signing key
    and pseudonym secret."""

    grants: GrantMinter
    subject_key: ECKey

    @classmethod
    def from_material(cls, grants: GrantMinter, subject: str) -> DepositGrantMinter:
        """A minter from the model grants' minter and the deposit broker's public subject key, as
        text. The key checks are the model broker's: a public EC P-256 key."""
        return cls(grants, broker_subject_key(subject))

    def mint(
        self,
        *,
        acting_for: Principal,
        repository: str,
        connector: DepositConnector,
        package_digest: str,
        item_digest: str,
        approval: str,
        lifetime_s: float = GRANT_LIFETIME_S,
    ) -> str:
        """A grant for the deposit broker to create one draft in `repository` through
        `connector`, holding exactly the package and item whose digests it names, as
        `acting_for`, on the strength of the approval event `approval`. Accepted once."""
        issued_at = int(self.grants.clock())
        claims: dict[str, object] = {
            CLAIM_AUDIENCE: DEPOSIT_BROKER_AUDIENCE,
            CLAIM_ISSUED_AT: issued_at,
            CLAIM_EXPIRES: issued_at + max(1, math.floor(lifetime_s)),
            CLAIM_TICKET_ID: secrets.token_urlsafe(16),
            CLAIM_SUBJECT: self._seal(acting_for),
            CLAIM_REPOSITORY: repository,
            CLAIM_TRANSPORT: connector.transport,
            CLAIM_BASE_URL: connector.base_url,
            CLAIM_PACKAGE_DIGEST: package_digest,
            CLAIM_ITEM_DIGEST: item_digest,
            CLAIM_APPROVAL: approval,
        }
        if connector.target:
            claims[CLAIM_TARGET] = connector.target
        return self._sign(GRANT_TYPE, claims)

    def ticket(
        self, *, acting_for: Principal, lifetime_s: float = TICKET_LIFETIME_S
    ) -> tuple[str, int]:
        """A single-use ticket for `acting_for` to make one request to the deposit broker's
        account interface, and the time it expires."""
        issued_at = int(self.grants.clock())
        expires_at = issued_at + max(1, math.floor(lifetime_s))
        claims: dict[str, object] = {
            CLAIM_AUDIENCE: DEPOSIT_BROKER_AUDIENCE,
            CLAIM_ISSUED_AT: issued_at,
            CLAIM_EXPIRES: expires_at,
            CLAIM_TICKET_ID: secrets.token_urlsafe(16),
            CLAIM_PURPOSE: TICKET_PURPOSE,
            CLAIM_SUBJECT: self._seal(acting_for),
        }
        return self._sign(TICKET_TYPE, claims), expires_at

    def _sign(self, typ: str, claims: dict[str, object]) -> str:
        key = self.grants.signing_key
        return jwt.encode({"alg": self.grants.algorithm, "kid": key.kid, "typ": typ}, claims, key)

    def _seal(self, principal: Principal) -> str:
        return jwe.encrypt_compact(
            {"alg": SUBJECT_KEY_ALGORITHM, "enc": SUBJECT_ENCRYPTION},
            self.grants.pseudonym(principal).encode("utf-8"),
            self.subject_key,
            algorithms=[SUBJECT_KEY_ALGORITHM, SUBJECT_ENCRYPTION],
        )
