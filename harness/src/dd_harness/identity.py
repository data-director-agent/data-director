"""Who an invocation acts for (Blueprint §5.4, ADR-0018, ADR-0029).

An agent must not operate anonymously: every invocation is made on behalf of a named human, and
the envelope and the crate record who. The caller never says so. The authentication boundary
names the principal, the transport hands it to the conductor, and the conductor records it. A
request that carries `acting_for` is refused by the contract, as one naming a profile is.

Two authenticators sit behind `Authenticator`:

- `OperatorAssertion` is the stub: the deployment's operator names one principal in
  configuration, and every invocation is recorded as acting for them with `assurance: asserted`.
  It serves callers with no request (the CLI, the evaluation) and development servers.
- `BearerTokenAuthenticator` establishes a person from an OpenID Connect ID token the caller
  sends as `Authorization: Bearer`. `verify_id_token` checks the token's signature against the
  issuer's published keys, then its issuer, audience, expiry and, where one was sent, its nonce,
  and records `assurance: authenticated` with the issuer in `vouched_by` (ADR-0029). The app's
  sign-in callback (#152) verifies with the same function.

A caller whose credential is missing or bad is refused with `Unauthenticated`. It is never given
the operator's principal. Nothing here keeps a token once it has been verified.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from joserfc import jws, jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet

from dd_sdk.contract.models import Assurance, Principal, PrincipalKind

# OpenID Connect Core §3.1.3.7: an ID token is signed, and ORCID signs with RS256. No other
# algorithm is accepted, so a token cannot choose a weaker one.
ALGORITHMS = ("RS256",)
# Clock skew allowed on `exp`, `iat` and `nbf`, in seconds.
LEEWAY_S = 60
# The shortest time between two fetches of an issuer's keys. A token naming a key the cache does
# not hold triggers a fetch (the issuer may have rotated its keys), and this stops a run of such
# tokens from turning into a run of requests to the issuer.
MIN_REFETCH_S = 60
FETCH_TIMEOUT_S = 10.0
DISCOVERY = "/.well-known/openid-configuration"


class IdentityError(Exception):
    """No principal is configured, or the one configured is malformed: a configuration error."""


class Unauthenticated(IdentityError):
    """A caller's credential is missing, expired or not to be trusted. The caller is refused
    (`401`, problem type `unauthenticated`), never given a default principal (ADR-0029). The
    message never contains the credential."""


class Authenticator(Protocol):
    def principal_for(self, headers: Mapping[str, str] | None) -> Principal:
        """The human a caller acts for, from the headers of its HTTP request (where a credential
        would travel). `None` is a caller with no request: the CLI, the evaluation."""
        ...


@dataclass(frozen=True)
class OperatorAssertion:
    """The stub: the one principal the operator configured, whoever the caller is."""

    principal: Principal

    def principal_for(self, headers: Mapping[str, str] | None) -> Principal:
        return self.principal


@dataclass(frozen=True)
class OidcProvider:
    """An OpenID Connect provider as the deployment configures it: the issuer, and the client ID
    its tokens are issued to. The code names no provider (ADR-0029)."""

    issuer: str
    client_id: str


def fetch_keys(issuer: str) -> dict[str, Any]:
    """The issuer's published keys (JWKS), found through its discovery document."""
    with httpx.Client(timeout=FETCH_TIMEOUT_S) as client:
        discovery = client.get(issuer.rstrip("/") + DISCOVERY)
        discovery.raise_for_status()
        configuration = discovery.json()
        # OpenID Connect Discovery §4.3: the document's issuer is exactly the one configured.
        if configuration.get("issuer") != issuer:
            raise ValueError(f"discovery names issuer {configuration.get('issuer')!r}")
        keys = client.get(configuration["jwks_uri"])
        keys.raise_for_status()
        document: dict[str, Any] = keys.json()
        return document


