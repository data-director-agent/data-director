"""The app's web server: the shell's API beside the built shell (docs/specs/app.md).

`GET /api/agents` is what the shell draws its capabilities panel from. `POST /api/runs` runs an
agent through the conductor and answers when the run has ended, with its envelope and the
checks' reports; `GET /api/runs` and `GET /api/runs/{id}` read the run store; `GET /api/examples`
lists example inputs; `GET /api/process-flow` is the Blueprint's entry points and phases
(`dd_sdk.process_flow`), which the shell's phase tracker draws. The run endpoint is a stopgap
until runs stream over AG-UI (#69).
`POST /api/conversations` starts a conversation, in the project it names or else a new one, and
`POST /api/conversations/{id}/turns` sends it one message, which may attach a `dd-inventory` file
and a supporting document's text for the project to keep, answered as a run is, or refused with
`409` unless it follows the latest turn (docs/specs/orchestration.md, docs/specs/app.md);
`GET /api/conversations` and `GET /api/conversations/{id}` read them back as the harness derives
them from the run store (docs/specs/orchestration.md, #130).
`GET /api/projects` lists the projects the person signed in may read, the one created last first
and a page at a time, each with what it holds and the conversations started in it
(docs/specs/projects.md, docs/specs/app.md, docs/specs/storage.md "Listing"); `POST /api/projects`
creates one for the person signed in, with no conversation, named by the optional `title` it is
sent, and answers `201` with its summary as the list shows it (docs/specs/app.md, rule 27).
`DELETE /api/projects/{id}` deletes a project for an owner who sends its name as `{"title": …}`
(its identifier while it has none), `400` otherwise; deleting removes nothing, and the summary it
answers with says until when the project may be restored. `POST /api/projects/{id}/restore`
restores it within that period, `409` after it or for a project not deleted, and
`GET /api/projects/deleted` lists the deleted projects the person may still restore, the one
deleted last first (docs/specs/projects.md, invariants 22 to 25).
`GET /api/projects/{id}/documents` reads a project's documents, each version's state and the
rule for when a decision needs a reason; `POST /api/projects/{id}/documents/{document_id}/decisions`
approves or rejects the latest version, or approves an edit of it, for the person signed in, and
answers `409` if that version is no longer the latest or undecided (docs/specs/projects.md);
`POST /api/projects/{id}/documents/{document_id}/answers` records the person's answers to questions
the latest version asks, for the next draft to place as supplied, and answers `409` if that
version is no longer the latest or does not ask them (docs/specs/drafting.md).
`GET /api/projects/{id}/inventory` is the inventory the project holds, as it was added, for the
researcher to read; it answers `404` when there is none.
`POST /api/projects/{id}/inventory` adds `{"inventory": …}` to the project as its latest, for
the person signed in: the researcher's revision of the one it holds, or a new scan
(docs/specs/projects.md). It answers `201` with what the project then holds of it.
`GET /api/projects/{id}/documentation` lists the documents attached to the project, without their
text, and `GET /api/projects/{id}/documentation/{digest}` is one document's text, `404` when the
project holds none with that digest (docs/specs/projects.md).
`GET /api/projects/{id}/repository` is the requirements of the repository the project chose last,
and `404` when none has been; `PUT` on it chooses one by its re3data identifier, which the pinned
re3data export resolves to the repository's name and declared standards, for the person signed in,
and answers with the requirements it resolved to and their warnings (docs/specs/deposit.md).
`GET /api/repositories?q=…` searches the pinned re3data export by name, re3data identifier,
re3data DOI or URL; without `q` it answers with the repositories the deployment suggests (its
overrides, then `suggested.yaml`), so a researcher can choose one on the project's page.
`GET /api/projects/{id}/intake` says whether the project's intake is pending, complete or
dismissed, with its next question and each question asked from the project's entry point and its
current answer; `POST /api/projects/{id}/intake/{question_id}` records the person's answer to one
(`{"answer_values": […]}`), refused with `400` when malformed and `409` when the harness rejects
it, and `POST /api/projects/{id}/intake/dismiss` passes the intake by; both answer with the intake
read anew (docs/specs/app.md, rule 25).
`GET /api/projects/{id}/disclosure` says how each approved document came about and what
generative AI was used, as a statement and as a PROV-O graph (docs/specs/disclosure.md).
`POST /api/projects/{id}/validation` validates the project against the requirements recorded
for the repository chosen last and keeps the report; `POST /api/projects/{id}/package` does the
same and, only if the project is valid, builds the deposit package, answering `409` with the
validation when it is not; `GET /api/projects/{id}/packages/{digest}` is a package the project
log records as built, as a zip (docs/specs/deposit.md).
`POST /a2a` and `GET /.well-known/agent-card.json` are the conductor's A2A routes, which accept a
delegation agent's callback under a live grant and nothing else (docs/specs/orchestration.md, #129).
`GET /api/about` names the build (version and commit), says whether reports can be filed and gives
the operator's privacy notice (`DD_PRIVACY_NOTICE_URL`) if there is one;
`POST /api/feedback` files a problem report or feature request as a GitHub issue
(docs/specs/app.md). `GET /api/sign-in` and `GET /api/sign-in/callback` sign a person in through
the configured OpenID Connect provider, `POST /api/sign-out` ends their session, and
`GET /api/session` says who is signed in, until when, and whether this server signs anyone in
(docs/specs/policy-and-identity.md, `dd_harness.signin`); `POST /api/session` says the same and
keeps the session going. Both also say whether a person may add their own model account.
`POST /api/model-account/ticket` issues the person signed in a single-use enrolment ticket and
names where the browser takes it: the model broker, which alone receives their key
(docs/specs/model-accounts.md, Enrolment).
Every other path serves the shell built from `app/web` (`npm run build` writes `app/web/dist`).
The app stops at start-up, with one line, if a setting is wrong or the shell has not been built.

Every `/api` route that runs or reads anything acts for the person the request's session names,
and answers `401` with an `unauthenticated` problem when there is none. Every
`/api/projects/{id}/…` route also needs the person to have a role in that project
(`dd_harness.project_access`): someone without one is answered `404`, as for a project that does
not exist, and a member asking for an owner's action `403` (docs/specs/projects.md). A deleted
project is answered as missing to anyone but an owner, and a route that would add to it, or start
or continue a conversation in it, answers `409` with a `project-deleted` problem until it is
restored. `/api/about`,
`/api/session` and the sign-in routes are open, so the shell can draw its sign-in page. A server
with no provider configured is a development server: every request acts for the operator.

Serves on http://127.0.0.1:7860 by default; `DD_APP_HOST` and `DD_APP_PORT` change the address,
and `DD_HARNESS_URL` the address the agents call back on, if they reach the app by another.
`DD_APP_MODEL_BROKER_URL` (a path on the app's origin, such as `/broker`) turns on adding one's own
model account, when the harness also mints model grants (`dd_app.model_accounts`).
A GitHub App (`DD_FEEDBACK_GITHUB_APP_ID` and `DD_FEEDBACK_GITHUB_APP_PRIVATE_KEY_FILE`) or a
token (`DD_FEEDBACK_GITHUB_TOKEN`, or `_FILE`) turns problem reports on, into `DD_FEEDBACK_REPO`.
"""

