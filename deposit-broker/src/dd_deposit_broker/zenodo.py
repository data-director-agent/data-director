"""Zenodo's API, as the deposit broker uses it (https://developers.zenodo.org/).

The API root is a deployment's `base_url`, such as `https://sandbox.zenodo.org/api`; the site, where
a person signs in and authorises, is that root without `/api`. The broker asks only for the
`deposit:write` scope, which lets it create a draft, set its metadata and upload a file, and does
not let it publish: Zenodo itself refuses to publish with such a token, whatever the broker sent
(docs/specs/deposit.md, invariant 14).

A draft is made in two calls: `POST {api}/deposit/depositions` with the item's metadata, then
`PUT {links.bucket}/{name}` with the RO-Crate package. If the upload fails, the half-made draft is
deleted, so a failed deposit leaves nothing behind. Nothing here calls the publish action, and a
test holds it to that.

Every failure is a `Refused` with a reason code; Zenodo's own message is never passed on, since it
may quote what was sent.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from urllib.parse import urlencode

import httpx

from dd_deposit_broker.reasons import Refused
from dd_deposit_broker.store import Tokens
from dd_sdk.deposit_grant import DepositAnswer, DepositReason

NAME = "zenodo"
SCOPE = "deposit:write"
TIMEOUT_S = 30.0
UPLOAD_TIMEOUT_S = 90.0
# A refresh is tried this many seconds before the access token says it expires.
REFRESH_MARGIN_S = 60
USER_AGENT = (
    "DataDirector-DepositBroker/0.1 (+https://github.com/data-director-agent/data-director)"
)


@dataclass(frozen=True)
class OAuthClient:
    """The deployment's OAuth application registered at one Zenodo installation."""

    client_id: str
    client_secret: str = field(repr=False)


def site(base_url: str) -> str:
    return base_url.rstrip("/").removesuffix("/api")


