"""What every route module shares: the app's dependencies, the guards that say whom a request
acts for, RFC 9457 problems, reading a request body into its model, and answering through a
response model (`dd_app.responses`)."""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response

from dd_app import feedback
from dd_app.config import EXAMPLES_DIR
from dd_app.deployment_view import DeploymentView
from dd_app.folder_scan import FolderRoots
from dd_app.github_auth import TokenSource
from dd_app.governance import Governance
from dd_app.listing_limit import ListingBusyError, ListingLimiter
from dd_app.problems import ProblemDetails as ProblemDetails
from dd_app.problems import no_conversation as no_conversation
from dd_app.problems import problem as problem
from dd_app.problems import refused as refused
from dd_app.project_service import ProjectService
from dd_app.reads import Reads
from dd_app.responses import ResponseBody as ResponseBody
from dd_app.responses import respond as respond
from dd_app.responses import respond_page as respond_page
from dd_harness.identity import Unauthenticated
from dd_harness.project_access import Action, allowed
from dd_harness.projects import ProjectError, UnknownProjectError
from dd_harness.sessions import SESSION_COOKIE, cookie
from dd_harness.signin import SignIn
from dd_sdk.contract.models import Principal
from dd_sdk.contract.problem import PROBLEM_BASE, unauthenticated
from dd_sdk.security_log import SecurityEvent, emit

# The service a security event names (docs/specs/security.md, Security events).
SERVICE = "app"

Endpoint = Callable[[Request], Awaitable[Response]]
Handler = Callable[[Request, Principal, "Deps"], Awaitable[Response]]
OpenHandler = Callable[[Request, "Deps"], Awaitable[Response]]


@dataclass(frozen=True)
class Feedback:
    """Where problem reports go: on when `source` is given (`dd_app.feedback`)."""

    source: TokenSource | None = None
    repo: str = feedback.DEFAULT_REPO
    # A test's stand-in for GitHub; without one each report opens a client of its own.
    client: httpx.AsyncClient | None = None
    limiter: feedback.RateLimiter = field(default_factory=feedback.RateLimiter)


@dataclass(frozen=True)
class Deps:
    """What the handlers need, built once by `dd_app.app.build_app`."""

    governance: Governance
    projects: ProjectService
    reads: Reads
    deployment: DeploymentView
    web_dist: Path
    # The build's identity (version and commit), as `GET /api/about` names it.
    identity: Mapping[str, str | None]
    feedback: Feedback = field(default_factory=Feedback)
    sign_in: SignIn | None = None
    # A test's stand-in for ORCID's public API (`dd_harness.orcid`).
    orcid_transport: httpx.BaseTransport | None = None
    # Where the browser reaches the model broker, when a person may add their own model account.
    model_broker_path: str | None = None
    # The providers a person's own model account may use; None where they may not add one.
    model_account_providers: list[dict[str, Any]] | None = None
    privacy_notice_url: str | None = None
    # The folders on this machine a local install may describe; None where it describes none.
    folder_roots: FolderRoots | None = None
    examples_dir: Path = EXAMPLES_DIR
    # The worker threads the listing routes may hold, so that turns always have some (#1258).
    listing: ListingLimiter = field(default_factory=ListingLimiter)
    started: float = field(default_factory=time.monotonic)

    @property
    def model_accounts(self) -> bool:
        """Whether a person may add their own model account here."""
        return self.model_account_providers is not None


async def listed[T](deps: Deps, work: Callable[[], T], title: str) -> T | Response:
    """What a listing route's `work` returns, run in the listing threads; when too many listings
    are waiting, a `503` with `Retry-After` instead (#1258)."""
    try:
        return await deps.listing.run(work)
    except ListingBusyError as exc:
        busy = problem(
            503,
            "listing-busy",
            title,
            "Too many listings are running; try again shortly.",
        )
        busy.headers["Retry-After"] = str(exc.retry_after)
        return busy


def caused_by(request: Request) -> str:
    """What a project log records as the cause of a change: the request's method and path."""
    return f"{request.method} {request.url.path}"


# Guards. Every route that acts for someone goes through `signed_in`, and every
# `/api/projects/{project_id}/…` route through `in_project`, so no handler can forget the check.


def bind(deps: Deps, handler: OpenHandler) -> Endpoint:
    """An open route: `handler`, given the app's dependencies and no principal."""

    async def endpoint(request: Request) -> Response:
        return await handler(request, deps)

    return endpoint


def signed_in(deps: Deps, handler: Handler) -> Endpoint:
    """`handler`, given the principal the request acts for; a request with none is refused
    with `401` (docs/specs/policy-and-identity.md), and never given a default."""

    async def endpoint(request: Request) -> Response:
        if (refused := requires_json(request)) is not None:
            return refused
        try:
            principal = deps.governance.authenticator.principal_for(request.headers)
        except Unauthenticated as exc:
            # A request with no session cookie is someone not yet signed in, not an event;
            # one whose cookie names no session is (docs/specs/security.md, Security events).
            if cookie(request.headers, SESSION_COOKIE):
                emit(
                    SecurityEvent.CALLER_REFUSED,
                    outcome="failure",
                    service=SERVICE,
                    reason=exc.reason,
                    transport="app",
                )
            return unauthenticated_problem(str(exc))
        return await handler(request, principal, deps)

    return endpoint