from __future__ import annotations

import logging
import os
import sys
import webbrowser
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import (
    JSONResponse,
    Response,
)
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from dd_app import deposit, documents, feedback
from dd_app.about import about
from dd_app.config import EXAMPLES_DIR, WEB_DIST, settings_from_env
from dd_app.github_auth import TokenSource
from dd_app.governance import (
    Governance,
)
from dd_app.model_accounts import broker_path
from dd_app.privacy import notice_url
from dd_app.project_service import ProjectService
from dd_app.routes import conversations, materials, meta, progress, projects, runs, session
from dd_app.routes.common import Deps, Feedback
from dd_harness.deposit import PackageRefusedError, build_package, check
from dd_harness.disclosure import disclose
from dd_harness.identity import IdentityError, Unauthenticated
from dd_harness.model_grants import jwks_routes
from dd_harness.policy import PolicyError
from dd_harness.project_access import Action, allowed
from dd_harness.projects import (
    ChangeRefusedError,
    ProjectError,
    Refusal,
    UnknownProjectError,
)
from dd_harness.registry import RegistryError
from dd_harness.requirements import RequirementsError
from dd_harness.server import LOOPBACK
from dd_harness.sessions import SESSION_COOKIE, cookie
from dd_harness.settings import SettingsError
from dd_harness.signin import SignIn, SignInSettings
from dd_harness.sources import SourceConfigError
from dd_harness.transport.a2a import a2a_routes
from dd_harness.transport.paging import PagingError, page_params, page_response
from dd_sdk import security_log
from dd_sdk.contract.models import Principal
from dd_sdk.contract.problem import PROBLEM_BASE, unauthenticated
from dd_sdk.credentials import ConfigError
from dd_sdk.security_log import SecurityEvent, emit

