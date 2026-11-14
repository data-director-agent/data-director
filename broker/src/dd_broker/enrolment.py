"""The broker's enrolment interface for the browser (docs/specs/model-accounts.md, Enrolment).

A signed-in person reads, adds, replaces or removes their own model account from the app's Profile
page. The browser sends each request here, with the reverse proxy passing on only
`/broker/enrolment/` of the app's own origin, so the key never passes through the app. Each request
carries a fresh enrolment ticket as `Authorization: Bearer`, which the app issued and the harness
signed; the broker accepts each ticket once (`dd_broker.grants.TicketVerifier`) and knows the
person only by the pseudonym it names.

- `GET /enrolment/account`: the account's label, and the person's token use for the last
  `USAGE_DAYS` days.
- `PUT /enrolment/account` with `{"provider": "anthropic", "key": "…"}`: the broker checks the key
  with one inexpensive call to the provider. Only a key that works is sealed and stored, and the
  answer is its label: the provider and the key's last four characters. A key that fails is not
  stored, and the answer is a reason code the page turns into plain words. The provider is
  `anthropic`, `openai`, `gemini` or `openai-compatible`; only `openai-compatible` takes a
  `base_url`, and requires one, which must be an origin the operator allows
  (`DD_BROKER_ALLOWED_BASE_URLS`) and passes the guard on private addresses (`dd_broker.guard`).
  The key is checked there, so a key is never sent to an endpoint the operator has not allowed.
- `DELETE /enrolment/account`: the sealed record is erased at once. A run already under way reads
  the account on each call, so its next call is made as its grant then allows.

Every answer is `Cache-Control: no-store`. The broker never logs a request body, and never returns
the provider's own text, which might quote the key.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Collection
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from dd_broker import anthropic, chat_completions
from dd_broker.grants import TicketVerifier
from dd_broker.guard import BaseUrlRefused, Resolver, Target, check_base_url, system_resolver
from dd_broker.reasons import Reason, Refused
from dd_broker.store import AccountLabel, Store
from dd_sdk.model_grant import HEADER_REASON

log = logging.getLogger("dd_broker")

ACCOUNT_PATH = "/enrolment/account"
USAGE_DAYS = 30
# A key is a few hundred characters at most; a body much larger than that is not an enrolment.
MAX_BODY_BYTES = 4096
MIN_KEY_CHARS = 8
MAX_KEY_CHARS = 512
MAX_BASE_URL_CHARS = 512
_NO_STORE = {"Cache-Control": "no-store"}


@dataclass(frozen=True)
class Enrolment:
    """What enrolment needs of the broker: its store, its ticket check, and the operator's
    allow-list of base URLs with the guard's resolver."""

    store: Store
    tickets: TicketVerifier
    allowed_base_urls: Collection[str] = ()
    private_base_urls: Collection[str] = ()
    resolve: Resolver = system_resolver


@dataclass(frozen=True)
class _Request:
    provider: str
    key: str
    base_url: str | None


def enrolment_refusal(status: int, reason: Reason) -> JSONResponse:
    return JSONResponse(
        {"reason": reason.value},
        status_code=status,
        headers={HEADER_REASON: reason.value, **_NO_STORE},
    )


def bearer(request: Request) -> str | None:
    scheme, _, value = (request.headers.get("authorization") or "").partition(" ")
    return value.strip() or None if scheme.lower() == "bearer" else None


def _account(label: AccountLabel | None) -> dict[str, Any] | None:
    if label is None:
        return None
    return {
        "provider": label.provider,
        "label": label.label,
        "created": label.created.isoformat(),
    }


async def read_account(store: Store, pseudonym: str) -> JSONResponse:
    since = datetime.now(UTC).date() - timedelta(days=USAGE_DAYS - 1)

    def read() -> tuple[AccountLabel | None, list[Any]]:
        return store.label(pseudonym), store.usage(pseudonym, since=since)

    label, usage = await run_in_threadpool(read)
    return JSONResponse(
        {
            "account": _account(label),
            "usage": [
                {
                    "day": row.day.isoformat(),
                    "payer": row.payer.value,
                    "provider": row.provider,
                    "model": row.model,
                    "input_tokens": row.input_tokens,
                    "output_tokens": row.output_tokens,
                }
                for row in usage
            ],
        },
        headers=_NO_STORE,
    )