def in_project(deps: Deps, action: Action, handler: Handler) -> Endpoint:
    """`handler`, signed in as `signed_in` makes it, and run only if the person may take
    `action` in the project the path names (`dd_harness.project_access`,
    docs/specs/projects.md, invariant 17). Someone with no role in the project is answered `404`,
    as for a project that does not exist, so that a refusal does not reveal whether it does; a
    member asking for an owner's action is answered `403`."""

    async def checked(request: Request, principal: Principal, deps: Deps) -> Response:
        project_id = request.path_params["project_id"]
        role = await run_in_threadpool(deps.governance.role, project_id, principal)
        if role is None:
            return no_project(project_id)
        if not allowed(role, action):
            return problem(
                403,
                "project-action-forbidden",
                "Not yours to do in this project",
                f"In project {project_id!r} a {role} may not {action}.",
            )
        # A deleted project takes no new work until it is restored; an owner may still read
        # it and restore it (docs/specs/projects.md, invariant 24).
        if action not in (Action.READ, Action.MANAGE) and await run_in_threadpool(
            deps.governance.is_deleted, project_id
        ):
            return project_deleted(project_id)
        try:
            return await handler(request, principal, deps)
        except UnknownProjectError:
            # A server that keeps no projects, or one gone since the check above.
            return no_project(project_id)

    return signed_in(deps, checked)


_CHANGES_STATE = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def requires_json(request: Request) -> Response | None:
    """`415` for a request that changes state and does not declare `application/json`, else `None`.

    A cross-origin page cannot send that type without a CORS preflight, which the app never
    answers, whereas a form can send `text/plain` or form-encoded bodies with the session cookie
    from a same-site origin that `SameSite=Lax` does not stop. The type is required whether or not
    there is a body, since a form with no fields posts too (#728).
    """
    if request.method not in _CHANGES_STATE:
        return None
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type == "application/json":
        return None
    return problem(
        415,
        "unsupported-media-type",
        "The request must be JSON",
        "A request that changes state must declare Content-Type: application/json.",
    )


# Request bodies.


class RequestBody(BaseModel):
    """A request body. Strict, so a field of the wrong type is refused rather than coerced.

    A refusal names what was wrong in the words of `refusal` (the body as a whole),
    `field_refusals` (one field) or `extra_refusal` (fields it does not take, as `{extra}`, their
    sorted list, or `{joined}`, their names joined); a validator's own message is used as it is.
    """

    model_config = ConfigDict(strict=True, extra="ignore", frozen=True)

    refusal: ClassVar[str] = "The body must be an object."
    field_refusals: ClassVar[Mapping[str, str]] = {}
    extra_refusal: ClassVar[str] = "Unexpected field(s): {joined}."

    @classmethod
    def refusal_for(cls, exc: ValidationError) -> str:
        errors = exc.errors()
        if extra := sorted(
            str(e["loc"][0])
            for e in errors
            if e["type"] == "extra_forbidden" and len(e["loc"]) == 1
        ):
            return cls.extra_refusal.format(extra=extra, joined=", ".join(extra))
        first = errors[0]
        if first["loc"]:
            return cls.field_refusals.get(str(first["loc"][0]), cls.refusal)
        if first["type"] == "value_error":
            return str(first["ctx"]["error"])
        return cls.refusal


async def parse_body[T: RequestBody](
    request: Request, model: type[T], title: str, *, empty: bool = False
) -> T | Response:
    """The request's body as `model`, or a `400` problem titled `title` saying what was wrong.
    With `empty`, a request with no body is read as `{}`."""
    body = await read_json(request, title, empty=empty)
    if isinstance(body, Response):
        return body
    try:
        return model.model_validate(body)
    except ValidationError as exc:
        return refused(model.refusal_for(exc), title)


async def read_json(request: Request, title: str, *, empty: bool = False) -> Any:
    """The request's body as JSON, or a `400` problem titled `title` (a `Response`) when it is
    not. With `empty`, a request with no body is read as `{}`."""
    raw = await request.body()
    if empty and not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except ValueError:
        return refused("The body is not JSON.", title)


# Problems (RFC 9457).


RUN_REFUSED = "Data Director could not start this run"


def no_project(project_id: str) -> Response:
    return problem(404, "project-not-found", "No such project", f"No project {project_id!r}.")


def project_refused(exc: ProjectError, project_id: str, title: str) -> Response:
    """`404` for a project that is not there, else `400` with what the project refused."""
    if isinstance(exc, UnknownProjectError):
        return no_project(project_id)
    return refused(str(exc), title)


def project_deleted(project_id: str) -> Response:
    return problem(
        409,
        "project-deleted",
        "This project is deleted",
        f"Project {project_id!r} is deleted; an owner may restore it.",
    )


def unauthenticated_problem(detail: str) -> Response:
    found = unauthenticated(detail)
    return problem(401, found.type.removeprefix(PROBLEM_BASE), found.title or "", detail)
