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

from dd_broker.reasons import Reason, Refused
from dd_broker.store import Store
from dd_sdk.model_grant import (
    BROKER_AUDIENCE,
    SIGNING_ALGORITHMS,
    SUBJECT_ENCRYPTION,
    SUBJECT_KEY_ALGORITHM,
    TICKET_TYPE,
    EnrolmentTicketClaims,
    ModelGrantClaims,
    ModelGrantError,
)

LEEWAY_S = 30
# The shortest time between two fetches of the harness's keys: a grant naming an unknown key
# triggers a fetch (the harness may have rotated its key), but a run of such grants does not
# become a run of requests.
MIN_REFETCH_S = 60
FETCH_TIMEOUT_S = 10.0
# A pseudonym is a keyed hash; anything much longer is not one.
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
    """The harness's public signing keys, fetched once and again when a grant names a key not
    held, at most once every `MIN_REFETCH_S`."""

    def __init__(
        self, fetch: Callable[[], Any], *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._fetch = fetch
        self._clock = clock
        self._keys: KeySet | None = None
        self._fetched_at = float("-inf")
        self._lock = threading.Lock()

    def key_set(self, kid: str | None, unavailable: Reason = Reason.GRANT_INVALID) -> KeySet:
        with self._lock:
            held = self._keys is not None and any(key.kid == kid for key in self._keys)
            if not held and self._clock() - self._fetched_at >= MIN_REFETCH_S:
                self._fetched_at = self._clock()
                # If the harness cannot be reached or published nonsense, the grant cannot be
                # checked: it is refused below, and a later one tries again.
                with contextlib.suppress(httpx.HTTPError, OSError, ValueError, JoseError):
                    self._keys = KeySet.import_key_set(self._fetch())
            if self._keys is None:
                raise Refused(503, unavailable)
            return self._keys


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
        header = jws.extract_compact(token.encode("ascii")).headers()
    except JoseError, ValueError, UnicodeError:
        raise Refused(401, invalid) from None
    if header.get("alg") not in SIGNING_ALGORITHMS or not typ_allowed(header.get("typ")):
        raise Refused(401, invalid)
    key_set = keys.key_set(header.get("kid"), invalid)
    try:
        decoded = jwt.decode(token, key_set, algorithms=list(SIGNING_ALGORITHMS))
    except JoseError, ValueError:
        raise Refused(401, invalid) from None
    registry = jwt.JWTClaimsRegistry(
        now=lambda: int(now()),
        leeway=LEEWAY_S,
        aud={"essential": True, "value": BROKER_AUDIENCE},
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


def open_subject(key: ECKey, subject: str, invalid: Reason) -> str:
    """The pseudonym sealed to the broker in a grant's or a ticket's `dd_subject`."""
    try:
        opened = jwe.decrypt_compact(subject, key, registry=_SUBJECT_REGISTRY)
        pseudonym = (opened.plaintext or b"").decode("utf-8")
    except JoseError, ValueError, UnicodeError:
        raise Refused(401, invalid) from None
    if not pseudonym or len(pseudonym) > MAX_PSEUDONYM_CHARS:
        raise Refused(401, invalid)
    return pseudonym


def subject_key(material: str | Mapping[str, Any]) -> ECKey:
    """The broker's private P-256 key, from a JWK (as JSON or a mapping) or a PEM. Raises
    `ValueError` if it is not a private P-256 key."""
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
