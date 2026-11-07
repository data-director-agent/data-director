"""The app's web server: the shell's API beside the built shell (docs/specs/app.md).

`GET /api/agents` is what the shell draws its capabilities panel from. `POST /api/runs` runs an
agent through the conductor and answers when the run has ended, with its envelope and the
checks' reports; `GET /api/runs` and `GET /api/runs/{id}` read the run store; `GET /api/examples`
lists example inputs; `GET /api/process-flow` is the Blueprint's entry points and phases
(`dd_sdk.process_flow`), which the shell's phase tracker draws. The run endpoint is a stopgap
until runs stream over AG-UI (#68, #69).
`POST /api/conversations` starts a conversation, in the project it names or else a new one, and
`POST /api/conversations/{id}/turns` sends it one message, which may attach a `dd-inventory` file
for the project to keep, answered as a run is, or refused with `409` unless it follows the latest
turn (docs/specs/orchestration.md, docs/specs/app.md); `GET /api/conversations` and
`GET /api/conversations/{id}` read them back as the harness derives them from the run store
(docs/specs/orchestration.md, #130).
`GET /api/projects` lists the projects the person signed in may read, each with what it holds and
the conversations started in it (docs/specs/projects.md, docs/specs/app.md).
`GET /api/projects/{id}/documents` reads a project's documents, each version's state and the
rule for when a decision needs a reason; `POST /api/projects/{id}/documents/{document_id}/decisions`
approves or rejects the latest version, or approves an edit of it, for the person signed in, and
answers `409` if that version is no longer the latest or undecided (docs/specs/projects.md);
`POST /api/projects/{id}/documents/{document_id}/answers` records the person's answers to questions
the latest version asks, for the next draft to place as supplied, and answers `409` if that
version is no longer the latest or does not ask them (docs/specs/drafting.md).
`GET /api/projects/{id}/inventory` is the inventory the project holds, as it was added, for the
researcher to read; it answers `404` when there is none.
`GET /api/projects/{id}/disclosure` says how each approved document came about and what
generative AI was used, as a statement and as a PROV-O graph (docs/specs/disclosure.md).
`POST /api/projects/{id}/validation` validates the project against the requirements recorded
for the repository chosen last and keeps the report; `POST /api/projects/{id}/package` does the
same and, only if the project is valid, builds the deposit package, answering `409` with the
validation when it is not; `GET /api/projects/{id}/packages/{digest}` is a package the project
log records as built, as a zip (docs/specs/deposit.md).
`POST /a2a` and `GET /.well-known/agent-card.json` are the conductor's A2A routes, which accept a
delegation agent's callback under a live grant and nothing else (docs/specs/orchestration.md, #129).
`GET /api/about` names the build (version and commit) and says whether reports can be filed;
`POST /api/feedback` files a problem report or feature request as a GitHub issue
(docs/specs/app.md). `GET /api/sign-in` and `GET /api/sign-in/callback` sign a person in through
the configured OpenID Connect provider, `POST /api/sign-out` ends their session, and
`GET /api/session` says who is signed in, until when, and whether this server signs anyone in
(docs/specs/policy-and-identity.md, `dd_harness.signin`); `POST /api/session` says the same and
keeps the session going.
Every other path serves the shell built from `app/web` (`npm run build` writes `app/web/dist`).
The app stops at start-up, with one line, if a setting is wrong or the shell has not been built.

Every `/api` route that runs or reads anything acts for the person the request's session names,
and answers `401` with an `unauthenticated` problem when there is none. `/api/about`,
`/api/session` and the sign-in routes are open, so the shell can draw its sign-in page. A server
with no provider configured is a development server: every request acts for the operator.

Serves on http://127.0.0.1:7860 by default; `DD_APP_HOST` and `DD_APP_PORT` change the address,
and `DD_HARNESS_URL` the address the agents call back on, if they reach the app by another.
A GitHub App (`DD_FEEDBACK_GITHUB_APP_ID` and `DD_FEEDBACK_GITHUB_APP_PRIVATE_KEY_FILE`) or a
token (`DD_FEEDBACK_GITHUB_TOKEN`, or `_FILE`) turns problem reports on, into `DD_FEEDBACK_REPO`.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import sys
import time
import webbrowser
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from dd_app import deposit, documents, feedback
from dd_app.about import about
from dd_app.config import EXAMPLES_DIR, WEB_DIST, settings_from_env
from dd_app.github_auth import TokenSource
from dd_app.governance import (
    Governance,
    TurnConflictError,
    UnknownConversationError,
    principal_summary,
)
from dd_harness.conductor import UnknownAgent
from dd_harness.deposit import PackageRefusedError, build_package, check
from dd_harness.disclosure import disclose
from dd_harness.identity import IdentityError, Unauthenticated
from dd_harness.policy import PolicyError
from dd_harness.projects import ChangeRefusedError, ProjectError, Refusal, UnknownProjectError
from dd_harness.registry import RegistryError
from dd_harness.server import LOOPBACK
from dd_harness.sessions import PENDING_S, SESSION_COOKIE, SIGN_IN_COOKIE, cookie
from dd_harness.settings import SettingsError
from dd_harness.signin import CALLBACK_PATH, SignIn, SignInSettings
from dd_harness.sources import SourceConfigError
from dd_harness.transport.a2a import a2a_routes
from dd_sdk.contract.models import ChoiceAnswer, Principal
from dd_sdk.contract.problem import PROBLEM_BASE, unauthenticated
from dd_sdk.contract.validate import ContractViolation
from dd_sdk.credentials import ConfigError
from dd_sdk.process_flow import ENTRIES, PHASES

log = logging.getLogger(__name__)
Handler = Callable[[Request, Principal], Awaitable[Response]]

# Where people reach the app, which the provider sends them back to (dd_harness.signin).
PUBLIC_URL_VARIABLE = "DD_APP_PUBLIC_URL"

FEEDBACK_REFUSED = "Data Director could not file this report"
DECISION_REFUSED = "Data Director could not record this decision"
ANSWERS_REFUSED = "Data Director could not record these answers"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7860
UNTRUSTED_WARNING = (
    "data-director: warning: serving on {host}. A delegation grant is a bearer token and callers "
    "are not authenticated; expose the app to the host or a private network only "
    "(docs/specs/agents.md).\n"
)
# Why a sign-in came back to `/sign-in` without opening a session, for the shell to say.
SIGN_IN_DECLINED = "declined"
SIGN_IN_FAILED = "failed"


class ShellNotBuiltError(FileNotFoundError):
    """`app/web/dist` holds no built shell."""


def build_app(
    governance: Governance,
    web_dist: Path = WEB_DIST,
    examples_dir: Path = EXAMPLES_DIR,
    *,
    feedback_source: TokenSource | None = None,
    feedback_repo: str = feedback.DEFAULT_REPO,
    feedback_client: httpx.AsyncClient | None = None,
    build: Mapping[str, str | None] | None = None,
    sign_in: SignIn | None = None,
) -> Starlette:
    """The server. `web_dist` must hold a built shell (its `index.html`).

    Problem reports are on when `feedback_source` is given; `feedback_client` and `build` let a test
    stand in for GitHub and for the build's identity. `sign_in` signs people in; its
    authenticator must be `governance.authenticator`. Without it, the server signs nobody in.
    """
    if not (web_dist / "index.html").is_file():
        raise ShellNotBuiltError(
            f"the shell is not built ({web_dist / 'index.html'} is missing); "
            "run `npm ci && npm run build` in app/web"
        )
    if sign_in is not None and governance.authenticator is not sign_in.authenticator:
        raise IdentityError("the app signs people in, so it must act for whom it signed in")

    def signed_in(handler: Handler) -> Callable[[Request], Awaitable[Response]]:
        """`handler`, given the principal the request acts for; a request with none is refused
        with `401` (docs/specs/policy-and-identity.md), and never given a default."""

        async def endpoint(request: Request) -> Response:
            try:
                principal = governance.authenticator.principal_for(request.headers)
            except Unauthenticated as exc:
                return _unauthenticated(str(exc))
            return await handler(request, principal)

        return endpoint

    async def agents(request: Request, acting_for: Principal) -> Response:
        # Off the event loop: refreshing the registry reads agent cards, which blocks.
        return JSONResponse(await run_in_threadpool(governance.agents, acting_for))

    async def start_run(request: Request, acting_for: Principal) -> Response:
        try:
            body = await request.json()
        except ValueError:
            return _refused("The body is not JSON.")
        if not isinstance(body, dict):
            return _refused("The body must be an object with `agent_id` and `input`.")
        agent_id, input = body.get("agent_id"), body.get("input")
        if not isinstance(agent_id, str) or not isinstance(input, dict):
            return _refused(
                "The body must name `agent_id` (a string) and give `input` (an object)."
            )
        try:
            return JSONResponse(await governance.run(agent_id, input, acting_for))
        # Refused before the run began, so nothing was stored (as `workbench/transport/agui.py`).
        except (ContractViolation, ValueError, UnknownAgent, PolicyError, IdentityError) as exc:
            return _refused(str(exc))

    # TODO(#153): every signed-in person still sees every run and conversation; each is to see
    # only their own.
    async def list_runs(request: Request, _: Principal) -> Response:
        return JSONResponse(governance.runs())

    async def get_run(request: Request, _: Principal) -> Response:
        invocation_id = request.path_params["invocation_id"]
        run = governance.stored_run(invocation_id)
        if run is None:
            return _problem(404, "run-not-found", "No such run", f"No run {invocation_id!r}.")
        return JSONResponse(run)

    async def start_conversation(request: Request, acting_for: Principal) -> Response:
        # No body starts the conversation in a new project; `{"project_id": …}` in that one.
        body: Any = {}
        if (await request.body()).strip():
            try:
                body = await request.json()
            except ValueError:
                return _refused("The body is not JSON.")
        if not isinstance(body, dict):
            return _refused("The body must be an object, with at most `project_id`.")
        if extra := sorted(set(body) - {"project_id"}):
            return _refused(f"A conversation takes only `project_id`, not {extra}.")
        project_id = body.get("project_id")
        if not (project_id is None or isinstance(project_id, str)):
            return _refused("`project_id` must be a string, or null for a new project.")
        try:
            conversation_id = await run_in_threadpool(
                governance.start_conversation, acting_for, project_id
            )
        except UnknownProjectError:
            return _no_project(str(project_id))
        found = governance.conversation(conversation_id) or {}
        return JSONResponse(
            {"conversation_id": conversation_id, "project_id": found.get("project_id")},
            status_code=201,
            headers={"Location": f"/api/conversations/{conversation_id}"},
        )

    async def send_turn(request: Request, acting_for: Principal) -> Response:
        conversation_id = request.path_params["conversation_id"]
        try:
            body = await request.json()
        except ValueError:
            return _refused("The body is not JSON.")
        if not isinstance(body, dict):
            return _refused(
                "The body must be an object with `agent_id`, `message_text` and `follows`."
            )
        if "history" in body:
            return _refused(
                "A turn may not give a history: the server builds it from the stored turns."
            )
        allowed = {"agent_id", "message_text", "follows", "inventory", "choice_answer"}
        if extra := sorted(set(body) - allowed):
            return _refused(
                "A turn takes only `agent_id`, `message_text`, `follows`, `inventory` and "
                f"`choice_answer`, not {extra}."
            )
        agent_id, message_text = body.get("agent_id"), body.get("message_text")
        if not isinstance(agent_id, str) or not isinstance(message_text, str):
            return _refused("The body must name `agent_id` and give `message_text`, as strings.")
        follows = body.get("follows")
        if "follows" not in body or not (follows is None or isinstance(follows, str)):
            return _refused(
                "The body must give `follows`: the `invocation_id` of the turn this one follows, "
                "or null for the first turn."
            )
        inventory = body.get("inventory")
        if not (inventory is None or isinstance(inventory, dict)):
            return _refused("`inventory` must be the object `dd-inventory` wrote.")
        if not message_text.strip() and inventory is None:
            return _refused("The message is empty.")
        answer = None
        if body.get("choice_answer") is not None:
            try:
                answer = ChoiceAnswer.model_validate(body["choice_answer"])
            except ValueError:
                return _refused(
                    "`choice_answer` must name the turn it answers (`answer_to`) and give "
                    "`answer_values`, a list of strings, and optionally `answer_other`."
                )
        if governance.conversation(conversation_id) is None:
            return _no_conversation(conversation_id)
        started = time.monotonic()
        outcome = "answered"
        try:
            return JSONResponse(
                await governance.turn(
                    conversation_id, agent_id, message_text, follows, acting_for, inventory, answer
                )
            )
        except UnknownConversationError:
            outcome = "unknown conversation"
            return _no_conversation(conversation_id)
        except TurnConflictError as exc:
            outcome = "conflict"
            return _problem(409, "turn-conflict", "The conversation has moved on", exc.detail)
        # A `ProjectError` (an inventory the project refuses) is a `ValueError`.
        except (ContractViolation, ValueError, UnknownAgent, PolicyError, IdentityError) as exc:
            outcome = "refused"
            return _refused(str(exc))
        except BaseException:
            outcome = "failed or dropped"
            raise
        finally:
            log.info(
                "data-director: turn %s %s in %.1f s",
                conversation_id,
                outcome,
                time.monotonic() - started,
            )

    async def list_conversations(request: Request, _: Principal) -> Response:
        return JSONResponse(governance.conversations())

    async def get_conversation(request: Request, _: Principal) -> Response:
        conversation_id = request.path_params["conversation_id"]
        found = governance.conversation(conversation_id)
        if found is None:
            return _no_conversation(conversation_id)
        return JSONResponse(found)

    async def list_projects(request: Request, reader: Principal) -> Response:
        return JSONResponse(await run_in_threadpool(governance.projects_for, reader))

    async def get_documents(request: Request, _: Principal) -> Response:
        # TODO(#389): every signed-in person still sees every project; only its members are to.
        project_id = request.path_params["project_id"]
        if governance.projects is None:
            return _no_project(project_id)
        try:
            found = await run_in_threadpool(documents.view, governance.projects, project_id)
        except UnknownProjectError:
            return _no_project(project_id)
        return JSONResponse(found)

    async def get_inventory(request: Request, _: Principal) -> Response:
        # TODO(#389): every signed-in person still sees every project; only its members are to.
        project_id = request.path_params["project_id"]
        store = governance.projects
        if store is None:
            return _no_project(project_id)
        try:
            found = await run_in_threadpool(store.inventory, project_id)
        except UnknownProjectError:
            return _no_project(project_id)
        if found is None:
            return _problem(
                404, "inventory-not-found", "No inventory", f"Project {project_id!r} has none."
            )
        return JSONResponse(found)

    async def get_disclosure(request: Request, _: Principal) -> Response:
        # TODO(#389): every signed-in person still sees every project; only its members are to.
        project_id = request.path_params["project_id"]
        store = governance.projects
        if store is None:
            return _no_project(project_id)
        try:
            found = await run_in_threadpool(disclose, store, governance.conductor.store, project_id)
        except UnknownProjectError:
            return _no_project(project_id)
        return JSONResponse({**found.to_document(), "prov": found.prov_jsonld()})

    async def validate_project(request: Request, acting_for: Principal) -> Response:
        # TODO(#389): every signed-in person still sees every project; only its members are to.
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
        # TODO(#389): every signed-in person still sees every project; only its members are to.
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
        # TODO(#389): every signed-in person still sees every project; only its members are to.
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

    async def list_examples(request: Request, _: Principal) -> Response:
        return JSONResponse(examples(examples_dir))

    async def get_process_flow(request: Request, _: Principal) -> Response:
        return JSONResponse(process_flow())

    identity = dict(build) if build is not None else about()
    started = time.monotonic()

    async def server_status(request: Request) -> Response:
        # Answers a monitor's `GET /server-status?auto` (collectd's apache plugin), in the shape
        # Apache's mod_status uses: `Key: value` lines. Open, and says only that the app is up.
        uptime = int(time.monotonic() - started)
        lines = [
            f"ServerVersion: data-director/{identity.get('app_version')}",
            f"ServerUptimeSeconds: {uptime}",
            f"Uptime: {uptime}",
        ]
        return Response("\n".join(lines) + "\n", media_type="text/plain")

    limiter = feedback.RateLimiter()

    async def get_policy(request: Request, _: Principal) -> Response:
        return JSONResponse(governance.policy())

    async def get_about(request: Request) -> Response:
        deployment = await run_in_threadpool(governance.deployment)
        return JSONResponse(
            {**identity, **deployment, "feedback_enabled": feedback_source is not None}
        )

    async def send_feedback(request: Request, _: Principal) -> Response:
        if feedback_source is None:
            return _problem(
                503,
                "feedback-unavailable",
                "Reports are not switched on",
                "This deployment has no GitHub credential for problem reports.",
            )
        try:
            body = await request.json()
        except ValueError:
            return _refused("The body is not JSON.", FEEDBACK_REFUSED)
        try:
            report = feedback.parse(body)
        except feedback.FeedbackRefusedError as exc:
            return _refused(str(exc), FEEDBACK_REFUSED)
        try:
            limiter.check()
        except feedback.RateLimitedError as exc:
            return _problem(429, "rate-limited", "Too many reports", str(exc))
        context: list[str] = []
        if report.include_context:
            if report.run and (stored := governance.stored_run(report.run)) is not None:
                context += feedback.run_context(stored)
            if report.conversation:
                found = governance.conversation(report.conversation)
                if found is not None:
                    context += feedback.conversation_context(found)
        text = feedback.issue_body(report, identity, context)
        try:
            if feedback_client is not None:
                created = await feedback.create_issue(
                    report, text, repo=feedback_repo, source=feedback_source, client=feedback_client
                )
            else:
                async with httpx.AsyncClient(timeout=feedback.GITHUB_TIMEOUT_SECONDS) as client:
                    created = await feedback.create_issue(
                        report, text, repo=feedback_repo, source=feedback_source, client=client
                    )
        except feedback.FeedbackFailedError as exc:
            log.warning("a problem report was not filed: %s", exc)
            return _problem(502, "feedback-failed", "The report was not filed", str(exc))
        return JSONResponse(created, status_code=201)

    async def get_session(request: Request) -> Response:
        # `GET` says when the session ends and does not keep it going; `POST` keeps it going,
        # which is what the shell's "Stay signed in" sends (WCAG 2.2.1).
        if sign_in is None:
            operator = governance.authenticator.principal_for(None)
            return JSONResponse(
                {
                    "signs_in": False,
                    "issuer": None,
                    "principal": _principal(operator),
                    "expires_at": None,
                }
            )
        session = sign_in.authenticator.session(request.headers, touch=request.method == "POST")
        body: dict[str, Any] = {"signs_in": True, "issuer": sign_in.issuer}
        if session is None:
            return JSONResponse({**body, "principal": None, "expires_at": None})
        expires_at = datetime.fromtimestamp(sign_in.store.expires_at(session), UTC)
        return JSONResponse(
            {
                **body,
                "principal": _principal(session.principal),
                "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
            }
        )

    async def begin_sign_in(request: Request) -> Response:
        if sign_in is None:
            return _no_sign_in()
        try:
            url, state = await sign_in.start(request.query_params.get("return_to"))
        except Unauthenticated as exc:
            log.warning("data-director: sign-in could not start: %s", exc)
            return _back_to_sign_in(SIGN_IN_FAILED)
        response = RedirectResponse(url, status_code=302)
        response.set_cookie(SIGN_IN_COOKIE, state, max_age=PENDING_S, **_SIGN_IN_COOKIE)
        return response

    async def finish_sign_in(request: Request) -> Response:
        if sign_in is None:
            return _no_sign_in()
        params = request.query_params
        response: Response
        if params.get("error"):
            # The person declined at the provider, or the provider refused the request.
            sign_in.store.take(params.get("state") or "")
            # `%r`: the parameter is the caller's, so it cannot write a line of its own.
            log.warning("data-director: the provider answered %r", params["error"][:64])
            response = _back_to_sign_in(SIGN_IN_DECLINED)
        else:
            try:
                session_id, return_to = await sign_in.finish(
                    params.get("code"), params.get("state"), cookie(request.headers, SIGN_IN_COOKIE)
                )
            except Unauthenticated as exc:
                log.warning("data-director: sign-in refused: %s", exc)
                response = _back_to_sign_in(SIGN_IN_FAILED)
            else:
                # A session open in this browser before is ended, not carried over.
                if previous := cookie(request.headers, SESSION_COOKIE):
                    sign_in.store.delete(previous)
                response = RedirectResponse(return_to, status_code=303)
                response.set_cookie(
                    SESSION_COOKIE, session_id, max_age=sign_in.settings.lifetime_s, **_SESSION
                )
        response.delete_cookie(SIGN_IN_COOKIE, **_SIGN_IN_COOKIE)
        return response

    async def sign_out(request: Request) -> Response:
        response = Response(status_code=204)
        if sign_in is not None:
            if session_id := cookie(request.headers, SESSION_COOKIE):
                sign_in.store.delete(session_id)
            response.delete_cookie(SESSION_COOKIE, **_SESSION)
        return response

    async def shell(request: Request) -> Response:
        # A page of the shell's own, so a reload or a link lands on it rather than a 404.
        return FileResponse(web_dist / "index.html")

    callback = governance.conductor.harness_url
    # No authenticator: delegation callbacks only, so the app is no other way in
    # (docs/specs/orchestration.md).
    delegation = a2a_routes(governance.conductor, None, callback)[1] if callback else []
    return Starlette(
        routes=[
            Route("/api/agents", signed_in(agents), methods=["GET"]),
            Route("/api/runs", signed_in(start_run), methods=["POST"]),
            Route("/api/runs", signed_in(list_runs), methods=["GET"]),
            Route("/api/runs/{invocation_id}", signed_in(get_run), methods=["GET"]),
            Route("/api/conversations", signed_in(start_conversation), methods=["POST"]),
            Route("/api/conversations", signed_in(list_conversations), methods=["GET"]),
            Route(
                "/api/conversations/{conversation_id}",
                signed_in(get_conversation),
                methods=["GET"],
            ),
            Route(
                "/api/conversations/{conversation_id}/turns",
                signed_in(send_turn),
                methods=["POST"],
            ),
            Route("/api/projects", signed_in(list_projects), methods=["GET"]),
            Route(
                "/api/projects/{project_id}/documents",
                signed_in(get_documents),
                methods=["GET"],
            ),
            Route(
                "/api/projects/{project_id}/inventory",
                signed_in(get_inventory),
                methods=["GET"],
            ),
            Route(
                "/api/projects/{project_id}/disclosure",
                signed_in(get_disclosure),
                methods=["GET"],
            ),
            Route(
                "/api/projects/{project_id}/validation",
                signed_in(validate_project),
                methods=["POST"],
            ),
            Route(
                "/api/projects/{project_id}/package",
                signed_in(package_project),
                methods=["POST"],
            ),
            Route(
                "/api/projects/{project_id}/packages/{digest}",
                signed_in(get_package),
                methods=["GET"],
            ),
            Route(
                "/api/projects/{project_id}/documents/{document_id}/decisions",
                signed_in(decide),
                methods=["POST"],
            ),
            Route(
                "/api/projects/{project_id}/documents/{document_id}/answers",
                signed_in(answer),
                methods=["POST"],
            ),
            Route("/api/examples", signed_in(list_examples), methods=["GET"]),
            Route("/api/process-flow", signed_in(get_process_flow), methods=["GET"]),
            Route("/api/policy", signed_in(get_policy), methods=["GET"]),
            Route("/api/about", get_about, methods=["GET"]),
            Route("/server-status", server_status, methods=["GET"]),
            Route("/api/feedback", signed_in(send_feedback), methods=["POST"]),
            Route("/api/session", get_session, methods=["GET", "POST"]),
            Route("/api/sign-in", begin_sign_in, methods=["GET"]),
            Route(CALLBACK_PATH, finish_sign_in, methods=["GET"]),
            Route("/api/sign-out", sign_out, methods=["POST"]),
            *delegation,
            Route("/activity", shell, methods=["GET"]),
            Route("/agents", shell, methods=["GET"]),
            Route("/policy", shell, methods=["GET"]),
            Route("/feedback", shell, methods=["GET"]),
            Route("/profile", shell, methods=["GET"]),
            Route("/projects", shell, methods=["GET"]),
            Route("/projects/{project_id}", shell, methods=["GET"]),
            Route("/sign-in", shell, methods=["GET"]),
            Route("/signed-out", shell, methods=["GET"]),
            Mount("/", StaticFiles(directory=web_dist, html=True)),
        ]
    )


# docs/specs/policy-and-identity.md: the session cookie is opaque, unreadable by script, sent only
# over HTTPS, and `Lax` because the provider sends the person back across sites. A browser treats
# `127.0.0.1` and `localhost` as secure, so a development sign-in over plain HTTP still works.
_SESSION: dict[str, Any] = {"path": "/", "secure": True, "httponly": True, "samesite": "lax"}
_SIGN_IN_COOKIE: dict[str, Any] = {**_SESSION, "path": "/api/sign-in"}


def _principal(principal: Principal) -> dict[str, Any]:
    return {"principal_id": principal.principal_id, **principal_summary(principal)}


def process_flow() -> dict[str, Any]:
    """The Blueprint's entry points and phases, the same for every deployment
    (docs/specs/orchestration.md)."""
    return {
        "entries": [dataclasses.asdict(e) for e in ENTRIES],
        "phases": [dataclasses.asdict(p) for p in PHASES],
    }


def examples(directory: Path) -> list[dict[str, Any]]:
    """The example inputs in `directory`, each with the class it names (`GET /api/examples`)."""
    found = []
    for path in sorted(directory.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        found.append(
            {"name": path.stem, "schema_class": document.get("schema_class"), "input": document}
        )
    return found


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


def _refused(detail: str, title: str = "Data Director could not start this run") -> Response:
    return _problem(400, "request-refused", title, detail)


def _unauthenticated(detail: str) -> Response:
    found = unauthenticated(detail)
    return _problem(401, found.type.removeprefix(PROBLEM_BASE), found.title or "", detail)


def _no_sign_in() -> Response:
    return _problem(
        404,
        "sign-in-unavailable",
        "This server signs nobody in",
        "No identity provider is configured: this is a development server.",
    )


def _back_to_sign_in(reason: str) -> Response:
    return RedirectResponse("/sign-in?" + urlencode({"problem": reason}), status_code=303)


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
    # missing or malformed (docs/specs/system.md), or an agent in this process configured wrongly:
    # nothing may run.
    except (
        IdentityError,
        SettingsError,
        PolicyError,
        RegistryError,
        SourceConfigError,
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
        )
        if host not in LOOPBACK and sign_in is None:
            sys.stderr.write(UNTRUSTED_WARNING.format(host=host))
        webbrowser.open(f"{base_url}/")
        uvicorn.run(app, host=host, port=port)
    except (ShellNotBuiltError, ConfigError) as exc:
        sys.exit(f"data-director: {exc}")
    finally:
        governance.conductor.close()
    return 0
