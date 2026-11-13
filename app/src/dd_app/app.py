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
`GET /api/about` names the build (version and commit) and says whether reports can be filed;
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
not exist, and a member asking for an owner's action `403` (docs/specs/projects.md). `/api/about`,
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
from starlette.responses import (
    FileResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from dd_app import deposit, documents, feedback
from dd_app.about import about
from dd_app.config import EXAMPLES_DIR, WEB_DIST, settings_from_env
from dd_app.github_auth import TokenSource
from dd_app.governance import (
    CREATED_BY_ROUTE,
    AttachedDocument,
    Governance,
    TurnConflictError,
    UnknownConversationError,
    principal_summary,
)
from dd_app.model_accounts import broker_path
from dd_harness import orcid
from dd_harness.conductor import UnknownAgent
from dd_harness.deposit import PackageRefusedError, build_package, check
from dd_harness.disclosure import disclose
from dd_harness.identity import IdentityError, Unauthenticated
from dd_harness.model_grants import jwks_routes
from dd_harness.policy import PolicyError
from dd_harness.project_access import Action, allowed
from dd_harness.projects import (
    TITLE_BY_RESEARCHER,
    ChangeRefusedError,
    ProjectError,
    Refusal,
    UnknownProjectError,
)
from dd_harness.registry import RegistryError
from dd_harness.requirements import RequirementsError
from dd_harness.server import LOOPBACK
from dd_harness.sessions import PENDING_S, SESSION_COOKIE, SIGN_IN_COOKIE, cookie
from dd_harness.settings import SettingsError
from dd_harness.signin import CALLBACK_PATH, SignIn, SignInSettings
from dd_harness.sources import SourceConfigError
from dd_harness.transport.a2a import a2a_routes
from dd_harness.transport.paging import PagingError, page_params, page_response
from dd_sdk.contract.models import Principal, ReplyAnswers, now
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
PROGRESS_REFUSED = "Data Director could not record where the project is"
INTAKE_REFUSED = "Data Director could not record this answer"
TITLE_REFUSED = "Data Director could not rename this project"
CREATE_REFUSED = "Data Director could not create this project"
REPOSITORY_REFUSED = "Data Director could not record this repository"
RESEARCHER_REFUSED = "Data Director could not keep these ORCID facts"
INVENTORY_REFUSED = "Data Director could not add this inventory"
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
    orcid_transport: httpx.BaseTransport | None = None,
    model_broker_path: str | None = None,
) -> Starlette:
    """The server. `web_dist` must hold a built shell (its `index.html`).

    Problem reports are on when `feedback_source` is given; `feedback_client` and `build` let a test
    stand in for GitHub and for the build's identity. `sign_in` signs people in; its
    authenticator must be `governance.authenticator`. Without it, the server signs nobody in.
    `orcid_transport` lets a test stand in for ORCID's public API (`dd_harness.orcid`).
    `model_broker_path` is where the browser reaches the model broker (`dd_app.model_accounts`);
    with it and a harness that mints model grants, a person may add their own model account.
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

    def signed_in(handler: Handler) -> Callable[[Request], Awaitable[Response]]:
        """`handler`, given the principal the request acts for; a request with none is refused
        with `401` (docs/specs/policy-and-identity.md), and never given a default."""

        async def endpoint(request: Request) -> Response:
            if (refused := _requires_json(request)) is not None:
                return refused
            try:
                principal = governance.authenticator.principal_for(request.headers)
            except Unauthenticated as exc:
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
            return await handler(request, principal)

        return signed_in(checked)

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

    # Each person sees only their own runs and conversations (#153); someone else's is answered
    # with 404, as one that does not exist.
    async def list_runs(request: Request, reader: Principal) -> Response:
        try:
            paging = page_params(request)
        except PagingError as exc:
            return _refused(str(exc), "Data Director could not list the runs")
        page = await run_in_threadpool(lambda: governance.runs(reader, **paging))
        return page_response(request, page)

    async def get_run(request: Request, reader: Principal) -> Response:
        invocation_id = request.path_params["invocation_id"]
        run = await run_in_threadpool(governance.stored_run, invocation_id, reader)
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
        found = governance.conversation(conversation_id, acting_for) or {}
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
        allowed = {
            "agent_id",
            "message_text",
            "follows",
            "inventory",
            "documentation",
            "reply_answers",
        }
        if extra := sorted(set(body) - allowed):
            return _refused(
                "A turn takes only `agent_id`, `message_text`, `follows`, `inventory`, "
                f"`documentation` and `reply_answers`, not {extra}."
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
        documentation = None
        if body.get("documentation") is not None:
            attached = body["documentation"]
            fields = ("name", "media_type", "text")
            if not (
                isinstance(attached, dict)
                and set(attached) == set(fields)
                and all(isinstance(attached[key], str) for key in fields)
            ):
                return _refused(
                    "`documentation` must be an object giving the document's `name`, "
                    "`media_type` and `text`, as strings."
                )
            documentation = AttachedDocument(**attached)
        if not message_text.strip() and inventory is None and documentation is None:
            return _refused("The message is empty.")
        answer = None
        if body.get("reply_answers") is not None:
            try:
                answer = ReplyAnswers.model_validate(body["reply_answers"])
            except ValueError:
                return _refused(
                    "`reply_answers` must name the turn it answers (`answer_to`) and give "
                    "`given_answers`: for each question answered, its `answered_key`, the "
                    "`answer_values` chosen and optionally `answer_words`."
                )
        if await run_in_threadpool(governance.conversation, conversation_id, acting_for) is None:
            return _no_conversation(conversation_id)
        started = time.monotonic()
        outcome = "answered"
        try:
            return JSONResponse(
                await governance.turn(
                    conversation_id,
                    agent_id,
                    message_text,
                    follows,
                    acting_for,
                    inventory,
                    answer,
                    documentation,
                )
            )
        except UnknownConversationError:
            outcome = "unknown conversation"
            return _no_conversation(conversation_id)
        except TurnConflictError as exc:
            outcome = "conflict"
            return _problem(409, "turn-conflict", "The conversation has moved on", exc.detail)
        # A `ProjectError` (an inventory or document the project refuses) is a `ValueError`.
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

    async def list_conversations(request: Request, reader: Principal) -> Response:
        try:
            paging = page_params(request)
        except PagingError as exc:
            return _refused(str(exc), "Data Director could not list the conversations")
        page = await run_in_threadpool(lambda: governance.conversations(reader, **paging))
        return page_response(request, page)

    async def get_conversation(request: Request, reader: Principal) -> Response:
        conversation_id = request.path_params["conversation_id"]
        found = await run_in_threadpool(governance.conversation, conversation_id, reader)
        if found is None:
            return _no_conversation(conversation_id)
        return JSONResponse(found)

    async def list_projects(request: Request, reader: Principal) -> Response:
        try:
            paging = page_params(request)
        except PagingError as exc:
            return _refused(str(exc), "Data Director could not list the projects")
        page = await run_in_threadpool(lambda: governance.projects_for(reader, **paging))
        return page_response(request, page)

    async def create_project(request: Request, person: Principal) -> Response:
        """A project of its own, with no conversation, named by the optional `title` the body
        gives (docs/specs/app.md, rule 27). Whom it is created for is whom the authenticator
        names, never the body. Answers `201` with its summary as `GET /api/projects` lists it."""
        store = governance.projects
        if store is None:
            return _problem(
                404, "project-not-found", "No such project", "This server keeps no projects."
            )
        try:
            body = await request.json()
        except ValueError:
            return _refused("The body is not JSON.", CREATE_REFUSED)
        if not isinstance(body, dict):
            return _refused("The body must be an object.", CREATE_REFUSED)
        extra = sorted(set(body) - {"title"})
        if extra:
            return _refused(f"Unexpected field(s): {', '.join(extra)}.", CREATE_REFUSED)
        title = body.get("title")
        if title is not None and not isinstance(title, str):
            return _refused("`title` is the project's name, or left out.", CREATE_REFUSED)

        def create() -> dict[str, Any]:
            project_id = store.create(acted_for=person, caused_by=CREATED_BY_ROUTE, title=title)
            return {**store.summary(project_id), "conversations": []}

        try:
            return JSONResponse(await run_in_threadpool(create), status_code=201)
        except ProjectError as exc:
            return _refused(str(exc), CREATE_REFUSED)

    async def get_documents(request: Request, _: Principal) -> Response:
        project_id = request.path_params["project_id"]
        if governance.projects is None:
            return _no_project(project_id)
        try:
            found = await run_in_threadpool(documents.view, governance.projects, project_id)
        except UnknownProjectError:
            return _no_project(project_id)
        return JSONResponse(found)

    async def get_inventory(request: Request, _: Principal) -> Response:
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

    async def add_inventory(request: Request, person: Principal) -> Response:
        """A revised or new inventory for the project, outside a turn. The store checks it against
        the `FileInventory` class schema and records which inventory it revises; whom it acts for
        is whom the authenticator names, never the body."""
        project_id = request.path_params["project_id"]
        store = governance.projects
        if store is None:
            return _no_project(project_id)
        try:
            body = await request.json()
        except ValueError:
            return _refused("The body is not JSON.", INVENTORY_REFUSED)
        inventory = body.get("inventory") if isinstance(body, dict) else None
        if not isinstance(inventory, dict):
            return _refused(
                "`inventory` must be the object `dd-inventory` wrote.", INVENTORY_REFUSED
            )

        def add() -> dict[str, Any]:
            store.add_inventory(
                project_id, inventory, acted_for=person, caused_by=f"POST {request.url.path}"
            )
            held: dict[str, Any] = store.summary(project_id)["inventory"]
            return held

        try:
            return JSONResponse(await run_in_threadpool(add), status_code=201)
        except UnknownProjectError:
            return _no_project(project_id)
        except ProjectError as exc:
            return _refused(str(exc), INVENTORY_REFUSED)

    async def list_documentation(request: Request, _: Principal) -> Response:
        project_id = request.path_params["project_id"]
        store = governance.projects
        if store is None:
            return _no_project(project_id)
        try:
            found = await run_in_threadpool(store.documentation, project_id)
        except UnknownProjectError:
            return _no_project(project_id)
        return JSONResponse(found)

    async def get_documentation(request: Request, _: Principal) -> Response:
        project_id, digest = request.path_params["project_id"], request.path_params["digest"]
        store = governance.projects
        if store is None:
            return _no_project(project_id)
        try:
            found = await run_in_threadpool(store.documentation_text, project_id, digest)
        except UnknownProjectError:
            return _no_project(project_id)
        if found is None:
            return _problem(
                404,
                "documentation-not-found",
                "No such document",
                f"Project {project_id!r} holds no document {digest!r}.",
            )
        return PlainTextResponse(found)

    def read_orcid(person: Principal) -> dict[str, Any]:
        """`person`'s own public ORCID record as a `ResearcherRecord`: only their own iD is ever
        read, and only when they ask (docs/specs/policy-and-identity.md)."""
        issuer = orcid.issuer_of(person)
        raw = orcid.fetch_record(person.principal_id, issuer, transport=orcid_transport)
        return orcid.normalise(
            raw,
            principal_id=person.principal_id,
            retrieved_at=now(),
            source=orcid.record_url(person.principal_id, issuer),
        )

    async def get_orcid_record(request: Request, person: Principal) -> Response:
        """What the signed-in person's public ORCID record offers, to choose from. Nothing is
        kept: keeping is `keep_researcher`, which reads the record again."""
        try:
            return JSONResponse(await run_in_threadpool(read_orcid, person))
        except orcid.OrcidError as exc:
            return _problem(409, "no-orcid-record", "No ORCID record to read", str(exc))
        except orcid.OrcidUnavailableError as exc:
            return _orcid_unavailable(str(exc))

    async def list_researchers(request: Request, _: Principal) -> Response:
        project_id = request.path_params["project_id"]
        store = governance.projects
        if store is None:
            return _no_project(project_id)
        try:
            return JSONResponse(await run_in_threadpool(store.researchers, project_id) or [])
        except UnknownProjectError:
            return _no_project(project_id)

    async def keep_researcher(request: Request, person: Principal) -> Response:
        """Keep in the project what the person ticked of their own public ORCID record. The body
        names a choice (`{"keep": {"sections": [...], "works": [put-codes], ...}}`), never the
        facts: the record is read again and only what it holds is kept, so the project holds
        ORCID's own words (docs/specs/projects.md). Answers with the project's records."""
        project_id = request.path_params["project_id"]
        store = governance.projects
        if store is None:
            return _no_project(project_id)
        try:
            body = await request.json()
        except ValueError:
            return _refused("The body is not JSON.", RESEARCHER_REFUSED)
        keep = body.get("keep") if isinstance(body, dict) else None
        if not isinstance(keep, dict):
            return _refused("`keep` names the sections and items to keep.", RESEARCHER_REFUSED)
        caused_by = f"{request.method} {request.url.path}"

        def add() -> list[dict[str, Any]]:
            chosen = orcid.select(read_orcid(person), keep)
            store.add_researcher(project_id, chosen, acted_for=person, caused_by=caused_by)
            return store.researchers(project_id) or []

        try:
            return JSONResponse(await run_in_threadpool(add), status_code=201)
        except UnknownProjectError:
            return _no_project(project_id)
        except orcid.OrcidUnavailableError as exc:
            return _orcid_unavailable(str(exc))
        except (orcid.OrcidError, ProjectError) as exc:
            return _refused(str(exc), RESEARCHER_REFUSED)

    async def withdraw_researcher(request: Request, person: Principal) -> Response:
        """Stop giving agents the ORCID facts the person kept in the project. Answers with the
        project's records that stand."""
        project_id = request.path_params["project_id"]
        store = governance.projects
        if store is None:
            return _no_project(project_id)
        caused_by = f"{request.method} {request.url.path}"

        def withdraw() -> list[dict[str, Any]]:
            store.withdraw_researcher(
                project_id, person.principal_id, acted_for=person, caused_by=caused_by
            )
            return store.researchers(project_id) or []

        try:
            return JSONResponse(await run_in_threadpool(withdraw))
        except UnknownProjectError:
            return _no_project(project_id)
        except ProjectError as exc:
            return _problem(404, "researcher-not-found", "Nothing of yours to withdraw", str(exc))

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

    async def get_progress(request: Request, _: Principal) -> Response:
        project_id = request.path_params["project_id"]
        store = governance.projects
        if store is None:
            return _no_project(project_id)
        try:
            return JSONResponse(await run_in_threadpool(store.progress, project_id))
        except UnknownProjectError:
            return _no_project(project_id)

    async def change_progress(request: Request, person: Principal) -> Response:
        """The researcher's word on where the project is: the entry point they chose, or a step
        they marked done, skipped or open again (docs/specs/orchestration.md). Whom it acts for is
        whom the authenticator names, never the body. Answers with the progress derived anew."""
        project_id = request.path_params["project_id"]
        store = governance.projects
        if store is None:
            return _no_project(project_id)
        try:
            body = await request.json()
        except ValueError:
            return _refused("The body is not JSON.", PROGRESS_REFUSED)
        if not isinstance(body, dict):
            return _refused("The body is not a JSON object.", PROGRESS_REFUSED)
        step_id = request.path_params.get("step_id")
        caused_by = f"{request.method} {request.url.path}"

        def change() -> dict[str, Any]:
            if step_id is None:
                entry = body.get("entry")
                if not isinstance(entry, int) or isinstance(entry, bool):
                    raise ProjectError("`entry` is the entry point's number, 1, 2 or 3.")
                store.choose_entry(project_id, entry, acted_for=person, caused_by=caused_by)
            else:
                mark = body.get("mark")
                if not isinstance(mark, str):
                    raise ProjectError("`mark` is one of done, skipped or open.")
                store.mark_step(project_id, step_id, mark, acted_for=person, caused_by=caused_by)
            return store.progress(project_id)

        try:
            return JSONResponse(await run_in_threadpool(change), status_code=201)
        except UnknownProjectError:
            return _no_project(project_id)
        except ProjectError as exc:
            return _refused(str(exc), PROGRESS_REFUSED)

    async def get_intake(request: Request, _: Principal) -> Response:
        project_id = request.path_params["project_id"]
        store = governance.projects
        if store is None:
            return _no_project(project_id)
        try:
            return JSONResponse(await run_in_threadpool(store.intake, project_id))
        except UnknownProjectError:
            return _no_project(project_id)

    async def answer_intake(request: Request, person: Principal) -> Response:
        """The researcher's answer to one intake question (docs/specs/app.md, rule 25), recorded
        for whom the authenticator names, never the body. A malformed body is refused with `400`
        and an answer the harness rejects with `409`, recording nothing; otherwise the server
        answers with where the intake then stands: the next question, or the progress the card
        names once it is complete."""
        project_id = request.path_params["project_id"]
        question_id = request.path_params["question_id"]
        store = governance.projects
        if store is None:
            return _no_project(project_id)
        try:
            body = await request.json()
        except ValueError:
            return _refused("The body is not JSON.", INTAKE_REFUSED)
        values = body.get("answer_values") if isinstance(body, dict) else None
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            return _refused(
                "The body is an object whose `answer_values` is a list of option values.",
                INTAKE_REFUSED,
            )
        caused_by = f"{request.method} {request.url.path}"

        def record() -> dict[str, Any]:
            store.answer_intake(
                project_id, question_id, values, acted_for=person, caused_by=caused_by
            )
            return store.intake(project_id)

        try:
            return JSONResponse(await run_in_threadpool(record), status_code=201)
        except UnknownProjectError:
            return _no_project(project_id)
        except ProjectError as exc:
            return _problem(409, "intake-answer-refused", INTAKE_REFUSED, str(exc))

    async def dismiss_intake(request: Request, person: Principal) -> Response:
        """The researcher passing the intake by (docs/specs/app.md, rule 25); an answer recorded
        later opens it again. Answers with where the intake then stands."""
        project_id = request.path_params["project_id"]
        store = governance.projects
        if store is None:
            return _no_project(project_id)
        caused_by = f"{request.method} {request.url.path}"

        def dismiss() -> dict[str, Any]:
            store.dismiss_intake(project_id, acted_for=person, caused_by=caused_by)
            return store.intake(project_id)

        try:
            return JSONResponse(await run_in_threadpool(dismiss), status_code=201)
        except UnknownProjectError:
            return _no_project(project_id)

    async def rename_project(request: Request, person: Principal) -> Response:
        """A person's name for the project, which a model's never replaces
        (docs/specs/projects.md). Whom it acts for is whom the authenticator names, never the
        body. Answers with the project's summary."""
        project_id = request.path_params["project_id"]
        store = governance.projects
        if store is None:
            return _no_project(project_id)
        try:
            body = await request.json()
        except ValueError:
            return _refused("The body is not JSON.", TITLE_REFUSED)
        title = body.get("title") if isinstance(body, dict) else None
        if not isinstance(title, str):
            return _refused("`title` is the project's new name.", TITLE_REFUSED)
        caused_by = f"{request.method} {request.url.path}"

        def rename() -> dict[str, Any]:
            store.rename(
                project_id,
                title,
                source=TITLE_BY_RESEARCHER,
                acted_for=person,
                caused_by=caused_by,
            )
            return store.summary(project_id)

        try:
            return JSONResponse(await run_in_threadpool(rename))
        except UnknownProjectError:
            return _no_project(project_id)
        except ProjectError as exc:
            return _refused(str(exc), TITLE_REFUSED)

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

    async def list_examples(request: Request, _: Principal) -> Response:
        return JSONResponse(examples(examples_dir))

    async def get_process_flow(request: Request, _: Principal) -> Response:
        return JSONResponse(process_flow())

    identity = dict(build) if build is not None else about()
    started = time.monotonic()

    async def server_status(request: Request) -> Response:
        # Answers a monitor's `GET /server-status?auto` (collectd's apache plugin), in the shape
        # Apache's mod_status uses: `Key: value` lines. Open on the app's own port; NGINX answers
        # 404 to it, so only the VM's monitor reaches it.
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

    async def send_feedback(request: Request, reporter: Principal) -> Response:
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
            # Only what the reporter may read themselves goes into a report (#153).
            if report.run and (stored := governance.stored_run(report.run, reporter)) is not None:
                context += feedback.run_context(stored)
            if report.conversation:
                found = governance.conversation(report.conversation, reporter)
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
        if (refused := _requires_json(request)) is not None:
            return refused
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
                    "model_accounts": model_accounts,
                }
            )
        session = sign_in.authenticator.session(request.headers, touch=request.method == "POST")
        body: dict[str, Any] = {
            "signs_in": True,
            "issuer": sign_in.issuer,
            "model_accounts": model_accounts,
        }
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

    async def model_account_ticket(request: Request, acting_for: Principal) -> Response:
        # The ticket names the person only by their pseudonym, sealed to the broker. The key
        # itself goes from the browser to the broker and never comes here.
        if not model_accounts or minter is None or model_broker_path is None:
            return _problem(
                404,
                "model-accounts-unavailable",
                "Own model accounts are not offered here",
                "This deployment does not let people add their own model account.",
            )
        ticket, expires = minter.enrolment_ticket(acting_for=acting_for)
        return JSONResponse(
            {
                "ticket": ticket,
                "broker_url": model_broker_path,
                "expires_at": datetime.fromtimestamp(expires, UTC)
                .isoformat()
                .replace("+00:00", "Z"),
            },
            headers={"Cache-Control": "no-store"},
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
        if (refused := _requires_json(request)) is not None:
            return refused
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
            Route("/api/projects", signed_in(create_project), methods=["POST"]),
            Route(
                "/api/projects/{project_id}/title",
                in_project(Action.CONTRIBUTE, rename_project),
                methods=["PUT"],
            ),
            Route(
                "/api/projects/{project_id}/documents",
                in_project(Action.READ, get_documents),
                methods=["GET"],
            ),
            Route(
                "/api/projects/{project_id}/inventory",
                in_project(Action.READ, get_inventory),
                methods=["GET"],
            ),
            Route(
                "/api/projects/{project_id}/inventory",
                in_project(Action.CONTRIBUTE, add_inventory),
                methods=["POST"],
            ),
            Route(
                "/api/projects/{project_id}/documentation",
                in_project(Action.READ, list_documentation),
                methods=["GET"],
            ),
            Route(
                "/api/projects/{project_id}/documentation/{digest}",
                in_project(Action.READ, get_documentation),
                methods=["GET"],
            ),
            Route(
                "/api/projects/{project_id}/researchers",
                in_project(Action.READ, list_researchers),
                methods=["GET"],
            ),
            Route(
                "/api/projects/{project_id}/researchers/me",
                in_project(Action.CONTRIBUTE, keep_researcher),
                methods=["PUT"],
            ),
            Route(
                "/api/projects/{project_id}/researchers/me",
                in_project(Action.CONTRIBUTE, withdraw_researcher),
                methods=["DELETE"],
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
            Route(
                "/api/projects/{project_id}/progress",
                in_project(Action.READ, get_progress),
                methods=["GET"],
            ),
            Route(
                "/api/projects/{project_id}/progress/entry",
                in_project(Action.CONTRIBUTE, change_progress),
                methods=["PUT"],
            ),
            Route(
                "/api/projects/{project_id}/progress/steps/{step_id}",
                in_project(Action.CONTRIBUTE, change_progress),
                methods=["PUT"],
            ),
            Route(
                "/api/projects/{project_id}/intake",
                in_project(Action.READ, get_intake),
                methods=["GET"],
            ),
            # Before the route below, which would read `dismiss` as a question.
            Route(
                "/api/projects/{project_id}/intake/dismiss",
                in_project(Action.CONTRIBUTE, dismiss_intake),
                methods=["POST"],
            ),
            Route(
                "/api/projects/{project_id}/intake/{question_id}",
                in_project(Action.CONTRIBUTE, answer_intake),
                methods=["POST"],
            ),
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
            Route("/api/researcher/orcid", signed_in(get_orcid_record), methods=["GET"]),
            Route("/api/examples", signed_in(list_examples), methods=["GET"]),
            Route("/api/process-flow", signed_in(get_process_flow), methods=["GET"]),
            Route("/api/policy", signed_in(get_policy), methods=["GET"]),
            Route("/api/about", get_about, methods=["GET"]),
            Route("/server-status", server_status, methods=["GET"]),
            Route("/api/feedback", signed_in(send_feedback), methods=["POST"]),
            Route("/api/session", get_session, methods=["GET", "POST"]),
            Route("/api/model-account/ticket", signed_in(model_account_ticket), methods=["POST"]),
            Route("/api/sign-in", begin_sign_in, methods=["GET"]),
            Route(CALLBACK_PATH, finish_sign_in, methods=["GET"]),
            Route("/api/sign-out", sign_out, methods=["POST"]),
            *delegation,
            # The harness's public keys for model grants, when it mints them
            # (docs/specs/model-accounts.md).
            *jwks_routes(governance.conductor.model_grants),
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


def _refused(detail: str, title: str = "Data Director could not start this run") -> Response:
    return _problem(400, "request-refused", title, detail)


def _orcid_unavailable(detail: str) -> Response:
    return _problem(502, "orcid-unavailable", "ORCID could not be reached", detail)


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