class IssuerKeys:
    """An issuer's signing keys, fetched once and again when a token names a key not held."""

    def __init__(self, issuer: str, fetch: Callable[[str], Mapping[str, Any]] = fetch_keys) -> None:
        self.issuer = issuer
        self._fetch = fetch
        self._keys: KeySet | None = None
        self._fetched_at = float("-inf")
        self._lock = threading.Lock()

    def key_set(self, kid: str | None) -> KeySet:
        with self._lock:
            held = self._keys is not None and any(key.kid == kid for key in self._keys)
            stale = time.monotonic() - self._fetched_at >= MIN_REFETCH_S
            if self._keys is None or (not held and stale):
                try:
                    fetched = KeySet.import_key_set(dict(self._fetch(self.issuer)))  # type: ignore[arg-type]
                except (httpx.HTTPError, ValueError, KeyError, JoseError) as exc:
                    raise Unauthenticated(
                        f"the keys of {self.issuer} could not be fetched to verify the token: "
                        f"{type(exc).__name__}"
                    ) from exc
                self._keys, self._fetched_at = fetched, time.monotonic()
            assert self._keys is not None
            return self._keys


def verify_id_token(
    token: str,
    provider: OidcProvider,
    keys: IssuerKeys,
    *,
    nonce: str | None = None,
    now: int | None = None,
) -> Principal:
    """The person an ID token names, once its signature, issuer, audience, times and (if `nonce`
    is given) nonce are verified. Raises `Unauthenticated` otherwise (ADR-0029)."""
    try:
        kid = jws.extract_compact(token.encode("ascii")).headers().get("kid")
        decoded = jwt.decode(token, keys.key_set(kid), algorithms=list(ALGORITHMS))
        claims: dict[str, Any] = decoded.claims
        options: dict[str, Any] = {
            "iss": {"essential": True, "value": provider.issuer},
            "aud": {"essential": True, "value": provider.client_id},
            "sub": {"essential": True},
            "exp": {"essential": True},
            "iat": {"essential": True},
        }
        if nonce is not None:
            options["nonce"] = {"essential": True, "value": nonce}
        jwt.JWTClaimsRegistry(now=now, leeway=LEEWAY_S, **options).validate(claims)
        # OpenID Connect Core §3.1.3.7: with several audiences, the token is for the party
        # named in `azp`.
        audience = claims["aud"]
        several = isinstance(audience, list) and len(audience) > 1
        if several and claims.get("azp") != provider.client_id:
            raise Unauthenticated("the token was issued to another party (azp)")
    except Unauthenticated:
        raise
    except (JoseError, UnicodeError, ValueError) as exc:
        raise Unauthenticated(f"the identity token was refused: {type(exc).__name__}") from exc
    return principal_from_claims(provider.issuer, claims)


def principal_from_claims(issuer: str, claims: Mapping[str, Any]) -> Principal:
    """The principal a verified token names. For ORCID the subject is the bare iD, so the
    principal is the iD URL, `https://orcid.org/<sub>` (ADR-0029). TODO: another provider's
    principal is a `mailto:` IRI or a URN (#179); this form fits an issuer whose subjects are
    paths under it, as ORCID's are."""
    principal_id = f"{issuer.rstrip('/')}/{claims['sub']}"
    given = " ".join(
        str(claims[part]).strip() for part in ("given_name", "family_name") if claims.get(part)
    )
    # A label for a reader, in ADR-0029's order. An iD holder may make their name private.
    name = str(claims.get("name") or "").strip() or given.strip() or principal_id
    try:
        return Principal(
            principal_id=principal_id,
            name=name,
            principal_kind=PrincipalKind.PERSON,
            assurance=Assurance.AUTHENTICATED,
            vouched_by=issuer,
        )
    except ValueError as exc:  # pydantic's ValidationError is a ValueError
        raise Unauthenticated("the identity token names no usable subject") from exc


@dataclass(frozen=True)
class BearerTokenAuthenticator:
    """A caller sends an ID token from the configured issuer as `Authorization: Bearer`, and
    each request is verified. TODO: whether an ID token is the right credential for a program
    that calls the harness, or whether that waits for machine-to-machine authentication (#17)."""

    provider: OidcProvider
    keys: IssuerKeys

    def principal_for(self, headers: Mapping[str, str] | None) -> Principal:
        if headers is None:
            raise Unauthenticated("no request, so no credential: sign in to act")
        value = next((v for k, v in headers.items() if k.lower() == "authorization"), "").strip()
        scheme, _, token = value.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise Unauthenticated("no bearer token: send Authorization: Bearer <ID token>")
        return verify_id_token(token.strip(), self.provider, self.keys)
