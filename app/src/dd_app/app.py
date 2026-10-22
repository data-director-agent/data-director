"""The app's web server: the shell's API beside the built shell (ADR-0024).

`GET /api/agents` is what the shell draws its capabilities panel from. `POST /api/runs` runs an
agent through the conductor and answers when the run has ended, with its envelope and the
checks' reports; `GET /api/runs` and `GET /api/runs/{id}` read the run store; `GET /api/examples`
lists example inputs. The run endpoint is a stopgap until runs stream over AG-UI (#68, #69).
`POST /api/conversations` starts a conversation and `POST /api/conversations/{id}/turns` sends it
one message, answered as a run is; `GET /api/conversations` and `GET /api/conversations/{id}`
read them back as the harness derives them from the run store (ADR-0012, #130).
`POST /a2a` and `GET /.well-known/agent-card.json` are the conductor's A2A routes, which accept a
delegation agent's callback under a live grant and nothing else (ADR-0012, #129).
Every other path serves the shell built from `app/web` (`npm run build` writes `app/web/dist`).
The app stops at start-up, with one line, if a setting is wrong or the shell has not been built.

Serves on http://127.0.0.1:7860 by default; `DD_APP_HOST` and `DD_APP_PORT` change the address,
and `DD_HARNESS_URL` the address the agents call back on, if they reach the app by another.
"""

from __future__ import annotations

import json
import os
import sys
import webbrowser
from pathlib import Path
from typing import Any

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from dd_app.config import EXAMPLES_DIR, WEB_DIST, settings_from_env
from dd_app.governance import Governance, UnknownConversationError
from dd_harness.conductor import UnknownAgent
from dd_harness.identity import IdentityError
from dd_harness.policy import PolicyError
from dd_harness.registry import RegistryError
from dd_harness.server import LOOPBACK
from dd_harness.settings import SettingsError
from dd_harness.sources import SourceConfigError
from dd_harness.transport.a2a import a2a_routes
from dd_sdk.contract.problem import PROBLEM_BASE
from dd_sdk.contract.validate import ContractViolation
from dd_sdk.credentials import ConfigError

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7860
UNTRUSTED_WARNING = (
    "data-director: warning: serving on {host}. A delegation grant is a bearer token and callers "
    "are not authenticated; expose the app to the host or a private network only (ADR-0011).\n"
)


class ShellNotBuiltError(FileNotFoundError):
    """`app/web/dist` holds no built shell."""