def authorize_url(
    base_url: str, client: OAuthClient, *, redirect_uri: str, state: str, challenge: str
) -> str:
    query = urlencode(
        {
            "response_type": "code",
            "client_id": client.client_id,
            "redirect_uri": redirect_uri,
            "scope": SCOPE,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{site(base_url)}/oauth/authorize?{query}"


def _client(transport: httpx.BaseTransport | None, timeout: float = TIMEOUT_S) -> httpx.Client:
    return httpx.Client(timeout=timeout, transport=transport, headers={"User-Agent": USER_AGENT})


def _token_request(
    base_url: str, form: dict[str, str], transport: httpx.BaseTransport | None, now: float
) -> Tokens:
    try:
        with _client(transport) as client:
            response = client.post(f"{site(base_url)}/oauth/token", data=form)
    except httpx.HTTPError:
        raise Refused(502, DepositReason.REPOSITORY_UNAVAILABLE) from None
    if response.status_code in (400, 401, 403):
        raise Refused(401, DepositReason.ACCOUNT_REJECTED)
    if response.status_code != 200:
        raise Refused(502, DepositReason.REPOSITORY_UNAVAILABLE)
    try:
        body = response.json()
        access = body["access_token"]
    except ValueError, KeyError, TypeError:
        raise Refused(502, DepositReason.REPOSITORY_UNAVAILABLE) from None
    if not isinstance(access, str) or not access:
        raise Refused(502, DepositReason.REPOSITORY_UNAVAILABLE)
    lifetime = body.get("expires_in")
    refresh = body.get("refresh_token")
    return Tokens(
        access,
        refresh if isinstance(refresh, str) and refresh else None,
        int(now + lifetime) if isinstance(lifetime, int) and lifetime > 0 else None,
    )


def exchange(
    base_url: str,
    client: OAuthClient,
    *,
    code: str,
    verifier: str,
    redirect_uri: str,
    transport: httpx.BaseTransport | None = None,
    now: float | None = None,
) -> Tokens:
    """The tokens an authorisation code is exchanged for."""
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client.client_id,
        "client_secret": client.client_secret,
        "code_verifier": verifier,
    }
    return _token_request(base_url, form, transport, time.time() if now is None else now)


def refresh(
    base_url: str,
    client: OAuthClient,
    tokens: Tokens,
    *,
    transport: httpx.BaseTransport | None = None,
    now: float | None = None,
) -> Tokens:
    """New tokens for an account connected through OAuth whose access token has expired."""
    if tokens.refresh_token is None:
        raise Refused(401, DepositReason.ACCOUNT_REJECTED)
    form = {
        "grant_type": "refresh_token",
        "refresh_token": tokens.refresh_token,
        "client_id": client.client_id,
        "client_secret": client.client_secret,
    }
    renewed = _token_request(base_url, form, transport, time.time() if now is None else now)
    if renewed.refresh_token is None:
        renewed = Tokens(renewed.access_token, tokens.refresh_token, renewed.expires_at)
    return renewed


def expiring(tokens: Tokens, now: float | None = None) -> bool:
    current = time.time() if now is None else now
    return tokens.expires_at is not None and tokens.expires_at - REFRESH_MARGIN_S <= current


def check(base_url: str, token: str, *, transport: httpx.BaseTransport | None = None) -> None:
    """That `token` can list the person's depositions, as `deposit:write` allows. Raises
    `Refused` for a token Zenodo does not accept."""
    try:
        with _client(transport) as client:
            response = client.get(
                f"{base_url.rstrip('/')}/deposit/depositions",
                params={"size": "1"},
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.HTTPError:
        raise Refused(502, DepositReason.REPOSITORY_UNAVAILABLE) from None
    if response.status_code in (401, 403):
        raise Refused(401, DepositReason.ACCOUNT_REJECTED)
    if response.status_code != 200:
        raise Refused(502, DepositReason.REPOSITORY_UNAVAILABLE)


def _failure(status: int) -> Refused:
    if status in (401, 403):
        return Refused(403, DepositReason.ACCOUNT_REJECTED)
    if status == 404:
        return Refused(400, DepositReason.TARGET_UNKNOWN)
    if status in (400, 413, 422):
        return Refused(400, DepositReason.ITEM_REJECTED)
    return Refused(502, DepositReason.REPOSITORY_UNAVAILABLE)


def create_draft(
    base_url: str,
    token: str,
    *,
    item: bytes,
    package: bytes,
    package_name: str,
    transport: httpx.BaseTransport | None = None,
) -> DepositAnswer:
    """Create a draft holding the item's metadata and the package, and never publish it."""
    api = base_url.rstrip("/")
    auth = {"Authorization": f"Bearer {token}"}
    try:
        with _client(transport) as client:
            created = client.post(
                f"{api}/deposit/depositions",
                content=item,
                headers={**auth, "Content-Type": "application/json"},
            )
    except httpx.HTTPError:
        raise Refused(502, DepositReason.REPOSITORY_UNAVAILABLE) from None
    if created.status_code != 201:
        raise _failure(created.status_code)
    try:
        body = created.json()
        deposit_id = str(body["id"])
        links = body.get("links") or {}
        bucket = links["bucket"]
    except ValueError, KeyError, TypeError:
        raise Refused(502, DepositReason.REPOSITORY_UNAVAILABLE) from None
    html = links.get("html") or f"{site(base_url)}/deposit/{deposit_id}"
    try:
        with _client(transport, UPLOAD_TIMEOUT_S) as client:
            uploaded = client.put(
                f"{bucket}/{package_name}",
                content=package,
                headers={**auth, "Content-Type": "application/octet-stream"},
            )
        failed = None if uploaded.status_code in (200, 201) else _failure(uploaded.status_code)
    except httpx.HTTPError:
        failed = Refused(502, DepositReason.REPOSITORY_UNAVAILABLE)
    if failed is not None:
        _discard(api, deposit_id, auth, transport)
        raise failed
    doi = body.get("doi") if isinstance(body.get("doi"), str) and body.get("doi") else None
    return DepositAnswer(deposit_id, html, doi)


def _discard(
    api: str, deposit_id: str, auth: dict[str, str], transport: httpx.BaseTransport | None
) -> None:
    """Delete a draft whose upload failed. Best effort: a draft left behind is the person's to
    delete, and the outcome says the deposit failed either way."""
    try:
        with _client(transport) as client:
            client.delete(f"{api}/deposit/depositions/{deposit_id}", headers=auth)
    except httpx.HTTPError:
        pass
