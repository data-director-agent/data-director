"""Model grant keys for tests (docs/specs/model-accounts.md, The grant).

`GrantKeys` generates a signing key, the broker's subject key pair and a pseudonym secret, gives the
`GrantMinter` a conductor mints with, and opens a grant as the broker would: it checks the
signature against the published keys and decrypts the sealed pseudonym. No key here is used
outside a test.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from typing import Any

from joserfc import jwe, jwt
from joserfc.jwk import ECKey, KeySet, RSAKey

from dd_harness.model_grants import GrantMinter
from dd_sdk.model_grant import (
    CLAIM_SUBJECT,
    SIGNING_ALGORITHMS,
    SUBJECT_ENCRYPTION,
    SUBJECT_KEY_ALGORITHM,
)


@dataclass(frozen=True)
class OpenedGrant:
    """A grant's header and claims once its signature is checked, and the pseudonym it seals."""

    header: dict[str, Any]
    claims: dict[str, Any]
    pseudonym: str


@dataclass(frozen=True)
class GrantKeys:
    signing_key: RSAKey = field(
        default_factory=lambda: RSAKey.generate_key(2048, parameters={"kid": "harness-test"})
    )
    subject_key: ECKey = field(default_factory=lambda: ECKey.generate_key("P-256"))
    secret: bytes = field(default_factory=lambda: secrets.token_bytes(32), repr=False)

    def minter(self) -> GrantMinter:
        public = ECKey.import_key(self.subject_key.as_dict(private=False))
        return GrantMinter(self.signing_key, public, self.secret)

    def open(self, grant: str, jwks: dict[str, Any] | None = None) -> OpenedGrant:
        """Verify `grant` against `jwks` (the minter's own published keys by default) and
        decrypt its pseudonym with the broker's private subject key."""
        keys = KeySet.import_key_set(jwks or self.minter().jwks())  # type: ignore[arg-type]
        token = jwt.decode(grant, keys, algorithms=list(SIGNING_ALGORITHMS))
        opened = jwe.decrypt_compact(
            token.claims[CLAIM_SUBJECT],
            self.subject_key,
            algorithms=[SUBJECT_KEY_ALGORITHM, SUBJECT_ENCRYPTION],
        )
        return OpenedGrant(
            dict(token.header), dict(token.claims), (opened.plaintext or b"").decode("utf-8")
        )