def build_app(
    governance: Governance, web_dist: Path = WEB_DIST, examples_dir: Path = EXAMPLES_DIR
) -> Starlette:
    """The server. `web_dist` must hold a built shell (its `index.html`)."""
    if not (web_dist / "index.html").is_file():
        raise ShellNotBuiltError(
            f"the shell is not built ({web_dist / 'index.html'} is missing); "
            "run `npm ci && npm run build` in app/web"
        )

    async def agents(request: Request) -> Response:
        return JSONResponse(governance.agents())

    async def start_run(request: Request) -> Response:
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
            return JSONResponse(await governance.run(agent_id, input))
        # Refused before the run began, so nothing was stored (as `workbench/transport/agui.py`).
        except (ContractViolation, ValueError, UnknownAgent, PolicyError, IdentityError) as exc:
            return _refused(str(exc))

    async def list_runs(request: Request) -> Response:
        return JSONResponse(governance.runs())

    async def get_run(request: Request) -> Response:
        invocation_id = request.path_params["invocation_id"]
        run = governance.stored_run(invocation_id)
        if run is None:
            return _problem(404, "run-not-found", "No such run", f"No run {invocation_id!r}.")
        return JSONResponse(run)

    async def start_conversation(request: Request) -> Response:
        conversation_id = governance.start_conversation()
        return JSONResponse(
            {"conversation_id": conversation_id},
            status_code=201,
            headers={"Location": f"/api/conversations/{conversation_id}"},
        )

    async def send_turn(request: Request) -> Response:
        conversation_id = request.path_params["conversation_id"]
        try:
            body = await request.json()
        except ValueError:
            return _refused("The body is not JSON.")
        if not isinstance(body, dict):
            return _refused("The body must be an object with `agent_id` and `message_text`.")
        if "history" in body:
            return _refused(
                "A turn may not give a history: the server builds it from the stored turns."
            )
        if extra := sorted(set(body) - {"agent_id", "message_text"}):
            return _refused(f"A turn takes only `agent_id` and `message_text`, not {extra}.")
        agent_id, message_text = body.get("agent_id"), body.get("message_text")
        if not isinstance(agent_id, str) or not isinstance(message_text, str):
            return _refused("The body must name `agent_id` and give `message_text`, as strings.")
        if not message_text.strip():
            return _refused("The message is empty.")
        if governance.conversation(conversation_id) is None:
            return _no_conversation(conversation_id)
        try:
            return JSONResponse(await governance.turn(conversation_id, agent_id, message_text))
        except UnknownConversationError:
            return _no_conversation(conversation_id)
        except (ContractViolation, ValueError, UnknownAgent, PolicyError, IdentityError) as exc:
            return _refused(str(exc))

    async def list_conversations(request: Request) -> Response:
        return JSONResponse(governance.conversations())

    async def get_conversation(request: Request) -> Response:
        conversation_id = request.path_params["conversation_id"]
        found = governance.conversation(conversation_id)
        if found is None:
            return _no_conversation(conversation_id)
        return JSONResponse(found)

    async def list_examples(request: Request) -> Response:
        return JSONResponse(examples(examples_dir))

    callback = governance.conductor.harness_url
    # No authenticator: delegation callbacks only, so the app is no other way in (ADR-0012).
    delegation = a2a_routes(governance.conductor, None, callback)[1] if callback else []
    return Starlette(
        routes=[
            Route("/api/agents", agents, methods=["GET"]),
            Route("/api/runs", start_run, methods=["POST"]),
            Route("/api/runs", list_runs, methods=["GET"]),
            Route("/api/runs/{invocation_id}", get_run, methods=["GET"]),
            Route("/api/conversations", start_conversation, methods=["POST"]),
            Route("/api/conversations", list_conversations, methods=["GET"]),
            Route("/api/conversations/{conversation_id}", get_conversation, methods=["GET"]),
            Route("/api/conversations/{conversation_id}/turns", send_turn, methods=["POST"]),
            Route("/api/examples", list_examples, methods=["GET"]),
            *delegation,
            Mount("/", StaticFiles(directory=web_dist, html=True)),
        ]
    )


def examples(directory: Path) -> list[dict[str, Any]]:
    """The example inputs in `directory`, each with the class it names (`GET /api/examples`)."""
    found = []
    for path in sorted(directory.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        found.append(
            {"name": path.stem, "schema_class": document.get("schema_class"), "input": document}
        )
    return found


def _problem(status: int, slug: str, title: str, detail: str) -> Response:
    return JSONResponse(
        {"type": PROBLEM_BASE + slug, "title": title, "status": status, "detail": detail},
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


def _refused(detail: str) -> Response:
    return _problem(400, "request-refused", "Data Director could not start this run", detail)


def main() -> int:
    """The `data-director` console script."""
    host = os.environ.get("DD_APP_HOST", DEFAULT_HOST)
    port = int(os.environ.get("DD_APP_PORT", DEFAULT_PORT))
    try:
        governance = Governance.create(settings_from_env(), f"http://{host}:{port}")
    # No principal (ADR-0018), or a profile, agent list or source list that is unset, missing
    # or malformed (ADR-0022), or an agent in this process configured wrongly: nothing may run.
    except (
        IdentityError,
        SettingsError,
        PolicyError,
        RegistryError,
        SourceConfigError,
        ConfigError,
    ) as exc:
        sys.exit(f"data-director: {exc}")
    try:
        app = build_app(governance)
        if host not in LOOPBACK:
            sys.stderr.write(UNTRUSTED_WARNING.format(host=host))
        webbrowser.open(f"http://{host}:{port}/")
        uvicorn.run(app, host=host, port=port)
    except ShellNotBuiltError as exc:
        sys.exit(f"data-director: {exc}")
    finally:
        governance.worker.shutdown()
    return 0
