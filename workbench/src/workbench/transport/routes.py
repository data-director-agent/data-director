"""The workbench's read routes: runs, conversations, schemas, agents, samples and the viewer's
static files. Split from `workbench.transport.app` so that `build_app` only composes."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import BaseRoute, Mount, Route
from starlette.staticfiles import StaticFiles

from dd_harness import conversations
from dd_harness.conductor import Conductor
from dd_harness.remote import RemoteAgent
from dd_harness.transport.paging import PagingError, page_params, page_response
from dd_sdk.agent import describe
from dd_sdk.contract.validate import SCHEMA_DIR

ROOT = Path(__file__).resolve().parents[3]
VIEWER_DIR = ROOT / "viewer"
SAMPLES_DIR = ROOT / "samples"
UISCHEMA = VIEWER_DIR / "uischema.json"


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


def _store_routes(conductor: Conductor) -> list[BaseRoute]:
    async def runs_index(request: Request) -> Response:
        try:
            paging = page_params(request)
        except PagingError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        page = await asyncio.to_thread(lambda: conductor.store.list_runs(**paging))
        return page_response(request, page)

    async def conversations_index(request: Request) -> Response:
        try:
            paging = page_params(request)
        except PagingError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        page = await asyncio.to_thread(
            lambda: conversations.list_conversations(conductor.store, **paging)
        )
        return page_response(request, page)

    async def conversation(request: Request) -> Response:
        conversation_id = request.path_params["conversation_id"]
        found = await asyncio.to_thread(
            conversations.get_conversation, conductor.store, conversation_id
        )
        if found is None:
            return JSONResponse({"error": f"no conversation {conversation_id}"}, status_code=404)
        return JSONResponse(found)

    async def class_schema(request: Request) -> Response:
        """A class schema a stored run was checked against, by its digest
        (docs/specs/contract.md)."""
        digest = request.path_params["digest"]
        found = await asyncio.to_thread(conductor.store.get_schema, digest)
        if found is None:
            return JSONResponse({"error": f"no class schema {digest}"}, status_code=404)
        return JSONResponse(found)

    return [
        Route("/runs", runs_index, methods=["GET"]),
        Route("/conversations", conversations_index, methods=["GET"]),
        Route("/conversations/{conversation_id}", conversation, methods=["GET"]),
        Route("/schema/sha256/{digest}", class_schema, methods=["GET"]),
    ]


def _agent_routes(conductor: Conductor) -> list[BaseRoute]:
    async def agents(request: Request) -> Response:
        await asyncio.to_thread(conductor.registry.refresh)  # reads cards with asyncio.run
        return JSONResponse(conductor.registry.listing())

    async def agent_detail(request: Request) -> Response:
        agent_id = request.path_params["agent_id"]
        registered = conductor.registry.get(agent_id)
        if registered is None:
            return JSONResponse({"error": f"no agent {agent_id}"}, status_code=404)
        card = registered.card if isinstance(registered, RemoteAgent) else None
        return JSONResponse({"card": card, "spec": describe(registered.spec)})

    return [
        Route("/agents", agents, methods=["GET"]),
        Route("/agents/{agent_id}", agent_detail, methods=["GET"]),
    ]


def _static_routes() -> list[BaseRoute]:
    async def uischema(request: Request) -> Response:
        return JSONResponse(json.loads(UISCHEMA.read_text(encoding="utf-8")))

    async def samples(request: Request) -> Response:
        return JSONResponse(list_samples())

    async def sample(request: Request) -> Response:
        name = request.path_params["name"]
        # Only names the listing produced are served: no path traversal.
        if name not in {s["name"] for s in list_samples()}:
            return JSONResponse({"error": f"no sample {name}"}, status_code=404)
        return FileResponse(SAMPLES_DIR / name)

    async def index(request: Request) -> Response:
        return FileResponse(VIEWER_DIR / "index.html")

    async def favicon(request: Request) -> Response:
        return FileResponse(VIEWER_DIR / "favicon.ico")

    return [
        Route("/schema/uischema.json", uischema, methods=["GET"]),
        Route("/samples", samples, methods=["GET"]),
        Route("/samples/{name}", sample, methods=["GET"]),
        Route("/", index, methods=["GET"]),
        Route("/favicon.ico", favicon, methods=["GET"]),
        Mount("/schema", StaticFiles(directory=SCHEMA_DIR), name="schema"),
        Mount("/viewer", StaticFiles(directory=VIEWER_DIR, html=True), name="viewer"),
    ]


def read_routes(conductor: Conductor) -> list[BaseRoute]:
    """Every route here. The `/schema/...` routes come before the `/schema` mount, which is last
    in `_static_routes`."""
    return [*_store_routes(conductor), *_agent_routes(conductor), *_static_routes()]