log = logging.getLogger(__name__)

# The service a security event names (docs/specs/security.md, Security events).
SERVICE = "app"
Handler = Callable[[Request, Principal], Awaitable[Response]]

# Where people reach the app, which the provider sends them back to (dd_harness.signin).
PUBLIC_URL_VARIABLE = "DD_APP_PUBLIC_URL"

DECISION_REFUSED = "Data Director could not record this decision"
ANSWERS_REFUSED = "Data Director could not record these answers"
TITLE_REFUSED = "Data Director could not rename this project"
DELETE_REFUSED = "Data Director could not delete this project"
RESTORE_REFUSED = "Data Director could not restore this project"
CREATE_REFUSED = "Data Director could not create this project"
REPOSITORY_REFUSED = "Data Director could not record this repository"
# The most repositories one search of the pinned re3data export answers with.
REPOSITORY_SEARCH_LIMIT = 20
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7860
UNTRUSTED_WARNING = (
    "data-director: warning: serving on {host}. A delegation grant is a bearer token and callers "
    "are not authenticated; expose the app to the host or a private network only "
    "(docs/specs/agents.md).\n"
)


class ShellNotBuiltError(FileNotFoundError):
    """`app/web/dist` holds no built shell."""


def build_app(  # noqa: C901, PLR0913, PLR0915
    governance: Governance,
    web_dist: Path = WEB_DIST,
    examples_dir: Path = EXAMPLES_DIR,
    *,
    feedback_source: TokenSource | None = None,
    feedback_repo: str = feedback.DEFAULT_REPO,
    feedback_client: httpx.AsyncClient | None = None,
    build: Mapping[str, str | None] | None = None,
    sign_in: SignIn | None = None,
    orcid_transport: httpx.BaseTransport | None = None,
    model_broker_path: str | None = None,
    privacy_notice_url: str | None = None,
) -> Starlette:
    """The server. `web_dist` must hold a built shell (its `index.html`).

    Problem reports are on when `feedback_source` is given; `feedback_client` and `build` let a test
    stand in for GitHub and for the build's identity. `sign_in` signs people in; its
    authenticator must be `governance.authenticator`. Without it, the server signs nobody in.
    `orcid_transport` lets a test stand in for ORCID's public API (`dd_harness.orcid`).
    `model_broker_path` is where the browser reaches the model broker (`dd_app.model_accounts`);
    with it and a harness that mints model grants, a person may add their own model account.
    `privacy_notice_url` is the operator's privacy notice (`dd_app.privacy`), which `GET /api/about`
    gives so that the footer can link to it; without it the footer has no link.
    """
    if not (web_dist / "index.html").is_file():
        raise ShellNotBuiltError(
            f"the shell is not built ({web_dist / 'index.html'} is missing); "
            "run `npm ci && npm run build` in app/web"
        )
    if sign_in is not None and governance.authenticator is not sign_in.authenticator:
        raise IdentityError("the app signs people in, so it must act for whom it signed in")

    minter = governance.conductor.model_grants
    # A person may add their own model account only where the profile lets one pay
    # (docs/specs/model-accounts.md, The profile) and the deployment can carry that to the broker.
    model_accounts = (
        minter is not None
        and model_broker_path is not None
        and governance.conductor.profile.model_accounts.own != "off"
    )
    # The providers, and the base URL origins, a person's own account may use, so the Profile page
    # offers only those. Origins are the profile's, not secrets; the broker checks them again.
    model_account_providers = (
        [
            {"provider": p.provider, "base_urls": [u.origin for u in p.base_urls]}
            for p in governance.conductor.profile.model_accounts.providers
        ]
        if model_accounts
        else []
    )
    deps = Deps(
        governance=governance,
        projects=ProjectService(governance),
        web_dist=web_dist,
        examples_dir=examples_dir,
        identity=dict(build) if build is not None else about(),
        feedback=Feedback(feedback_source, feedback_repo, feedback_client),
        sign_in=sign_in,
        orcid_transport=orcid_transport,
        model_broker_path=model_broker_path,
        model_accounts=model_accounts,
        model_account_providers=model_account_providers,
        privacy_notice_url=privacy_notice_url,
    )

    def signed_in(handler: Handler) -> Callable[[Request], Awaitable[Response]]:
        """`handler`, given the principal the request acts for; a request with none is refused
        with `401` (docs/specs/policy-and-identity.md), and never given a default."""

        async def endpoint(request: Request) -> Response:
            if (refused := _requires_json(request)) is not None:
                return refused
            try:
                principal = governance.authenticator.principal_for(request.headers)
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
                return _unauthenticated(str(exc))
            return await handler(request, principal)

        return endpoint

    def in_project(action: Action, handler: Handler) -> Callable[[Request], Awaitable[Response]]:
        """`handler`, signed in as `signed_in` makes it, and run only if the person may take
        `action` in the project the path names (`dd_harness.project_access`,
        docs/specs/projects.md, invariant 17). Every `/api/projects/{project_id}/…` route goes
        through here, so no handler can forget the check. Someone with no role in the project is
        answered `404`, as for a project that does not exist, so that a refusal does not reveal
        whether it does; a member asking for an owner's action is answered `403`."""

        async def checked(request: Request, principal: Principal) -> Response:
            project_id = request.path_params["project_id"]
            role = await run_in_threadpool(governance.role, project_id, principal)
            if role is None:
                return _no_project(project_id)
            if not allowed(role, action):
                return _problem(
                    403,
                    "project-action-forbidden",
                    "Not yours to do in this project",
                    f"In project {project_id!r} a {role} may not {action}.",
                )
            # A deleted project takes no new work until it is restored; an owner may still read
            # it and restore it (docs/specs/projects.md, invariant 24).
            if action not in (Action.READ, Action.MANAGE) and await run_in_threadpool(
                governance.is_deleted, project_id
            ):
                return _project_deleted(project_id)
            return await handler(request, principal)

        return signed_in(checked)

    # with 404, as one that does not exist.
    async def list_runs(request: Request, reader: Principal) -> Response:
        try:
            paging = page_params(request)
        except PagingError as exc:
            return _refused(str(exc), "Data Director could not list the runs")
        page = await run_in_threadpool(lambda: governance.runs(reader, **paging))
        return page_response(request, page)

    async def get_documents(request: Request, _: Principal) -> Response:
        project_id = request.path_params["project_id"]
        if governance.projects is None:
            return _no_project(project_id)
        try:
            found = await run_in_threadpool(documents.view, governance.projects, project_id)
        except UnknownProjectError:
            return _no_project(project_id)
        return JSONResponse(found)

    async def get_disclosure(request: Request, _: Principal) -> Response:
        project_id = request.path_params["project_id"]
        store = governance.projects
        if store is None:
            return _no_project(project_id)
        try:
            found = await run_in_threadpool(disclose, store, governance.conductor.store, project_id)
        except UnknownProjectError:
            return _no_project(project_id)
        return JSONResponse({**found.to_document(), "prov": found.prov_jsonld()})

    async def get_repository(request: Request, _: Principal) -> Response:
        project_id = request.path_params["project_id"]
        store = governance.projects
        if store is None:
            return _no_project(project_id)
        try:
            found = await run_in_threadpool(store.requirements, project_id)
        except UnknownProjectError:
            return _no_project(project_id)
        if found is None:
            return _problem(
                404,
                "repository-not-chosen",
                "No repository chosen",
                f"Project {project_id!r} has not chosen one.",
            )
        return JSONResponse(found)

    async def choose_repository(request: Request, person: Principal) -> Response:
        """The researcher's choice of repository, by its re3data identifier alone: its name and
        declared standards come from the pinned re3data export (docs/specs/deposit.md). Whom it
        acts for is whom the authenticator names, never the body. Answers with the requirements
        it resolved to; a change is a new choice, and the last one counts."""
        project_id = request.path_params["project_id"]
        store, requirements = governance.projects, governance.requirements
        if store is None:
            return _no_project(project_id)
        if requirements is None:
            return _problem(
                503,
                "repositories-unavailable",
                REPOSITORY_REFUSED,
                "This server has no repository requirement sets.",
            )
        try:
            body = await request.json()
        except ValueError:
            return _refused("The body is not JSON.", REPOSITORY_REFUSED)
        re3data_id = body.get("re3data_id") if isinstance(body, dict) else None
        if not isinstance(re3data_id, str):
            return _refused(
                "`re3data_id` is the repository's re3data identifier.", REPOSITORY_REFUSED
            )

        def choose() -> dict[str, Any] | None:
            store.choose_repository(
                project_id,
                re3data_id,
                registry=governance.conductor.sources,
                requirements=requirements,
                acted_for=person,
                caused_by=f"PUT {request.url.path}",
            )
            return store.requirements(project_id)

        try:
            return JSONResponse(await run_in_threadpool(choose), status_code=201)
        except UnknownProjectError:
            return _no_project(project_id)
        except SourceConfigError as exc:
            return _problem(503, "re3data-unavailable", REPOSITORY_REFUSED, str(exc))
        except (ProjectError, RequirementsError) as exc:
            return _refused(str(exc), REPOSITORY_REFUSED)

    async def search_repositories(request: Request, _: Principal) -> Response:
        """Repositories a researcher may choose: those the pinned re3data export holds that `q`
        names, or, without `q`, those the deployment suggests (docs/specs/deposit.md)."""
        query = request.query_params.get("q", "").strip()
        sources, requirements = governance.conductor.sources, governance.requirements

        def search() -> dict[str, Any]:
            if query:
                found = sources.find_repositories(query, limit=REPOSITORY_SEARCH_LIMIT)
            else:
                found = sources.repositories(requirements.suggested if requirements else ())
            return {
                "snapshot_ref": sources.re3data_export_ref(),
                "query": query,
                "suggested": not query,
                "repositories": [m.describe() for m in found],
            }

        try:
            return JSONResponse(await run_in_threadpool(search))
        except SourceConfigError as exc:
            return _problem(503, "re3data-unavailable", "Repositories cannot be searched", str(exc))

    async def validate_project(request: Request, acting_for: Principal) -> Response:
        project_id = request.path_params["project_id"]
        store = governance.projects
        if store is None:
            return _no_project(project_id)
        try:
            validation, digest = await run_in_threadpool(
                lambda: check(
                    store, project_id, acted_for=acting_for, caused_by=f"POST {request.url.path}"
                )
            )
        except UnknownProjectError:
            return _no_project(project_id)
        return JSONResponse(deposit.validation_view(validation, digest), status_code=201)

    async def package_project(request: Request, acting_for: Principal) -> Response:
        project_id = request.path_params["project_id"]
        store = governance.projects
        if store is None:
            return _no_project(project_id)
        try:
            built = await run_in_threadpool(
                lambda: build_package(
                    store,
                    governance.conductor.store,
                    project_id,
                    acted_for=acting_for,
                    caused_by=f"POST {request.url.path}",
                )
            )
        except UnknownProjectError:
            return _no_project(project_id)
        except PackageRefusedError as exc:
            digest = await run_in_threadpool(deposit.last_report_digest, store, project_id)
            return _problem(
                409,
                "package-refused",
                "No package was built",
                str(exc),
                validation=deposit.validation_view(exc.validation, digest),
            )
        digest = await run_in_threadpool(deposit.last_report_digest, store, project_id)
        return JSONResponse(
            {
                **deposit.validation_view(built.validation, digest),
                "package": {
                    "digest": built.digest,
                    "size": len(built.content),
                    "href": f"{request.url.path.removesuffix('/package')}/packages/{built.digest}",
                },
            },
            status_code=201,
        )

    async def get_package(request: Request, _: Principal) -> Response:
        project_id = request.path_params["project_id"]
        digest = request.path_params["digest"]
        store = governance.projects
        if store is None:
            return _no_project(project_id)
        content = None
        if deposit.DIGEST.fullmatch(digest):
            try:
                content = await run_in_threadpool(store.package, project_id, digest)
            except UnknownProjectError:
                return _no_project(project_id)
        if content is None:
            return _problem(
                404,
                "package-not-found",
                "No such package",
                f"Project {project_id!r} has built no package {digest!r}.",
            )
        return Response(
            content,
            media_type="application/zip",
            headers={
                "content-disposition": f'attachment; filename="deposit-package-{digest[:12]}.zip"'
            },
        )

    async def decide(request: Request, decider: Principal) -> Response:
        # The decider is whom the authenticator names, never the body (docs/specs/projects.md).
        project_id = request.path_params["project_id"]
        store = governance.projects
        if store is None:
            return _no_project(project_id)
        try:
            body = await request.json()
        except ValueError:
            return _refused("The body is not JSON.", DECISION_REFUSED)
        try:
            decision = documents.parse_decision(request.path_params["document_id"], body)
        except documents.DecisionRequestError as exc:
            return _refused(str(exc), DECISION_REFUSED)
        try:
            decided = await run_in_threadpool(
                lambda: store.decide(
                    project_id, decision, acted_for=decider, caused_by=f"POST {request.url.path}"
                )
            )
        except UnknownProjectError:
            return _no_project(project_id)
        except ChangeRefusedError as exc:
            if exc.refusal is Refusal.NO_DOCUMENT:
                return _problem(404, exc.refusal.value, "No such document", exc.detail)
            return _problem(409, exc.refusal.value, "The document has moved on", exc.detail)
        except ProjectError as exc:
            return _refused(str(exc), DECISION_REFUSED)
        found = await run_in_threadpool(documents.view, store, project_id)
        return JSONResponse({**found, "decided": decided.model_dump()}, status_code=201)

    async def answer(request: Request, answerer: Principal) -> Response:
        # Who answered is whom the authenticator names, never the body (docs/specs/drafting.md).
        project_id = request.path_params["project_id"]
        document_id = request.path_params["document_id"]
        store = governance.projects
        if store is None:
            return _no_project(project_id)
        try:
            body = await request.json()
        except ValueError:
            return _refused("The body is not JSON.", ANSWERS_REFUSED)
        try:
            version, answers = documents.parse_answers(document_id, body)
        except documents.DecisionRequestError as exc:
            return _refused(str(exc), ANSWERS_REFUSED)
        try:
            answered = await run_in_threadpool(
                lambda: store.answer(
                    project_id,
                    document_id,
                    version,
                    answers,
                    acted_for=answerer,
                    caused_by=f"POST {request.url.path}",
                )
            )
        except UnknownProjectError:
            return _no_project(project_id)
        except ChangeRefusedError as exc:
            if exc.refusal is Refusal.NO_DOCUMENT:
                return _problem(404, exc.refusal.value, "No such document", exc.detail)
            return _problem(409, exc.refusal.value, "The document has moved on", exc.detail)
        except ProjectError as exc:
            return _refused(str(exc), ANSWERS_REFUSED)
        found = await run_in_threadpool(documents.view, store, project_id)
        return JSONResponse({**found, "answered": answered.model_dump()}, status_code=201)

    callback = governance.conductor.harness_url
    # No authenticator: delegation callbacks only, so the app is no other way in
    # (docs/specs/orchestration.md).
    delegation = a2a_routes(governance.conductor, None, callback)[1] if callback else []
    return Starlette(
        routes=[
            # ROUTE MODULES
            *session.routes(deps),
            *meta.routes(deps),
            *progress.routes(deps),
            *materials.routes(deps),
            *projects.routes(deps),
            *conversations.routes(deps),
            *runs.routes(deps),
            Route(
                "/api/projects/{project_id}/documents",
                in_project(Action.READ, get_documents),
                methods=["GET"],
            ),
            Route(
                "/api/projects/{project_id}/disclosure",
                in_project(Action.READ, get_disclosure),
                methods=["GET"],
            ),
            Route(
                "/api/projects/{project_id}/repository",
                in_project(Action.READ, get_repository),
                methods=["GET"],
            ),
            Route(
                "/api/projects/{project_id}/repository",
                in_project(Action.CONTRIBUTE, choose_repository),
                methods=["PUT"],
            ),
            # Before the route below, which would read `dismiss` as a question.
            Route(
                "/api/projects/{project_id}/validation",
                in_project(Action.CONTRIBUTE, validate_project),
                methods=["POST"],
            ),
            Route(
                "/api/projects/{project_id}/package",
                in_project(Action.CONTRIBUTE, package_project),
                methods=["POST"],
            ),
            Route(
                "/api/projects/{project_id}/packages/{digest}",
                in_project(Action.READ, get_package),
                methods=["GET"],
            ),
            Route(
                "/api/projects/{project_id}/documents/{document_id}/decisions",
                in_project(Action.DECIDE, decide),
                methods=["POST"],
            ),
            Route(
                "/api/projects/{project_id}/documents/{document_id}/answers",
                in_project(Action.CONTRIBUTE, answer),
                methods=["POST"],
            ),
            Route("/api/repositories", signed_in(search_repositories), methods=["GET"]),
            *delegation,
            # The harness's public keys for model grants, when it mints them
            # (docs/specs/model-accounts.md).
            *jwks_routes(governance.conductor.model_grants),
            *meta.shell_routes(deps),
            Mount("/", StaticFiles(directory=web_dist, html=True)),
        ]
    )


