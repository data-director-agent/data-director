"""Checking a token the harness signed, for the services that hold people's own credentials: the
model broker (`dd_broker.grants`) and the deposit broker (`dd_deposit_broker.tokens`).

The harness signs model grants, deposit grants and their enrolment tickets with one key, publishes
the public half as a JWKS (`/.well-known/jwks.json`), and seals the person's pseudonym to the
service's own P-256 key. Each service checks a token here: that its signature is the harness's,
with one of `SIGNING_ALGORITHMS`; that its JOSE `typ` is one the service accepts; that it is
addressed to the service and within its lifetime, allowing `LEEWAY_S` of clock skew; and opens the
pseudonym. What a token's claims must be, and whether it is accepted once, is each service's own
code, because that is governance.

A failure raises `TokenRejected` (with `expired` when only the time was wrong) or `KeysUnavailable`
(the harness's keys could not be read), which each service turns into its own reason codes. No
message quotes a token.

Needs the `brokers` extra (`joserfc`).
"""

from __future__ import annotations

import contextlib
import json
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from joserfc import jwe, jws, jwt
from joserfc.errors import ExpiredTokenError, InvalidClaimError, JoseError, MissingClaimError
from joserfc.jwk import ECKey, KeySet

from dd_sdk.credentials import ConfigError
from dd_sdk.model_grant import SIGNING_ALGORITHMS, SUBJECT_ENCRYPTION, SUBJECT_KEY_ALGORITHM

LEEWAY_S = 30
# The shortest time between two fetches of the harness's keys: a token naming an unknown key
# triggers a fetch (the harness may have rotated its key), but a run of such tokens does not
# become a run of requests.
MIN_REFETCH_S = 60
FETCH_TIMEOUT_S = 10.0
# A pseudonym is a keyed hash; anything much longer is not one.
MAX_PSEUDONYM_CHARS = 256

_SUBJECT_REGISTRY = jwe.JWERegistry(algorithms=[SUBJECT_KEY_ALGORITHM, SUBJECT_ENCRYPTION])


class TokenRejected(Exception):  # noqa: N818 - a refusal, not an error in the service
    """The token is not one the harness signed for this service, now. `expired` when only its
    lifetime is wrong."""

    def __init__(self, *, expired: bool = False) -> None:
        super().__init__("expired" if expired else "invalid")
        self.expired = expired


class KeysUnavailable(Exception):  # noqa: N818 - the harness's keys could not be read
    """The harness's published keys could not be read, so no token can be checked yet."""


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


def jwks_source(
    env: Mapping[str, str], url_name: str, file_name: str
) -> tuple[str | None, Path | None]:
    """Where the harness's keys are read from: exactly one of a URL (`url_name`) and a file
    (`file_name`). Raises `ConfigError` otherwise."""
    url = (env.get(url_name) or "").strip()
    file = (env.get(file_name) or "").strip()
    if bool(url) == bool(file):
        raise ConfigError(f"set one of {url_name} or {file_name}")
    if url and urlsplit(url).scheme not in {"http", "https"}:
        raise ConfigError(f"{url_name} is not an http(s) URL")
    return (url or None), (Path(file) if file else None)


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

    def key_set(self, kid: str | None) -> KeySet:
        """The keys, with `kid` among them if the harness has it. Raises `KeysUnavailable` if no
        keys could ever be read."""
        with self._lock:
            held = self._keys is not None and any(key.kid == kid for key in self._keys)
            if not held and self._clock() - self._fetched_at >= MIN_REFETCH_S:
                self._fetched_at = self._clock()
                # If the harness cannot be reached or published nonsense, the token cannot be
                # checked: it is refused, and a later one tries again.
                with contextlib.suppress(httpx.HTTPError, OSError, ValueError, JoseError):
                    self._keys = KeySet.import_key_set(self._fetch())
            if self._keys is None:
                raise KeysUnavailable
            return self._keys


def decode(
    token: str,
    keys: HarnessKeys,
    now: Callable[[], float],
    *,
    audience: str,
    typ_allowed: Callable[[Any], bool],
) -> dict[str, Any]:
    """The claims of a token the harness signed for `audience`, within its lifetime."""
    try:
        header = jws.extract_compact(token.encode("ascii")).headers()
    except JoseError, ValueError, UnicodeError:
        raise TokenRejected from None
    if header.get("alg") not in SIGNING_ALGORITHMS or not typ_allowed(header.get("typ")):
        raise TokenRejected
    key_set = keys.key_set(header.get("kid"))
    try:
        decoded = jwt.decode(token, key_set, algorithms=list(SIGNING_ALGORITHMS))
    except JoseError, ValueError:
        raise TokenRejected from None
    registry = jwt.JWTClaimsRegistry(
        now=lambda: int(now()),
        leeway=LEEWAY_S,
        aud={"essential": True, "value": audience},
        exp={"essential": True},
        iat={"essential": True},
    )
    try:
        registry.validate(decoded.claims)
    except ExpiredTokenError:
        raise TokenRejected(expired=True) from None
    except InvalidClaimError, MissingClaimError, JoseError:
        raise TokenRejected from None
    return dict(decoded.claims)


def open_subject(key: ECKey, subject: str) -> str:
    """The pseudonym sealed to the service in a token's `dd_subject`."""
    try:
        opened = jwe.decrypt_compact(subject, key, registry=_SUBJECT_REGISTRY)
        pseudonym = (opened.plaintext or b"").decode("utf-8")
    except JoseError, ValueError, UnicodeError:
        raise TokenRejected from None
    if not pseudonym or len(pseudonym) > MAX_PSEUDONYM_CHARS:
        raise TokenRejected
    return pseudonym


def subject_key(material: str | Mapping[str, Any]) -> ECKey:
    """The service's private P-256 key, from a JWK (as JSON or a mapping) or a PEM. Raises
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
