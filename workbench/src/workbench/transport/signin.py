"""Signing admins in to a deployed workbench (docs/specs/policy-and-identity.md, #549).

A workbench serves no one but the people who build and test agents. With `DD_OIDC_ISSUER` set it
signs people in through the harness's OpenID Connect flow (`dd_harness.signin`) and admits only
the ORCID iDs in `DD_WORKBENCH_ADMINS`: anyone else is refused at the callback, and no session is
opened for them. Every route but the sign-in routes then needs an admin's session, and a run acts
for the admin who started it, recorded `authenticated`.

Without an issuer the workbench is a development server, as before: every run acts for the
operator's principal, recorded `asserted`, and nothing is gated.

The workbench is served on its own port beside the app, and a browser scopes cookies by host and
not by port, so its cookies have names of their own.
"""

from __future__ import annotations

import html
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from dd_harness.identity import Unauthenticated
from dd_harness.sessions import PENDING_S, cookie
from dd_harness.settings import Settings
from dd_harness.signin import CALLBACK_PATH, NotAdmitted, SignIn, SignInSettings
from dd_sdk.contract.models import Principal, to_document
from dd_sdk.contract.problem import problem, unauthenticated
from dd_sdk.credentials import ConfigError

log = logging.getLogger(__name__)

PUBLIC_URL_VARIABLE = "DD_WORKBENCH_PUBLIC_URL"
ADMINS_VARIABLE = "DD_WORKBENCH_ADMINS"
SESSION_COOKIE = "dd_workbench_session"
SIGN_IN_COOKIE = "dd_workbench_sign_in"
SIGN_IN_PATH = "/api/sign-in"
SIGN_OUT_PATH = "/api/sign-out"
SESSION_PATH = "/api/session"
# An ORCID iD: four groups of four, the last character a digit or the checksum `X`.
ORCID_ID = re.compile(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]")
# Paths the gate leaves open: signing in and out, and what a browser asks for unprompted. `/a2a`
# takes delegation callbacks only (`build_app`), each carrying a grant the conductor issued, and
# NGINX closes it and the agent card to callers outside the VM.
OPEN_PATHS = frozenset(
    {
        SIGN_IN_PATH,
        CALLBACK_PATH,
        SIGN_OUT_PATH,
        SESSION_PATH,
        "/favicon.ico",
        "/a2a",
        "/.well-known/agent-card.json",
    }
)

# The session cookie is opaque, unreadable by script, sent only over HTTPS, and `Lax` because the
# provider sends the person back across sites (docs/specs/policy-and-identity.md).
_SESSION: dict[str, Any] = {"path": "/", "secure": True, "httponly": True, "samesite": "lax"}
_SIGN_IN: dict[str, Any] = {**_SESSION, "path": SIGN_IN_PATH}


def admins_from_env(env: Mapping[str, str]) -> frozenset[str]:
    """The ORCID iDs `DD_WORKBENCH_ADMINS` lists, separated by commas or spaces. Each may be bare
    or an iD URL. Raises `ConfigError` for an empty list or an entry that is not an iD: a
    workbench that signs people in must admit someone, and a mistyped iD must not pass silently."""
    value = env.get(ADMINS_VARIABLE, "")
    entries = [e for e in re.split(r"[\s,]+", value) if e]
    if not entries:
        raise ConfigError(
            f"{ADMINS_VARIABLE} unset: a workbench that signs people in admits only the ORCID iDs "
            "it lists"
        )
    admins = set()
    for entry in entries:
        orcid = entry.rstrip("/").rsplit("/", 1)[-1]
        if not ORCID_ID.fullmatch(orcid):
            raise ConfigError(f"{ADMINS_VARIABLE}: {entry!r} is not an ORCID iD")
        admins.add(orcid)
    return frozenset(admins)


@dataclass(frozen=True)
class Admins:
    """Whom the workbench admits: a person the deployment's issuer vouched for, whose iD is
    listed. TODO(#154): an interim list until people have roles."""

    issuer: str
    orcids: frozenset[str]

    def __call__(self, principal: Principal) -> bool:
        prefix = self.issuer.rstrip("/") + "/"
        return (
            principal.vouched_by == self.issuer
            and principal.principal_id.startswith(prefix)
            and principal.principal_id.removeprefix(prefix) in self.orcids
        )


def _problem(status: int, document: Any) -> JSONResponse:
    return JSONResponse(
        to_document(document), status_code=status, media_type="application/problem+json"
    )


def _wants_page(request: Request) -> bool:
    return request.method == "GET" and "text/html" in request.headers.get("accept", "")


def _page(status: int, title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        "<!doctype html><html lang='en-GB'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{html.escape(title)} - Data Director Workbench</title></head>"
        f"<body><main><h1>{html.escape(title)}</h1>{body}</main></body></html>",
        status_code=status,
    )


def _not_an_admin(principal: Principal) -> HTMLResponse:
    who = html.escape(principal.principal_id)
    return _page(
        403,
        "Not an admin",
        f"<p>You signed in as <code>{who}</code>, which is not an admin of this workbench.</p>"
        "<p>Ask the operator to add your ORCID iD, or use the Data Director app.</p>",
    )


