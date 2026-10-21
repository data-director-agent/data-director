"""The app's web server: the shell's API beside the built shell (ADR-0024).

`GET /api/agents` is what the shell draws its capabilities panel from. Every other path serves
the shell built from `app/web` (`npm run build` writes `app/web/dist`). The app stops at
start-up, with one line, if a setting is wrong or the shell has not been built.

Serves on http://127.0.0.1:7860 by default; `DD_APP_HOST` and `DD_APP_PORT` change the address.
"""

from __future__ import annotations

import os
import sys
import webbrowser
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from dd_app.config import WEB_DIST, settings_from_env
from dd_app.governance import Governance
from dd_harness.identity import IdentityError
from dd_harness.policy import PolicyError
from dd_harness.registry import RegistryError
from dd_harness.settings import SettingsError
from dd_harness.sources import SourceConfigError

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7860


class ShellNotBuiltError(FileNotFoundError):
    """`app/web/dist` holds no built shell."""


def build_app(governance: Governance, web_dist: Path = WEB_DIST) -> Starlette:
    """The server. `web_dist` must hold a built shell (its `index.html`)."""
    if not (web_dist / "index.html").is_file():
        raise ShellNotBuiltError(
            f"the shell is not built ({web_dist / 'index.html'} is missing); "
            "run `npm ci && npm run build` in app/web"
        )

    async def agents(request: Request) -> Response:
        return JSONResponse(governance.agents())

    return Starlette(
        routes=[
            Route("/api/agents", agents, methods=["GET"]),
            Mount("/", StaticFiles(directory=web_dist, html=True)),
        ]
    )


def main() -> int:
    """The `data-director` console script."""
    try:
        governance = Governance.create(settings_from_env())
    # No principal (ADR-0018), or a profile, agent list or source list that is unset, missing
    # or malformed (ADR-0022): nothing may run.
    except (IdentityError, SettingsError, PolicyError, RegistryError, SourceConfigError) as exc:
        sys.exit(f"data-director: {exc}")
    try:
        app = build_app(governance)
        host = os.environ.get("DD_APP_HOST", DEFAULT_HOST)
        port = int(os.environ.get("DD_APP_PORT", DEFAULT_PORT))
        webbrowser.open(f"http://{host}:{port}/")
        uvicorn.run(app, host=host, port=port)
    except ShellNotBuiltError as exc:
        sys.exit(f"data-director: {exc}")
    finally:
        governance.worker.shutdown()
    return 0
