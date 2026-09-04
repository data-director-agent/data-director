"""The Starlette application: A2A, AG-UI, schema files, the store index and the static shell."""

from __future__ import annotations

import json
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from workbench.conductor import Conductor
from workbench.contract.validate import SCHEMA_DIR
from workbench.transport import agui
from workbench.transport.a2a import a2a_routes

ROOT = Path(__file__).resolve().parents[3]
SHELL_DIR = ROOT / "shell"
UISCHEMA = SHELL_DIR / "uischema.json"


def build_app(conductor: Conductor, base_url: str = "http://127.0.0.1:8000") -> Starlette:
    _card, routes = a2a_routes(conductor, base_url)

    async def agui_run(request: Request) -> Response:
        return await agui.run_agent(request, conductor)

    async def agui_replay(request: Request) -> Response:
        return await agui.replay_run(request, conductor)

    async def runs_index(request: Request) -> Response:
        items = [
            {
                "invocation_id": e["invocation_id"],
                "agent_id": e["agent_id"],
                "status": e["outcome"]["status"],
                "completed_at": e["completed_at"],
            }
            for e in conductor.store.iter_envelopes()
        ]
        return JSONResponse(list(reversed(items)))

    async def uischema(request: Request) -> Response:
        return JSONResponse(json.loads(UISCHEMA.read_text(encoding="utf-8")))

    async def sample(request: Request) -> Response:
        return FileResponse(ROOT / "samples" / "soil-chemistry.profile.json")

    async def index(request: Request) -> Response:
        return FileResponse(SHELL_DIR / "index.html")

    return Starlette(
        routes=[
            *routes,
            Route("/agui", agui_run, methods=["POST"]),
            Route("/agui/runs/{invocation_id}", agui_replay, methods=["GET"]),
            Route("/runs", runs_index, methods=["GET"]),
            Route("/schema/uischema.json", uischema, methods=["GET"]),
            Route("/samples/soil-chemistry.profile.json", sample, methods=["GET"]),
            Route("/", index, methods=["GET"]),
            Mount("/schema", StaticFiles(directory=SCHEMA_DIR), name="schema"),
            Mount("/shell", StaticFiles(directory=SHELL_DIR, html=True), name="shell"),
        ]
    )
