"""What the shell reads about the deployment, problem reports, and the shell itself.

`GET /api/about` names the build (version and commit), says whether reports can be filed and gives
the operator's privacy notice (`DD_PRIVACY_NOTICE_URL`) if there is one, and whether it may
describe folders on its own machine (`server_folders`, `dd_app.folder_scan`);
`POST /api/feedback` files a problem report or feature request as a GitHub issue
(docs/specs/app.md). `GET /api/policy` is the profile the gate holds runs to, `GET /api/sources`
is the credit each external source asks for (`dd_app.credits`), open to all; `GET /api/examples`
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
from typing import Any, Literal

import httpx
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import FileResponse, PlainTextResponse, Response
from starlette.routing import Route

from dd_app import credits as credits_file
from dd_app import feedback
from dd_app.routes.common import (
    Deps,
    ResponseBody,
    bind,
    problem,
    read_json,
    refused,
    respond,
    signed_in,
)
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
    "/sources",
    "/steward",
)


class Example(ResponseBody):
    """An example input the shell offers (`GET /api/examples`)."""

    name: str
    schema_class: str | None
    """The class the example names, or null if it names none."""
    input: dict[str, Any]


class CreditMatch(ResponseBody):
    source_id_prefixes: list[str]
    """An evidence item whose `source_id` starts with one of these is from the source."""
    snapshot_ref_prefixes: list[str]
    """An evidence item whose `snapshot_ref` starts with one of these is from the source."""


class SourceCredit(ResponseBody):
    """An external source, the credit it asks for and the terms it sets."""

    id: str
    name: str
    url: str
    kind: Literal["data", "service", "font"]
    licence: str
    """An SPDX identifier, or a `LicenseRef-` for terms without one."""
    licence_url: str
    attribution: str
    """The credit as the source asks for it, to be shown as written."""
    credit_required: bool
    non_commercial: bool
    """The source's own terms limit use to non-commercial purposes."""
    use: Literal["pinned", "live", "both"]
    terms_url: str | None
    citation: str | None
    badge_url: str | None
    match: CreditMatch


class Sources(ResponseBody):
    """The external sources the app uses, with their credits (`GET /api/sources`)."""

    sources: list[SourceCredit]


class FlowStep(ResponseBody):
    id: str
    """A stable label, `<phase>.<step>`, that an agent's `serves` names."""
    text: str
    """The Blueprint's wording, for the orchestrator; the shell shows `label`."""
    requirements: list[str]
    """The Blueprint requirements applied at this step; empty when the figure names none."""
    optional: bool
    out_of_scope: bool
    """The Blueprint has the step but this project does not yet do it."""
    person_decides: bool
    """A person decides the step (C2); no agent may serve it."""
    label: str
    """The step in a researcher's words."""
    prompt: str
    """How a researcher might open a conversation about the step."""


class FlowPhase(ResponseBody):
    number: int
    title: str
    """The Blueprint's title; the shell shows `name`."""
    steps: list[FlowStep]
    name: str
    """A short name for the phase in a researcher's words."""
    summary: str
    """One sentence on what the phase is for."""


class FlowEntry(ResponseBody):
    number: int
    text: str
    starts_at: int
    """The phase a researcher entering here joins at."""


class ProcessFlow(ResponseBody):
    """The Blueprint's entry points and phases (`GET /api/process-flow`, `dd_sdk.process_flow`)."""

    entries: list[FlowEntry]
    phases: list[FlowPhase]


class PolicyProfile(ResponseBody):
    id: str
    version: int
    ref: str
    """What every stored run records as the rules it was held to."""
    digest: str
    """SHA-256 of the profile file's bytes."""
    description: str
    orchestrator: str | None
    """The agent a conversation goes to; null when the profile names none."""


class PolicyAgent(ResponseBody):
    agent_id: str
    action_class: str
    """The action class the profile assigns the agent."""
    requires_approval: bool


class PolicyStep(ResponseBody):
    """How far a Blueprint step is delegated under this profile (#448).

    Worked out from the profile and the agents serving the step, not set by a profile key.
    """

    step_id: str
    phase_number: int
    phase_name: str
    label: str
    """The step in a researcher's words."""
    autonomy: Literal["delegated", "must_approve", "never_delegated", "not_offered"]
    """`delegated`: the agents serving it run as their class allows; `must_approve`: a serving
    agent's class needs approval, so its runs are referred; `never_delegated`: a person decides it;
    `not_offered`: no agent here does it."""
    reason: Literal["out_of_scope", "no_agent"] | None
    """Why a step is not offered; null for any other."""
    agent_ids: list[str]
    """The enabled agents serving the step."""
    action_classes: list[str]
    """The classes the profile assigns those agents."""
    refers_to: str | None
    """Whom the step's runs are referred to, such as `data_steward`; null when none."""


