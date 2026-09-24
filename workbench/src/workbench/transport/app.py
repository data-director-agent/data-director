"""The Starlette application: A2A, AG-UI, the agent manifest, samples, schema files, the store
index and the static shell. Nothing here names an agent or a payload class."""

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
SAMPLES_DIR = ROOT / "samples"
UISCHEMA = SHELL_DIR / "uischema.json"


def list_samples(directory: Path = SAMPLES_DIR) -> list[dict[str, str | None]]:
    """Every JSON document in samples/, with the input class its schema_class names."""
    out: list[dict[str, str | None]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        schema_class = doc.get("schema_class") if isinstance(doc, dict) else None
        out.append({"name": path.name, "schema_class": schema_class})
    return out


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

    async def agents(request: Request) -> Response:
        return JSONResponse(
            {"agents": conductor.registry.manifest(), "unavailable": conductor.registry.unavailable}
        )

    async def samples(request: Request) -> Response:
        return JSONResponse(list_samples())

    async def sample(request: Request) -> Response:
        name = request.path_params["name"]
        # Only names the listing produced are served: no path traversal.
        if name not in {s["name"] for s in list_samples()}:
            return JSONResponse({"error": f"no sample {name}"}, status_code=404)
        return FileResponse(SAMPLES_DIR / name)

    async def index(request: Request) -> Response:
        return FileResponse(SHELL_DIR / "index.html")

    async def favicon(request: Request) -> Response:
        return FileResponse(SHELL_DIR / "favicon.ico")

    return Starlette(
        routes=[
            *routes,
            Route("/agui", agui_run, methods=["POST"]),
            Route("/agui/runs/{invocation_id}", agui_replay, methods=["GET"]),
            Route("/runs", runs_index, methods=["GET"]),
            Route("/schema/uischema.json", uischema, methods=["GET"]),
            Route("/agents", agents, methods=["GET"]),
            Route("/samples", samples, methods=["GET"]),
            Route("/samples/{name}", sample, methods=["GET"]),
            Route("/", index, methods=["GET"]),
            Route("/favicon.ico", favicon, methods=["GET"]),
            Mount("/schema", StaticFiles(directory=SCHEMA_DIR), name="schema"),
            Mount("/shell", StaticFiles(directory=SHELL_DIR, html=True), name="shell"),
        ]
    )
