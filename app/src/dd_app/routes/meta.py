"""What the shell reads about the deployment, problem reports, and the shell itself.

`GET /api/about` names the build (version and commit), says whether reports can be filed and gives
the operator's privacy notice (`DD_PRIVACY_NOTICE_URL`) if there is one, and whether it may
describe folders on its own machine (`server_folders`, `dd_app.folder_scan`);
`POST /api/feedback` files a problem report or feature request as a GitHub issue
(docs/specs/app.md). `GET /api/policy` is the profile the gate holds runs to, `GET /api/examples`
lists example inputs and `GET /api/process-flow` is the Blueprint's entry points and phases
(`dd_sdk.process_flow`), which the shell's phase tracker draws. `GET /server-status` answers a
monitor. The shell's own pages serve its `index.html`.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from starlette.routing import Route

from dd_app import feedback
from dd_app.routes.common import Deps, bind, problem, read_json, refused, signed_in
from dd_sdk.contract.models import Principal
from dd_sdk.process_flow import ENTRIES, PHASES

log = logging.getLogger(__name__)

FEEDBACK_REFUSED = "Data Director could not file this report"
# The shell's pages, each of which a reload or a link may land on.
SHELL_PAGES = (
    "/activity",
    "/agents",
    "/policy",
    "/feedback",
    "/profile",
    "/projects",
    "/projects/{project_id}",
    "/settings",
    "/sign-in",
    "/signed-out",
)


def routes(deps: Deps) -> list[Route]:
    return [
        Route("/api/examples", signed_in(deps, list_examples), methods=["GET"]),
        Route("/api/process-flow", signed_in(deps, get_process_flow), methods=["GET"]),
        Route("/api/policy", signed_in(deps, get_policy), methods=["GET"]),
        Route("/api/about", bind(deps, get_about), methods=["GET"]),
        Route("/server-status", bind(deps, server_status), methods=["GET"]),
        Route("/api/feedback", signed_in(deps, send_feedback), methods=["POST"]),
    ]


def shell_routes(deps: Deps) -> list[Route]:
    """The shell's pages; they go after every other route, before the built files."""
    return [Route(page, bind(deps, shell), methods=["GET"]) for page in SHELL_PAGES]


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


async def list_examples(request: Request, _: Principal, deps: Deps) -> Response:
    return JSONResponse(examples(deps.examples_dir))


async def get_process_flow(request: Request, _: Principal, deps: Deps) -> Response:
    return JSONResponse(process_flow())


async def get_policy(request: Request, _: Principal, deps: Deps) -> Response:
    return JSONResponse(deps.governance.policy())


async def get_about(request: Request, deps: Deps) -> Response:
    deployment = await run_in_threadpool(deps.governance.deployment)
    return JSONResponse(
        {
            **deps.identity,
            **deployment,
            "feedback_enabled": deps.feedback.source is not None,
            "privacy_notice_url": deps.privacy_notice_url,
            "server_folders": deps.folder_roots is not None,
        }
    )


async def server_status(request: Request, deps: Deps) -> Response:
    # Answers a monitor's `GET /server-status?auto` (collectd's apache plugin), in the shape
    # Apache's mod_status uses: `Key: value` lines. Open on the app's own port; NGINX answers
    # 404 to it, so only the VM's monitor reaches it.
    uptime = int(time.monotonic() - deps.started)
    lines = [
        f"ServerVersion: data-director/{deps.identity.get('app_version')}",
        f"ServerUptimeSeconds: {uptime}",
        f"Uptime: {uptime}",
    ]
    return Response("\n".join(lines) + "\n", media_type="text/plain")


async def send_feedback(request: Request, reporter: Principal, deps: Deps) -> Response:
    settings = deps.feedback
    if settings.source is None:
        return problem(
            503,
            "feedback-unavailable",
            "Reports are not switched on",
            "This deployment has no GitHub credential for problem reports.",
        )
    body = await read_json(request, FEEDBACK_REFUSED)
    if isinstance(body, Response):
        return body
    try:
        report = feedback.parse(body)
    except feedback.FeedbackRefusedError as exc:
        return refused(str(exc), FEEDBACK_REFUSED)
    try:
        settings.limiter.check()
    except feedback.RateLimitedError as exc:
        return problem(429, "rate-limited", "Too many reports", str(exc))
    text = feedback.issue_body(report, deps.identity, _context(report, reporter, deps))
    try:
        if settings.client is not None:
            created = await feedback.create_issue(
                report, text, repo=settings.repo, source=settings.source, client=settings.client
            )
        else:
            async with httpx.AsyncClient(timeout=feedback.GITHUB_TIMEOUT_SECONDS) as client:
                created = await feedback.create_issue(
                    report, text, repo=settings.repo, source=settings.source, client=client
                )
    except feedback.FeedbackFailedError as exc:
        log.warning("a problem report was not filed: %s", exc)
        return problem(502, "feedback-failed", "The report was not filed", str(exc))
    return JSONResponse(created, status_code=201)


def _context(report: feedback.Report, reporter: Principal, deps: Deps) -> list[str]:
    """What the report's run and conversation add, if the reporter asked for it. Only what the
    reporter may read themselves goes into a report (#153)."""
    context: list[str] = []
    if not report.include_context:
        return context
    if report.run and (stored := deps.governance.stored_run(report.run, reporter)) is not None:
        context += feedback.run_context(stored)
    if report.conversation:
        found = deps.governance.conversation(report.conversation, reporter)
        if found is not None:
            context += feedback.conversation_context(found)
    return context


async def shell(request: Request, deps: Deps) -> Response:
    # A page of the shell's own, so a reload or a link lands on it rather than a 404.
    return FileResponse(deps.web_dist / "index.html")


def not_found(deps: Deps) -> Callable[[Request, Exception], Awaitable[Response]]:
    """The answer to a path nothing serves. A person following a link or typing an address is sent
    the shell with `404`, so it shows its not-found page; everything else, such as a script
    calling a path that is not there, keeps the plain answer."""

    async def handler(request: Request, exc: Exception) -> Response:
        wants_page = (
            request.method == "GET"
            and not request.url.path.startswith("/api/")
            and "text/html" in request.headers.get("accept", "")
        )
        if wants_page:
            return FileResponse(deps.web_dist / "index.html", status_code=404)
        detail = exc.detail if isinstance(exc, HTTPException) else "Not Found"
        return PlainTextResponse(detail, status_code=404)

    return handler