class Policy(ResponseBody):
    """The rules the policy gate holds every run to (`GET /api/policy`)."""

    profile: PolicyProfile
    agents: list[PolicyAgent]
    actions_requiring_approval: list[str]
    steps: list[PolicyStep]
    """Each Blueprint step in order, with how far it is delegated here."""


class DeployedProfile(ResponseBody):
    id: str
    version: int
    digest: str
    orchestrator: str | None


class About(ResponseBody):
    """The build, what the deployment runs and what it offers (`GET /api/about`, open to all)."""

    app_version: str | None
    harness_version: str | None
    commit: str | None
    profile: DeployedProfile
    unavailable: list[str]
    """The configured agents it cannot reach, by name."""
    incompatible: list[str]
    """The configured agents built against another contract, by name."""
    feedback_enabled: bool
    privacy_notice_url: str | None
    """The operator's privacy notice for this instance, or null if it has set none."""
    server_folders: bool
    """Whether it may describe folders on its own machine (`dd_app.folder_scan`)."""


class FiledIssue(ResponseBody):
    """The GitHub issue a report was filed as (`POST /api/feedback`)."""

    url: str
    number: int


def routes(deps: Deps) -> list[Route]:
    return [
        Route("/api/examples", signed_in(deps, list_examples), methods=["GET"]),
        Route("/api/process-flow", signed_in(deps, get_process_flow), methods=["GET"]),
        Route("/api/policy", signed_in(deps, get_policy), methods=["GET"]),
        Route("/api/about", bind(deps, get_about), methods=["GET"]),
        Route("/api/sources", bind(deps, get_sources), methods=["GET"]),
        Route("/server-status", bind(deps, server_status), methods=["GET"]),
        Route("/api/feedback", signed_in(deps, send_feedback), methods=["POST"]),
    ]


def shell_routes(deps: Deps) -> list[Route]:
    """The shell's pages; they go after every other route, before the built files."""
    return [Route(page, bind(deps, shell), methods=["GET"]) for page in SHELL_PAGES]


def process_flow() -> dict[str, Any]:
    """The Blueprint's entry points and phases, the same for every deployment
    (docs/specs/orchestration.md), with each tuple a list, as JSON has them."""
    return {
        "entries": [dataclasses.asdict(e) for e in ENTRIES],
        "phases": [_listed(dataclasses.asdict(p)) for p in PHASES],
    }


def _listed(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _listed(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_listed(v) for v in value]
    return value


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
    return respond(list[Example], examples(deps.examples_dir))


async def get_process_flow(request: Request, _: Principal, deps: Deps) -> Response:
    return respond(ProcessFlow, process_flow())


async def get_policy(request: Request, _: Principal, deps: Deps) -> Response:
    # It refreshes the registry, which reaches agents over the network.
    return respond(Policy, await run_in_threadpool(deps.deployment.policy))


async def get_sources(request: Request, deps: Deps) -> Response:
    # Open to all, as the credit is owed on the sign-in page too.
    found = await run_in_threadpool(credits_file.load, deps.credits_file)
    return respond(Sources, {"sources": [c.model_dump() for c in found]})


async def get_about(request: Request, deps: Deps) -> Response:
    deployment = await run_in_threadpool(deps.deployment.deployment)
    return respond(
        About,
        {
            **deps.identity,
            **deployment,
            "feedback_enabled": deps.feedback.source is not None,
            "privacy_notice_url": deps.privacy_notice_url,
            "server_folders": deps.folder_roots is not None,
        },
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
    context = await run_in_threadpool(_context, report, reporter, deps)
    deployment = await run_in_threadpool(deps.deployment.deployment)
    text = feedback.issue_body(report, deps.identity, context, deployment)
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
    return respond(FiledIssue, created, status_code=201)


def _context(report: feedback.Report, reporter: Principal, deps: Deps) -> list[str]:
    """What the report's run and conversation add, if the reporter asked for it. Only what the
    reporter may read themselves goes into a report (#153)."""
    context: list[str] = []
    if not report.include_context:
        return context
    if report.run and (stored := deps.reads.stored_run(report.run, reporter)) is not None:
        context += feedback.run_context(stored)
    if report.conversation:
        found = deps.reads.conversation(report.conversation, reporter)
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
