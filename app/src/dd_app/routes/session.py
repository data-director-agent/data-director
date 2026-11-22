"""Signing in and out, who is signed in, and a person's model-account enrolment ticket.

`GET /api/sign-in` and `GET /api/sign-in/callback` sign a person in through the configured
OpenID Connect provider, `POST /api/sign-out` ends their session, and `GET /api/session` says who
is signed in, until when, and whether this server signs anyone in
(docs/specs/policy-and-identity.md, `dd_harness.signin`); `POST /api/session` says the same and
keeps the session going. Both also say whether a person may add their own model account.
`POST /api/model-account/ticket` issues the person signed in a single-use enrolment ticket and
names where the browser takes it: the model broker, which alone receives their key
(docs/specs/model-accounts.md, Enrolment).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlencode

from pydantic import MISSING
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from starlette.routing import Route

from dd_app.principals import principal_summary
from dd_app.routes.common import (
    SERVICE,
    Deps,
    ResponseBody,
    bind,
    problem,
    requires_json,
    respond,
    signed_in,
)
from dd_harness.identity import RefusalReason, Unauthenticated
from dd_harness.sessions import PENDING_S, SESSION_COOKIE, SIGN_IN_COOKIE, cookie
from dd_harness.signin import CALLBACK_PATH, NotAdmitted, SignIn
from dd_harness.stewardship import DeploymentRole
from dd_sdk.contract.models import Principal
from dd_sdk.security_log import SecurityEvent, emit

log = logging.getLogger(__name__)

# Why a sign-in came back to `/sign-in` without opening a session, for the shell to say.
SIGN_IN_DECLINED = "declined"
SIGN_IN_FAILED = "failed"

# docs/specs/policy-and-identity.md: the session cookie is opaque, unreadable by script, sent only
# over HTTPS, and `Lax` because the provider sends the person back across sites. A browser treats
# `127.0.0.1` and `localhost` as secure, so a development sign-in over plain HTTP still works.
_SESSION: dict[str, Any] = {"path": "/", "secure": True, "httponly": True, "samesite": "lax"}
_SIGN_IN_COOKIE: dict[str, Any] = {**_SESSION, "path": "/api/sign-in"}


class PrincipalSummary(ResponseBody):
    """What the shell is told about a person (`dd_app.governance.principal_summary`): whom runs
    act for, and who vouched for them."""

    name: str
    assurance: Literal["asserted", "authenticated"]
    vouched_by: str | MISSING = MISSING
    """The issuer that vouched for an authenticated person; absent for an asserted one."""


class RawStewardTeam(ResponseBody):
    """A steward team the person is in, as the profile names it (docs/specs/stewardship.md)."""

    team_id: str
    name: str


class RawSessionPrincipal(PrincipalSummary):
    """The person a session is open for."""

    principal_id: str
    roles: list[Literal["researcher", "steward", "administrator"]]
    """The person's deployment roles, from the profile (docs/specs/stewardship.md, invariant 1).
    Everyone is a researcher. No deployment role makes anyone a member of a project."""
    teams: list[RawStewardTeam]
    """The steward teams the person is in; empty unless they are a steward."""


class RawModelAccountProvider(ResponseBody):
    """A provider a person's own model account may be with."""

    provider: str
    base_urls: list[str]
    """The origins (`https://host[:port]`) the account may name as its base URL."""


class RawSession(ResponseBody):
    """Who is signed in, until when, and whether this server signs anyone in
    (`GET`/`POST /api/session`)."""

    signs_in: bool
    """False on a development server, where every run acts for the operator."""
    issuer: str | None
    """The identity provider people sign in with (its issuer IRI), or null."""
    principal: RawSessionPrincipal | None
    expires_at: str | None
    """When the session ends if nothing more is done in it (ISO 8601), or null."""
    model_accounts: bool
    """Whether a person may add their own model account (docs/specs/model-accounts.md)."""
    model_account_providers: list[RawModelAccountProvider]
    """The providers a person's own account may be with; empty unless `model_accounts`."""
    repository_accounts: bool
    """Whether a person may connect their own repository account, to deposit a draft through
    the repository's API (docs/specs/deposit.md)."""


