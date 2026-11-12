"""The broker's HTTP interface for agents (docs/specs/model-accounts.md).

`POST /anthropic/v1/messages` takes an Anthropic Messages API request from an agent. In order,
the broker:

1. authenticates the agent by its own broker credential (`x-api-key` or `Authorization: Bearer`);
2. verifies the model grant in `X-DD-Model-Grant` for that agent (`dd_broker.grants`);
3. refuses a model the grant does not allow, and a streamed request;
4. chooses who pays, from the grant's account alone:

   | Grant's account | The person has a key | The person has none |
   |---|---|---|
   | `own` | their key | refused, `model-account-missing` |
   | `own-or-deployment` | their key | the deployment's key |
   | `deployment` | the deployment's key | the deployment's key |

5. forwards the call, to the person's provider for their own key, or to the deployment's base URL
   (the LiteLLM gateway when one is configured) for the deployment's;
6. returns the provider's answer unchanged, with `X-DD-Model-Account` (`own` or `deployment`) and
   `X-DD-Model-Provider`, and adds the tokens to the person's counts.

A refusal or a provider error is reduced to a status and a reason code (`dd_broker.reasons`). The
broker never returns or logs a provider's error text, a request body, a key or a grant, and keeps
no prompt and no reply. A rejected or limited own key never falls back to the deployment's key:
that would silently change who pays (invariant 10).

The enrolment interface for the browser is TODO(#807). OpenAI-compatible calls are TODO(#811).
"""

from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import AsyncIterator, Collection, Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from dd_broker import anthropic
from dd_broker.agents import AgentCredentials
from dd_broker.grants import GrantVerifier, HarnessKeys, VerifiedGrant, fetch_file, fetch_url
from dd_broker.guard import BaseUrlRefused, Resolver, Target, check_base_url, system_resolver
from dd_broker.reasons import Reason, Refused
from dd_broker.seal import SealError
from dd_broker.settings import BrokerSettings
from dd_broker.store import Store
from dd_sdk.model_grant import (
    HEADER_ACCOUNT,
    HEADER_GRANT,
    HEADER_PROVIDER,
    HEADER_REASON,
    Account,
    Payer,
)

log = logging.getLogger("dd_broker")

# Anthropic's error types, by status, so an agent's Anthropic client raises its usual exception.
_ERROR_TYPES = {
    400: "invalid_request_error",
    401: "authentication_error",
    403: "permission_error",
    404: "not_found_error",
    429: "rate_limit_error",
    500: "api_error",
    502: "api_error",
    503: "api_error",
    529: "overloaded_error",
}


@dataclass
class Broker:
    store: Store
    verifier: GrantVerifier
    agents: AgentCredentials
    deployment_key: str | None = field(default=None, repr=False)
    deployment_base_url: str | None = None
    allowed_base_urls: Collection[str] = ()
    private_base_urls: Collection[str] = ()
    resolve: Resolver = system_resolver
    transport: httpx.AsyncBaseTransport | None = None

    @classmethod
    def open(cls, settings: BrokerSettings) -> Broker:
        fetch = (
            fetch_url(settings.harness_jwks_url)
            if settings.harness_jwks_url
            else fetch_file(settings.harness_jwks_file)  # type: ignore[arg-type]
        )
        return cls(
            store=Store(settings.store, settings.key_encryption_key),
            verifier=GrantVerifier(HarnessKeys(fetch), settings.subject_key),
            agents=settings.agents,
            deployment_key=settings.deployment_key,
            deployment_base_url=settings.deployment_base_url,
            allowed_base_urls=settings.allowed_base_urls,
            private_base_urls=settings.private_base_urls,
        )


@dataclass(frozen=True)
class _Payment:
    payer: Payer
    provider: str
    target: Target
    key: str = field(repr=False)


def presented_credential(headers: Mapping[str, str]) -> str | None:
    """The agent's broker credential, from `x-api-key` or `Authorization: Bearer`: whichever its
    provider client sends (the Anthropic client sends the second since version 2)."""
    if key := headers.get("x-api-key"):
        return key
    scheme, _, value = (headers.get("authorization") or "").partition(" ")
    return value.strip() or None if scheme.lower() == "bearer" else None


def refusal(status: int, reason: Reason) -> JSONResponse:
    error_type = _ERROR_TYPES.get(status, "api_error")
    return JSONResponse(
        {"type": "error", "error": {"type": error_type, "message": reason.value}},
        status_code=status,
        headers={HEADER_REASON: reason.value},
    )


