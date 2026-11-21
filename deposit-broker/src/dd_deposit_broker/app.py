"""The deposit broker's HTTP interface (docs/specs/deposit.md, Depositing through an API).

For the browser, through the reverse proxy, which passes on only `/deposit-broker/connect/`:

- `GET /connect/options`: the repository API roots the broker serves, and whether each is
  connected through OAuth or by pasting a token. Public: it names no person.
- `POST /connect/{transport}/start`, a form with `ticket` and `base_url`: starts an OAuth
  authorisation for the person the ticket names, and sends the browser to the repository to sign
  in and approve. The `state` it sends is recorded with the person's pseudonym, a PKCE verifier
  and a nonce the browser is given in a cookie, so the authorisation can be finished only once,
  soon, and only in the browser that started it.
- `GET /connect/{transport}/callback`: finishes it, keeps the tokens sealed, and sends the browser
  back to the app's Settings page.
- `GET`, `PUT` and `DELETE /connect/account?base_url=…`, each with a fresh ticket as
  `Authorization: Bearer`: whether the person has an account there, connect one by pasting a token
  (which is checked with one call before it is kept), or disconnect it, which erases it at once.

For the harness, on loopback only:

- `POST /deposits`, with a deposit grant in `X-DD-Deposit-Grant` and the bytes it names: creates
  the draft as the person the grant names and answers where it is. Never publishes.

Every refusal is a status and a reason code in `X-DD-Reason`. The broker never logs a body, a
token or a repository's own message, and never returns one.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.routing import Route

from dd_deposit_broker import zenodo
from dd_deposit_broker.reasons import Refused
from dd_deposit_broker.settings import DepositBrokerSettings, base_url
from dd_deposit_broker.store import OAUTH, TOKEN, PendingAuthorisation, Store, Tokens
from dd_deposit_broker.tokens import HarnessKeys, Verifier, fetch_file, fetch_url
from dd_sdk.deposit_grant import (
    DEPOSITS_PATH,
    HEADER_GRANT,
    HEADER_REASON,
    DepositGrantError,
    DepositReason,
    DepositRequest,
    sha256,
)

log = logging.getLogger("dd_deposit_broker")

COOKIE = "dd_deposit_oauth"
AUTHORISATION_LIFETIME_S = 600
MAX_FORM_BYTES = 8192
MAX_ACCOUNT_BYTES = 4096
# The package holds no data file; this bounds a deposit request, base64 and all.
MAX_DEPOSIT_BYTES = 64 * 1024 * 1024
MIN_TOKEN_CHARS = 8
MAX_TOKEN_CHARS = 1024
_NO_STORE = {"Cache-Control": "no-store"}


@dataclass
class DepositBroker:
    settings: DepositBrokerSettings
    store: Store
    verifier: Verifier
    # The repositories' transport; tests give a mock.
    transport: httpx.BaseTransport | None = field(default=None, repr=False)

    @classmethod
    def open(
        cls,
        settings: DepositBrokerSettings,
        *,
        transport: httpx.BaseTransport | None = None,
        jwks_transport: httpx.BaseTransport | None = None,
    ) -> DepositBroker:
        store = Store(settings.store, settings.key_encryption_key)
        fetch = (
            fetch_url(settings.harness_jwks_url, transport=jwks_transport)
            if settings.harness_jwks_url
            else fetch_file(settings.harness_jwks_file)  # type: ignore[arg-type]
        )
        verifier = Verifier(HarnessKeys(fetch), settings.subject_key, store)
        return cls(settings, store, verifier, transport)

    def redirect_uri(self, transport: str) -> str:
        return f"{self.settings.public_url}/connect/{transport}/callback"

    def cookie_path(self) -> str:
        return (urlsplit(self.settings.public_url or "").path or "") + "/connect/"


def _refused(refused: Refused) -> Response:
    return Response(
        status_code=refused.status,
        headers={HEADER_REASON: refused.reason.value, **_NO_STORE},
    )


def _guarded(
    handler: Callable[[DepositBroker, Request], Awaitable[Response]], broker: DepositBroker
) -> Callable[[Request], Awaitable[Response]]:
    async def endpoint(request: Request) -> Response:
        try:
            return await handler(broker, request)
        except Refused as refused:
            log.info("refused %s %s: %s", request.method, request.url.path, refused.reason.value)
            return _refused(refused)

    return endpoint


async def _body(request: Request, limit: int) -> bytes:
    declared = request.headers.get("content-length")
    if declared is not None and (not declared.isdigit() or int(declared) > limit):
        raise Refused(413, DepositReason.BODY_INVALID)
    body = await request.body()
    if len(body) > limit:
        raise Refused(413, DepositReason.BODY_INVALID)
    return body


def _bearer(request: Request) -> str | None:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def _served(broker: DepositBroker, value: str | None) -> str:
    """The API root `value` names, if the broker serves it."""
    try:
        root = base_url(value or "")
    except ValueError:
        raise Refused(400, DepositReason.BASE_URL_NOT_ALLOWED) from None
    if root not in broker.settings.allowed:
        raise Refused(400, DepositReason.BASE_URL_NOT_ALLOWED)
    return root


# --- For the browser ----------------------------------------------------------------------------


async def options(broker: DepositBroker, _request: Request) -> Response:
    return JSONResponse(
        {
            "repositories": [
                {
                    "base_url": root,
                    "transport": transport,
                    "oauth": root in broker.settings.oauth_clients,
                }
                for root, transport in broker.settings.allowed.items()
            ]
        },
        headers=_NO_STORE,
    )


def _field(form: dict[str, list[str]], name: str) -> str | None:
    values = form.get(name)
    return values[0] if values else None


async def start(broker: DepositBroker, request: Request) -> Response:
    transport = request.path_params["transport"]
    form = parse_qs((await _body(request, MAX_FORM_BYTES)).decode("utf-8", "replace"))
    pseudonym = await run_in_threadpool(broker.verifier.ticket, _field(form, "ticket"))
    root = _served(broker, _field(form, "base_url"))
    client = broker.settings.oauth_clients.get(root)
    if broker.settings.allowed[root] != transport or client is None:
        raise Refused(400, DepositReason.TRANSPORT_UNKNOWN)
    state, verifier, browser = (secrets.token_urlsafe(32) for _ in range(3))
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    await run_in_threadpool(
        broker.store.begin_authorisation,
        state,
        PendingAuthorisation(pseudonym, root, verifier, browser),
        lifetime_s=AUTHORISATION_LIFETIME_S,
    )
    location = zenodo.authorize_url(
        root,
        client,
        redirect_uri=broker.redirect_uri(transport),
        state=state,
        challenge=challenge.decode("ascii"),
    )
    response = RedirectResponse(location, status_code=303, headers=_NO_STORE)
    response.set_cookie(
        COOKIE,
        browser,
        max_age=AUTHORISATION_LIFETIME_S,
        path=broker.cookie_path(),
        secure=True,
        httponly=True,
        samesite="lax",
    )
    return response


def _back(broker: DepositBroker, outcome: dict[str, str]) -> Response:
    response = RedirectResponse(
        f"{broker.settings.app_url}/settings?{urlencode(outcome)}",
        status_code=303,
        headers=_NO_STORE,
    )
    response.delete_cookie(COOKIE, path=broker.cookie_path(), secure=True, httponly=True)
    return response


async def callback(broker: DepositBroker, request: Request) -> Response:
    transport = request.path_params["transport"]
    state = request.query_params.get("state") or ""
    pending = await run_in_threadpool(broker.store.finish_authorisation, state) if state else None
    browser = request.cookies.get(COOKIE) or ""
    if pending is None or not hmac.compare_digest(pending.browser, browser):
        return _back(broker, {"repository_error": DepositReason.TICKET_INVALID.value})
    if request.query_params.get("error") or not request.query_params.get("code"):
        return _back(broker, {"repository_error": DepositReason.ACCOUNT_REJECTED.value})
    client = broker.settings.oauth_clients.get(pending.base_url)
    if client is None or broker.settings.allowed.get(pending.base_url) != transport:
        return _back(broker, {"repository_error": DepositReason.TRANSPORT_UNKNOWN.value})
    try:
        tokens = await run_in_threadpool(
            lambda: zenodo.exchange(
                pending.base_url,
                client,
                code=request.query_params["code"],
                verifier=pending.verifier,
                redirect_uri=broker.redirect_uri(transport),
                transport=broker.transport,
            )
        )
    except Refused as refused:
        return _back(broker, {"repository_error": refused.reason.value})
    host = urlsplit(pending.base_url).hostname or pending.base_url
    await run_in_threadpool(
        lambda: broker.store.put(
            pending.pseudonym, pending.base_url, tokens, method=OAUTH, label=f"Signed in at {host}"
        )
    )
    return _back(broker, {"repository": "connected"})


async def account(broker: DepositBroker, request: Request) -> Response:
    if request.method == "PUT":
        return await _put_account(broker, request)
    pseudonym = await run_in_threadpool(broker.verifier.ticket, _bearer(request))
    root = _served(broker, request.query_params.get("base_url"))
    if request.method == "DELETE":
        await run_in_threadpool(broker.store.remove, pseudonym, root)
        return Response(status_code=204, headers=_NO_STORE)
    found = await run_in_threadpool(broker.store.account, pseudonym, root)
    shown: dict[str, Any] = {"base_url": root, "connected": found is not None}
    if found is not None:
        shown |= {
            "label": found.label,
            "method": found.method,
            "created": found.created.isoformat(),
        }
    return JSONResponse(shown, headers=_NO_STORE)


async def _put_account(broker: DepositBroker, request: Request) -> Response:
    pseudonym = await run_in_threadpool(broker.verifier.ticket, _bearer(request))
    try:
        body = json.loads(await _body(request, MAX_ACCOUNT_BYTES))
    except ValueError:
        raise Refused(400, DepositReason.BODY_INVALID) from None
    if not isinstance(body, dict) or set(body) != {"base_url", "token"}:
        raise Refused(400, DepositReason.BODY_INVALID)
    root = _served(broker, body["base_url"])
    token = body["token"]
    if (
        not isinstance(token, str)
        or not MIN_TOKEN_CHARS <= len(token.strip()) <= MAX_TOKEN_CHARS
        or any(c.isspace() for c in token.strip())
    ):
        raise Refused(400, DepositReason.BODY_INVALID)
    token = token.strip()
    await run_in_threadpool(lambda: zenodo.check(root, token, transport=broker.transport))
    label = f"Personal token ending {token[-4:]}"
    await run_in_threadpool(
        lambda: broker.store.put(pseudonym, root, Tokens(token), method=TOKEN, label=label)
    )
    return JSONResponse(
        {"base_url": root, "connected": True, "label": label, "method": TOKEN},
        headers=_NO_STORE,
    )


# --- For the harness ----------------------------------------------------------------------------


async def deposits(broker: DepositBroker, request: Request) -> Response:
    verified = await run_in_threadpool(broker.verifier.grant, request.headers.get(HEADER_GRANT))
    claims = verified.claims
    root = _served(broker, claims.base_url)
    if broker.settings.allowed[root] != claims.transport:
        raise Refused(400, DepositReason.TRANSPORT_UNKNOWN)
    try:
        sent = DepositRequest.from_json(json.loads(await _body(request, MAX_DEPOSIT_BYTES)))
    except ValueError, DepositGrantError:
        raise Refused(400, DepositReason.BODY_INVALID) from None
    if not (
        hmac.compare_digest(sha256(sent.package), claims.package_digest)
        and hmac.compare_digest(sha256(sent.item), claims.item_digest)
    ):
        raise Refused(400, DepositReason.DIGEST_MISMATCH)
    found = await run_in_threadpool(broker.store.account, verified.pseudonym, root)
    if found is None:
        raise Refused(403, DepositReason.ACCOUNT_MISSING)
    tokens = found.tokens
    if found.method == OAUTH and zenodo.expiring(tokens):
        client = broker.settings.oauth_clients.get(root)
        if client is None:
            raise Refused(403, DepositReason.ACCOUNT_REJECTED)
        tokens = await run_in_threadpool(
            lambda: zenodo.refresh(root, client, found.tokens, transport=broker.transport)
        )
        await run_in_threadpool(broker.store.replace_tokens, verified.pseudonym, root, tokens)
    access = tokens.access_token
    answer = await run_in_threadpool(
        lambda: zenodo.create_draft(
            root,
            access,
            item=sent.item,
            package=sent.package,
            package_name=sent.package_name,
            transport=broker.transport,
        )
    )
    log.info("draft made for approval %s", claims.approval)
    return JSONResponse(answer.to_json(), status_code=201, headers=_NO_STORE)


async def healthz(_request: Request) -> Response:
    return JSONResponse({"status": "ok"})


def build_app(broker: DepositBroker) -> Starlette:
    return Starlette(
        routes=[
            Route("/connect/options", _guarded(options, broker), methods=["GET"]),
            Route("/connect/{transport}/start", _guarded(start, broker), methods=["POST"]),
            Route("/connect/{transport}/callback", _guarded(callback, broker), methods=["GET"]),
            Route("/connect/account", _guarded(account, broker), methods=["GET", "PUT", "DELETE"]),
            Route(DEPOSITS_PATH, _guarded(deposits, broker), methods=["POST"]),
            Route("/healthz", healthz, methods=["GET"]),
        ]
    )