class AdminGate:
    """Every request outside `OPEN_PATHS` needs a live session of an admin. A page with no session
    is sent to sign in and back; any other request is answered with a problem document."""

    def __init__(self, app: ASGIApp, sign_in: SignIn) -> None:
        self.app = app
        self.sign_in = sign_in

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in OPEN_PATHS:
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        session = self.sign_in.authenticator.session(request.headers)
        response: Response
        if session is None:
            if _wants_page(request):
                here = request.url.path + (f"?{request.url.query}" if request.url.query else "")
                query = urlencode({"return_to": here})
                response = RedirectResponse(f"{SIGN_IN_PATH}?{query}", status_code=303)
            else:
                response = _problem(401, unauthenticated("not signed in: sign in to the workbench"))
        elif self.sign_in.admit is not None and not self.sign_in.admit(session.principal):
            # Admitted at sign-in, and since taken off the list.
            response = _problem(
                403,
                problem(
                    "forbidden",
                    "Not an admin",
                    f"{session.principal.principal_id} is not an admin of this workbench",
                    403,
                ),
            )
        else:
            await self.app(scope, receive, send)
            return
        await response(scope, receive, send)


def sign_in_routes(sign_in: SignIn) -> list[Route]:
    """The routes that sign an admin in and out, and say who is signed in."""

    async def begin(request: Request) -> Response:
        try:
            url, state = await sign_in.start(request.query_params.get("return_to"))
        except Unauthenticated as exc:
            log.warning("workbench: sign-in could not start: %s", exc)
            return _page(502, "Sign-in unavailable", "<p>The provider could not be reached.</p>")
        response = RedirectResponse(url, status_code=302)
        response.set_cookie(SIGN_IN_COOKIE, state, max_age=PENDING_S, **_SIGN_IN)
        return response

    async def finish(request: Request) -> Response:
        params = request.query_params
        again = f"<p><a href='{SIGN_IN_PATH}'>Sign in again</a></p>"
        response: Response
        if params.get("error"):
            sign_in.store.take(params.get("state") or "")
            log.warning("workbench: the provider answered %r", params["error"][:64])
            response = _page(401, "Not signed in", "<p>The sign-in was declined.</p>" + again)
        else:
            try:
                session_id, return_to = await sign_in.finish(
                    params.get("code"), params.get("state"), cookie(request.headers, SIGN_IN_COOKIE)
                )
            except NotAdmitted as exc:
                log.warning(
                    "workbench: refused %s, who is not an admin", exc.principal.principal_id
                )
                response = _not_an_admin(exc.principal)
            except Unauthenticated as exc:
                log.warning("workbench: sign-in refused: %s", exc)
                response = _page(401, "Not signed in", "<p>The sign-in failed.</p>" + again)
            else:
                if previous := cookie(request.headers, SESSION_COOKIE):
                    sign_in.store.delete(previous)
                response = RedirectResponse(return_to, status_code=303)
                response.set_cookie(
                    SESSION_COOKIE, session_id, max_age=sign_in.settings.lifetime_s, **_SESSION
                )
        response.delete_cookie(SIGN_IN_COOKIE, **_SIGN_IN)
        return response

    async def sign_out(request: Request) -> Response:
        if session_id := cookie(request.headers, SESSION_COOKIE):
            sign_in.store.delete(session_id)
        response = Response(status_code=204)
        response.delete_cookie(SESSION_COOKIE, **_SESSION)
        return response

    async def session(request: Request) -> Response:
        found = sign_in.authenticator.session(request.headers, touch=False)
        principal = found.principal if found is not None else None
        return JSONResponse(
            {
                "signs_in": True,
                "principal": (
                    {"principal_id": principal.principal_id, "name": principal.name}
                    if principal is not None
                    else None
                ),
            }
        )

    return [
        Route(SIGN_IN_PATH, begin, methods=["GET"]),
        Route(CALLBACK_PATH, finish, methods=["GET"]),
        Route(SIGN_OUT_PATH, sign_out, methods=["POST"]),
        Route(SESSION_PATH, session, methods=["GET"]),
    ]


def admin_sign_in(env: Mapping[str, str], settings: Settings, base_url: str) -> SignIn | None:
    """The sign-in the environment configures, admitting only its admins, or None for a
    development server. Raises `IdentityError` or `ConfigError` for a configuration that cannot be
    served, before anything is."""
    configured = SignInSettings.from_env(
        env, settings, base_url, public_url_variable=PUBLIC_URL_VARIABLE
    )
    if configured is None:
        return None
    admins = Admins(configured.provider.issuer, admins_from_env(env))
    return SignIn(configured, session_cookie=SESSION_COOKIE, admit=admins)


async def no_sign_in_session(request: Request) -> Response:
    """`GET /api/session` on a development server: nobody signs in."""
    return JSONResponse({"signs_in": False, "principal": None})