_CHANGES_STATE = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _requires_json(request: Request) -> Response | None:
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
    return _problem(
        415,
        "unsupported-media-type",
        "The request must be JSON",
        "A request that changes state must declare Content-Type: application/json.",
    )


def _problem(status: int, slug: str, title: str, detail: str, **extra: Any) -> Response:
    """An RFC 9457 problem; `extra` are its extension members."""
    return JSONResponse(
        {"type": PROBLEM_BASE + slug, "title": title, "status": status, "detail": detail, **extra},
        status_code=status,
        media_type="application/problem+json",
    )


def _no_conversation(conversation_id: str) -> Response:
    return _problem(
        404,
        "conversation-not-found",
        "No such conversation",
        f"No conversation {conversation_id!r}.",
    )


def _no_project(project_id: str) -> Response:
    return _problem(404, "project-not-found", "No such project", f"No project {project_id!r}.")


def _project_deleted(project_id: str) -> Response:
    return _problem(
        409,
        "project-deleted",
        "This project is deleted",
        f"Project {project_id!r} is deleted; an owner may restore it.",
    )


def _refused(detail: str, title: str = "Data Director could not start this run") -> Response:
    return _problem(400, "request-refused", title, detail)


def _unauthenticated(detail: str) -> Response:
    found = unauthenticated(detail)
    return _problem(401, found.type.removeprefix(PROBLEM_BASE), found.title or "", detail)