class RepositoryTicket(ResponseBody):
    """A single-use ticket for the deposit broker, and where the browser takes it to connect,
    read or disconnect the person's own repository account (`POST /api/repository-account/ticket`).
    """

    ticket: str
    deposit_broker_url: str
    expires_at: str


class Ticket(ResponseBody):
    """A single-use enrolment ticket, and where the browser takes it with the person's key
    (`POST /api/model-account/ticket`)."""

    ticket: str
    broker_url: str
    expires_at: str


def routes(deps: Deps) -> list[Route]:
    return [
        Route("/api/session", bind(deps, get_session), methods=["GET", "POST"]),
        Route(
            "/api/model-account/ticket",
            signed_in(deps, model_account_ticket),
            methods=["POST"],
        ),
        Route(
            "/api/repository-account/ticket",
            signed_in(deps, repository_account_ticket),
            methods=["POST"],
        ),
        Route("/api/sign-in", bind(deps, begin_sign_in), methods=["GET"]),
        Route(CALLBACK_PATH, bind(deps, finish_sign_in), methods=["GET"]),
        Route("/api/sign-out", bind(deps, sign_out), methods=["POST"]),
    ]


def _principal(principal: Principal, deps: Deps) -> dict[str, Any]:
    found = deps.governance.conductor.profile.roles_of(principal.principal_id)
    return {
        "principal_id": principal.principal_id,
        **principal_summary(principal),
        "roles": sorted(found.roles, key=list(DeploymentRole).index),
        "teams": [{"team_id": t.team_id, "name": t.name} for t in found.teams],
    }


def _timestamp(seconds: float) -> str:
    return datetime.fromtimestamp(seconds, UTC).isoformat().replace("+00:00", "Z")


async def get_session(request: Request, deps: Deps) -> Response:
    if (refused := requires_json(request)) is not None:
        return refused
    # `GET` says when the session ends and does not keep it going; `POST` keeps it going,
    # which is what the shell's "Stay signed in" sends (WCAG 2.2.1).
    accounts = {
        "model_accounts": deps.model_accounts,
        "model_account_providers": deps.model_account_providers or [],
        "repository_accounts": deps.repository_accounts,
    }
    sign_in = deps.sign_in
    if sign_in is None:
        operator = deps.governance.authenticator.principal_for(None)
        return respond(
            RawSession,
            {
                "signs_in": False,
                "issuer": None,
                "principal": _principal(operator, deps),
                "expires_at": None,
                **accounts,
            },
        )
    session = sign_in.authenticator.session(request.headers, touch=request.method == "POST")
    body: dict[str, Any] = {"signs_in": True, "issuer": sign_in.issuer, **accounts}
    if session is None:
        return respond(RawSession, {**body, "principal": None, "expires_at": None})
    return respond(
        RawSession,
        {
            **body,
            "principal": _principal(session.principal, deps),
            "expires_at": _timestamp(sign_in.store.expires_at(session)),
        },
    )


async def model_account_ticket(request: Request, acting_for: Principal, deps: Deps) -> Response:
    # The ticket names the person only by their pseudonym, sealed to the broker. The key
    # itself goes from the browser to the broker and never comes here.
    minter = deps.governance.conductor.model_grants
    if not deps.model_accounts or minter is None or deps.model_broker_path is None:
        return problem(
            404,
            "model-accounts-unavailable",
            "Own model accounts are not offered here",
            "This deployment does not let people add their own model account.",
        )
    ticket, expires = minter.enrolment_ticket(acting_for=acting_for)
    return respond(
        Ticket,
        {"ticket": ticket, "broker_url": deps.model_broker_path, "expires_at": _timestamp(expires)},
        headers={"Cache-Control": "no-store"},
    )


async def repository_account_ticket(
    request: Request, acting_for: Principal, deps: Deps
) -> Response:
    # The ticket names the person only by their pseudonym, sealed to the deposit broker. Their
    # repository token goes between the browser, the repository and the broker, never here.
    broker = deps.governance.deposit_broker
    if broker is None or deps.deposit_broker_path is None:
        return problem(
            404,
            "repository-accounts-unavailable",
            "Repository accounts are not offered here",
            "This deployment does not deposit through a repository's API.",
        )
    ticket, expires = broker.minter.ticket(acting_for=acting_for)
    return respond(
        RepositoryTicket,
        {
            "ticket": ticket,
            "deposit_broker_url": deps.deposit_broker_path,
            "expires_at": _timestamp(expires),
        },
        headers={"Cache-Control": "no-store"},
    )