def _choose(broker: Broker, grant: VerifiedGrant) -> _Payment:
    account = grant.claims.account
    if account in (Account.OWN, Account.OWN_OR_DEPLOYMENT):
        try:
            own = broker.store.account(grant.pseudonym)
        except SealError:
            log.error("a sealed key does not open; check the key-encryption key")
            raise Refused(500, Reason.BROKER_ERROR) from None
        if own is not None:
            if own.provider != anthropic.PROVIDER:
                # A different provider is never substituted (invariant 12). Serving an
                # OpenAI-compatible account is TODO(#811).
                raise Refused(403, Reason.ACCOUNT_UNSUPPORTED)
            if own.base_url:
                try:
                    target = check_base_url(
                        own.base_url,
                        broker.allowed_base_urls,
                        private=broker.private_base_urls,
                        resolve=broker.resolve,
                    )
                except BaseUrlRefused:
                    raise Refused(403, Reason.BASE_URL_REFUSED) from None
            else:
                target = Target(url=anthropic.BASE_URL)
            return _Payment(Payer.OWN, own.provider, target, own.key)
        if account is Account.OWN:
            raise Refused(403, Reason.MODEL_ACCOUNT_MISSING)
    if not broker.deployment_key:
        raise Refused(503, Reason.DEPLOYMENT_ACCOUNT_UNAVAILABLE)
    target = Target(url=broker.deployment_base_url or anthropic.BASE_URL)
    return _Payment(Payer.DEPLOYMENT, anthropic.PROVIDER, target, broker.deployment_key)


def _provider_failure(status: int, payer: Payer) -> Refused:
    if status in (401, 403):
        if payer is Payer.OWN:
            return Refused(403, Reason.MODEL_ACCOUNT_REJECTED)
        log.error("the provider refused the deployment's key (HTTP %d)", status)
        return Refused(502, Reason.PROVIDER_ERROR)
    if status == 429:
        return Refused(
            429, Reason.MODEL_ACCOUNT_LIMIT if payer is Payer.OWN else Reason.PROVIDER_ERROR
        )
    if status == 400:
        return Refused(400, Reason.REQUEST_INVALID)
    if status == 529:
        return Refused(529, Reason.PROVIDER_ERROR)
    return Refused(502, Reason.PROVIDER_ERROR)


async def _messages(broker: Broker, client: httpx.AsyncClient, request: Request) -> Response:
    agent = broker.agents.authenticate(presented_credential(request.headers))
    if agent is None:
        raise Refused(401, Reason.AGENT_UNAUTHENTICATED)
    grant = await run_in_threadpool(
        broker.verifier.verify, request.headers.get(HEADER_GRANT), agent
    )
    try:
        body: Any = json.loads(await request.body())
    except ValueError:
        raise Refused(400, Reason.REQUEST_INVALID) from None
    if not isinstance(body, dict) or not isinstance(body.get("model"), str):
        raise Refused(400, Reason.REQUEST_INVALID)
    if body.get("stream"):
        # No agent streams today; serving a stream is a later change.
        raise Refused(400, Reason.STREAMING_UNSUPPORTED)
    if not grant.allows(body["model"]):
        raise Refused(403, Reason.MODEL_NOT_GRANTED)
    payment = await run_in_threadpool(_choose, broker, grant)
    try:
        answer = await anthropic.send(client, payment.target, payment.key, body, request.headers)
    except httpx.HTTPError:
        raise Refused(502, Reason.PROVIDER_UNREACHABLE) from None
    if answer.status_code != 200:
        raise _provider_failure(answer.status_code, payment.payer)
    try:
        document = answer.json()
    except ValueError:
        raise Refused(502, Reason.PROVIDER_ERROR) from None
    if not isinstance(document, dict):
        raise Refused(502, Reason.PROVIDER_ERROR)
    reported = document.get("model")
    served: str = reported if isinstance(reported, str) else body["model"]
    input_tokens, output_tokens = anthropic.usage(document)
    await run_in_threadpool(
        lambda: broker.store.add_usage(
            grant.pseudonym,
            payer=payment.payer,
            provider=payment.provider,
            model=served,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
    )
    log.info(
        "call agent=%s payer=%s provider=%s model=%s",
        agent,
        payment.payer.value,
        payment.provider,
        served,
    )
    return Response(
        content=answer.content,
        status_code=200,
        media_type="application/json",
        headers={HEADER_ACCOUNT: payment.payer.value, HEADER_PROVIDER: payment.provider},
    )


def build_app(broker: Broker) -> Starlette:
    clients: list[httpx.AsyncClient] = []

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with httpx.AsyncClient(transport=broker.transport) as client:
            clients.append(client)
            yield
            clients.clear()

    async def messages(request: Request) -> Response:
        try:
            return await _messages(broker, clients[0], request)
        except Refused as refused:
            log.info("refused reason=%s status=%d", refused.reason.value, refused.status)
            return refusal(refused.status, refused.reason)

    async def healthz(request: Request) -> Response:
        return JSONResponse({"status": "ok"})

    return Starlette(
        routes=[
            Route("/anthropic/v1/messages", messages, methods=["POST"]),
            Route("/healthz", healthz, methods=["GET"]),
        ],
        lifespan=lifespan,
    )