def main() -> int:
    """The `data-director` console script."""
    host = os.environ.get("DD_APP_HOST", DEFAULT_HOST)
    port = int(os.environ.get("DD_APP_PORT", DEFAULT_PORT))
    base_url = f"http://{host}:{port}"
    try:
        settings = settings_from_env()
        sign_in_settings = SignInSettings.from_env(
            os.environ, settings, base_url, public_url_variable=PUBLIC_URL_VARIABLE
        )
        sign_in = SignIn(sign_in_settings) if sign_in_settings is not None else None
        governance = Governance.create(
            settings, base_url, sign_in.authenticator if sign_in is not None else None
        )
    # No principal (docs/specs/policy-and-identity.md), a provider set wrongly or beside an operator
    # (docs/specs/policy-and-identity.md), or a profile, agent list or source list that is unset,
    # missing or malformed (docs/specs/system.md), requirement sets that are malformed or
    # contradict one another (docs/specs/deposit.md), or an agent in this process configured
    # wrongly: nothing may run.
    except (
        IdentityError,
        SettingsError,
        PolicyError,
        RegistryError,
        SourceConfigError,
        RequirementsError,
        ConfigError,
    ) as exc:
        sys.exit(f"data-director: {exc}")
    feedback_repo = os.environ.get(feedback.REPO_VARIABLE) or feedback.DEFAULT_REPO
    try:
        app = build_app(
            governance,
            feedback_source=feedback.source_from_env(os.environ, feedback_repo),
            feedback_repo=feedback_repo,
            sign_in=sign_in,
            model_broker_path=broker_path(os.environ),
            privacy_notice_url=notice_url(os.environ),
        )
        if host not in LOOPBACK and sign_in is None:
            sys.stderr.write(UNTRUSTED_WARNING.format(host=host))
        security_log.configure()
        webbrowser.open(f"{base_url}/")
        uvicorn.run(app, host=host, port=port)
    except (ShellNotBuiltError, ConfigError) as exc:
        sys.exit(f"data-director: {exc}")
    finally:
        governance.conductor.close()
    return 0