async def begin_sign_in(request: Request, deps: Deps) -> Response:
    if deps.sign_in is None:
        return _no_sign_in()
    try:
        url, state = await deps.sign_in.start(request.query_params.get("return_to"))
    except Unauthenticated as exc:
        log.warning("data-director: sign-in could not start: %s", exc)
        emit(SecurityEvent.SIGN_IN_FAILED, outcome="failure", service=SERVICE, reason=exc.reason)
        return _back_to_sign_in(SIGN_IN_FAILED)
    response = RedirectResponse(url, status_code=302)
    response.set_cookie(SIGN_IN_COOKIE, state, max_age=PENDING_S, **_SIGN_IN_COOKIE)
    return response


async def finish_sign_in(request: Request, deps: Deps) -> Response:
    if deps.sign_in is None:
        return _no_sign_in()
    params = request.query_params
    if params.get("error"):
        # The person declined at the provider, or the provider refused the request.
        deps.sign_in.store.take(params.get("state") or "")
        # `%r`: the parameter is the caller's, so it cannot write a line of its own.
        log.warning("data-director: the provider answered %r", params["error"][:64])
        emit(
            SecurityEvent.SIGN_IN_FAILED,
            outcome="failure",
            service=SERVICE,
            reason=RefusalReason.PROVIDER_DECLINED,
        )
        response = _back_to_sign_in(SIGN_IN_DECLINED)
    else:
        response = await _open_session(request, deps.sign_in)
    response.delete_cookie(SIGN_IN_COOKIE, **_SIGN_IN_COOKIE)
    return response


async def _open_session(request: Request, sign_in: SignIn) -> Response:
    """The provider's answer to a sign-in this browser began, turned into a session."""
    params = request.query_params
    try:
        session_id, return_to = await sign_in.finish(
            params.get("code"), params.get("state"), cookie(request.headers, SIGN_IN_COOKIE)
        )
    except Unauthenticated as exc:
        log.warning("data-director: sign-in refused: %s", exc)
        emit(
            SecurityEvent.SIGN_IN_FAILED,
            outcome="failure",
            service=SERVICE,
            # Only a person the provider vouched for is named: anything else is unverified.
            principal=exc.principal.principal_id if isinstance(exc, NotAdmitted) else None,
            reason=exc.reason,
        )
        return _back_to_sign_in(SIGN_IN_FAILED)
    if (opened := sign_in.store.get(session_id, touch=False)) is not None:
        emit(
            SecurityEvent.SIGN_IN_SUCCEEDED,
            outcome="success",
            service=SERVICE,
            principal=opened.principal.principal_id,
        )
    # A session open in this browser before is ended, not carried over.
    if previous := cookie(request.headers, SESSION_COOKIE):
        sign_in.store.delete(previous)
    response = RedirectResponse(return_to, status_code=303)
    response.set_cookie(SESSION_COOKIE, session_id, max_age=sign_in.settings.lifetime_s, **_SESSION)
    return response


async def sign_out(request: Request, deps: Deps) -> Response:
    if (refused := requires_json(request)) is not None:
        return refused
    response = Response(status_code=204)
    if deps.sign_in is not None:
        if session_id := cookie(request.headers, SESSION_COOKIE):
            if (ended := deps.sign_in.store.get(session_id, touch=False)) is not None:
                emit(
                    SecurityEvent.SIGN_OUT,
                    outcome="success",
                    service=SERVICE,
                    principal=ended.principal.principal_id,
                )
            deps.sign_in.store.delete(session_id)
        response.delete_cookie(SESSION_COOKIE, **_SESSION)
    return response


def _no_sign_in() -> Response:
    return problem(
        404,
        "sign-in-unavailable",
        "This server signs nobody in",
        "No identity provider is configured: this is a development server.",
    )


def _back_to_sign_in(reason: str) -> Response:
    return RedirectResponse("/sign-in?" + urlencode({"problem": reason}), status_code=303)
