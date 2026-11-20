"""Checking a deposit grant and a repository enrolment ticket.

This is governance and the deposit broker's own code. A grant or a ticket is accepted only if:

- its signature is the harness's, checked against the harness's published keys (JWKS) with one of
  `dd_sdk.deposit_grant.SIGNING_ALGORITHMS`;
- its JOSE `typ` is the grant's or the ticket's, as the request expects;
- it is addressed to the deposit broker and within its lifetime, allowing `LEEWAY_S` of skew;
- it has the grant's or the ticket's shape (`DepositGrantClaims`, `RepositoryTicketClaims`);
- its sealed pseudonym opens with the deposit broker's subject key;
- its `jti` has not been accepted before: each is accepted once.

A model grant or a model enrolment ticket has another audience and `typ`, and is refused.
"""

from __future__ import annotations

import contextlib
import json
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from joserfc import jwe, jws, jwt
from joserfc.errors import ExpiredTokenError, InvalidClaimError, JoseError, MissingClaimError
from joserfc.jwk import ECKey, KeySet

from dd_deposit_broker.reasons import Refused
from dd_deposit_broker.store import Store
from dd_sdk.deposit_grant import (
    DEPOSIT_BROKER_AUDIENCE,
    GRANT_TYPE,
    SIGNING_ALGORITHMS,
    SUBJECT_ENCRYPTION,
    SUBJECT_KEY_ALGORITHM,
    TICKET_TYPE,
    DepositGrantClaims,
    DepositGrantError,
    DepositReason,
    RepositoryTicketClaims,
)

LEEWAY_S = 30
MIN_REFETCH_S = 60
FETCH_TIMEOUT_S = 10.0
MAX_PSEUDONYM_CHARS = 256

_SUBJECT_REGISTRY = jwe.JWERegistry(algorithms=[SUBJECT_KEY_ALGORITHM, SUBJECT_ENCRYPTION])


def fetch_url(url: str, *, transport: httpx.BaseTransport | None = None) -> Callable[[], Any]:
    def fetch() -> Any:
        with httpx.Client(timeout=FETCH_TIMEOUT_S, transport=transport) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.json()

    return fetch


def fetch_file(path: Path) -> Callable[[], Any]:
    def fetch() -> Any:
        return json.loads(path.read_text(encoding="utf-8"))

    return fetch


class HarnessKeys:
    """The harness's public signing keys, fetched once and again when a token names a key not
    held, at most once every `MIN_REFETCH_S`."""

    def __init__(
        self, fetch: Callable[[], Any], *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._fetch = fetch
        self._clock = clock
        self._keys: KeySet | None = None
        self._fetched_at = float("-inf")
        self._lock = threading.Lock()

    def key_set(self, kid: str | None, invalid: DepositReason) -> KeySet:
        with self._lock:
            held = self._keys is not None and any(key.kid == kid for key in self._keys)
            if not held and self._clock() - self._fetched_at >= MIN_REFETCH_S:
                self._fetched_at = self._clock()
                with contextlib.suppress(httpx.HTTPError, OSError, ValueError, JoseError):
                    self._keys = KeySet.import_key_set(self._fetch())
            if self._keys is None:
                raise Refused(503, invalid)
            return self._keys


@dataclass(frozen=True)
class VerifiedGrant:
    claims: DepositGrantClaims
    # Known only to the broker: never logged, never returned.
    pseudonym: str = field(repr=False)


class Verifier:
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
        if not self._store.use_once(claims.grant_id, claims.expires_at + LEEWAY_S):
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
        if not self._store.use_once(claims.ticket_id, claims.expires_at + LEEWAY_S):
            raise Refused(401, DepositReason.TICKET_USED)
        return pseudonym

    def _decode(
        self, token: str, typ: str, invalid: DepositReason, expired: DepositReason
    ) -> dict[str, Any]:
        try:
            header = jws.extract_compact(token.encode("ascii")).headers()
        except JoseError, ValueError, UnicodeError:
            raise Refused(401, invalid) from None
        if header.get("alg") not in SIGNING_ALGORITHMS or header.get("typ") != typ:
            raise Refused(401, invalid)
        key_set = self._keys.key_set(header.get("kid"), invalid)
        try:
            decoded = jwt.decode(token, key_set, algorithms=list(SIGNING_ALGORITHMS))
        except JoseError, ValueError:
            raise Refused(401, invalid) from None
        registry = jwt.JWTClaimsRegistry(
            now=lambda: int(self._now()),
            leeway=LEEWAY_S,
            aud={"essential": True, "value": DEPOSIT_BROKER_AUDIENCE},
            exp={"essential": True},
            iat={"essential": True},
        )
        try:
            registry.validate(decoded.claims)
        except ExpiredTokenError:
            raise Refused(401, expired) from None
        except InvalidClaimError, MissingClaimError, JoseError:
            raise Refused(401, invalid) from None
        return dict(decoded.claims)

    def _open(self, subject: str, invalid: DepositReason) -> str:
        try:
            opened = jwe.decrypt_compact(subject, self._subject_key, registry=_SUBJECT_REGISTRY)
            pseudonym = (opened.plaintext or b"").decode("utf-8")
        except JoseError, ValueError, UnicodeError:
            raise Refused(401, invalid) from None
        if not pseudonym or len(pseudonym) > MAX_PSEUDONYM_CHARS:
            raise Refused(401, invalid)
        return pseudonym


def subject_key(material: str | Mapping[str, Any]) -> ECKey:
    """The deposit broker's private P-256 key, from a JWK (as JSON or a mapping) or a PEM."""
    if isinstance(material, str) and material.lstrip().startswith("{"):
        material = json.loads(material)
    try:
        key = ECKey.import_key(material)  # type: ignore[arg-type]
    except (JoseError, ValueError, TypeError) as exc:
        raise ValueError("not an EC key") from exc
    if key.curve_name != "P-256":
        raise ValueError("not a P-256 key")
    if not key.is_private:
        raise ValueError("not a private key")
    return key