def _enrolment(body: bytes) -> _Request:
    """The provider, key and base URL from a PUT body, or `Refused`. Never echoes the body."""
    if len(body) > MAX_BODY_BYTES:
        raise Refused(413, Reason.REQUEST_INVALID)
    try:
        document: Any = json.loads(body)
    except ValueError:
        raise Refused(400, Reason.REQUEST_INVALID) from None
    if not isinstance(document, dict):
        raise Refused(400, Reason.REQUEST_INVALID)
    provider, key = document.get("provider"), document.get("key")
    base_url = document.get("base_url")
    if not isinstance(provider, str) or not isinstance(key, str):
        raise Refused(400, Reason.REQUEST_INVALID)
    if provider != anthropic.PROVIDER and provider not in chat_completions.PROVIDERS:
        raise Refused(400, Reason.ACCOUNT_UNSUPPORTED)
    if provider == chat_completions.COMPATIBLE:
        if not isinstance(base_url, str) or not 0 < len(base_url) <= MAX_BASE_URL_CHARS:
            raise Refused(400, Reason.REQUEST_INVALID)
        base_url = base_url.strip().rstrip("/")
    elif base_url is not None:
        # Every other provider's endpoint is fixed.
        raise Refused(400, Reason.REQUEST_INVALID)
    key = key.strip()
    if not (MIN_KEY_CHARS <= len(key) <= MAX_KEY_CHARS) or not all(
        "!" <= char <= "~" for char in key
    ):
        raise Refused(400, Reason.REQUEST_INVALID)
    return _Request(provider, key, base_url)


def _target(enrolment: Enrolment, wanted: _Request) -> Target:
    """Where the key is checked: the provider's endpoint, or an OpenAI-compatible account's base
    URL once the operator's allow-list and the guard on private addresses pass it."""
    if wanted.provider == anthropic.PROVIDER:
        return Target(url=anthropic.BASE_URL)
    endpoint = chat_completions.PROVIDERS[wanted.provider].base_url
    if endpoint is not None:
        return Target(url=endpoint)
    assert wanted.base_url is not None
    try:
        return check_base_url(
            wanted.base_url,
            enrolment.allowed_base_urls,
            private=enrolment.private_base_urls,
            resolve=enrolment.resolve,
        )
    except BaseUrlRefused:
        raise Refused(422, Reason.BASE_URL_REFUSED) from None


def _label(wanted: _Request) -> str:
    if wanted.provider == anthropic.PROVIDER:
        return anthropic.label(wanted.key)
    provider = chat_completions.PROVIDERS[wanted.provider]
    return chat_completions.label(provider, wanted.key, wanted.base_url)


async def enrol(
    enrolment: Enrolment, client: httpx.AsyncClient, pseudonym: str, body: bytes
) -> Response:
    wanted = _enrolment(body)
    target = await run_in_threadpool(_target, enrolment, wanted)
    check = (
        anthropic.check_key if wanted.provider == anthropic.PROVIDER else chat_completions.check_key
    )
    try:
        status = await check(client, target, wanted.key)
    except httpx.HTTPError:
        raise Refused(502, Reason.PROVIDER_UNREACHABLE) from None
    if status in (401, 403):
        raise Refused(422, Reason.MODEL_ACCOUNT_REJECTED)
    if status == 429:
        raise Refused(429, Reason.MODEL_ACCOUNT_LIMIT)
    if status != 200:
        raise Refused(502, Reason.PROVIDER_ERROR)
    await run_in_threadpool(
        lambda: enrolment.store.put(
            pseudonym,
            wanted.provider,
            wanted.key,
            label=_label(wanted),
            base_url=wanted.base_url,
        )
    )
    log.info("enrolled provider=%s", wanted.provider)
    return await read_account(enrolment.store, pseudonym)


async def remove(store: Store, pseudonym: str) -> Response:
    removed = await run_in_threadpool(store.remove, pseudonym)
    log.info("removed account=%s", "yes" if removed else "none")
    return Response(status_code=204, headers=_NO_STORE)


async def account(enrolment: Enrolment, client: httpx.AsyncClient, request: Request) -> Response:
    """`GET`, `PUT` or `DELETE /enrolment/account`, for the person the ticket names."""
    try:
        # Read the body before the ticket is spent, so that a body too large to read does not
        # cost the person their ticket; it is checked after.
        declared = request.headers.get("content-length", "0")
        if not declared.isdigit() or int(declared) > MAX_BODY_BYTES:
            raise Refused(413, Reason.REQUEST_INVALID)
        body = await request.body() if request.method == "PUT" else b""
        pseudonym = await run_in_threadpool(enrolment.tickets.verify, bearer(request))
        if request.method == "GET":
            return await read_account(enrolment.store, pseudonym)
        if request.method == "PUT":
            return await enrol(enrolment, client, pseudonym, body)
        return await remove(enrolment.store, pseudonym)
    except Refused as refused:
        log.info("enrolment refused reason=%s status=%d", refused.reason.value, refused.status)
        return enrolment_refusal(refused.status, refused.reason)
