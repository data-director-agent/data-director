"""The agents and their runs.

`GET /api/agents` is what the shell draws its capabilities panel from. `POST /api/runs` runs an
agent through the conductor and answers when the run has ended, with its envelope and the
checks' reports; `GET /api/runs` and `GET /api/runs/{id}` read the run store. The run endpoint is
a stopgap until runs stream over AG-UI (#69). Each person sees only their own runs (#153);
someone else's is answered with 404, as one that does not exist.
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from dd_app import contract_shapes as contract
from dd_app.routes.common import (
    RUN_REFUSED,
    Deps,
    RequestBody,
    ResponseBody,
    parse_body,
    problem,
    refused,
    respond,
    respond_page,
    signed_in,
)
from dd_app.routes.session import PrincipalSummary
from dd_harness.conductor import UnknownAgent
from dd_harness.identity import IdentityError
from dd_harness.policy import PolicyError
from dd_harness.transport.paging import PagingError, page_params
from dd_sdk.contract.models import Principal
from dd_sdk.contract.validate import ContractViolation

# Refused before a run or turn began, so nothing was stored (as `workbench/transport/agui.py`).
REFUSED_BEFORE_RUN = (ContractViolation, ValueError, UnknownAgent, PolicyError, IdentityError)


class StartRun(RequestBody):
    """`POST /api/runs`: the agent to run and its input."""

    refusal: ClassVar[str] = "The body must be an object with `agent_id` and `input`."
    field_refusals: ClassVar[dict[str, str]] = dict.fromkeys(
        ("agent_id", "input"),
        "The body must name `agent_id` (a string) and give `input` (an object).",
    )

    agent_id: str
    input: dict[str, Any]


type OutcomeStatus = Literal["succeeded", "abstained", "referred", "failed", "suspended"]


class Derivation(ResponseBody):
    """How an agent derives one field of its payload."""

    how: Literal["template", "model", "lexical", "registry"]
    recorded_in: str | None


class AgentSetting(ResponseBody):
    """An option a deployment's profile may set for an agent."""

    choices: list[str]
    default: str
    description: str


class RawManifestEntry(ResponseBody):
    """An agent's manifest, as its card declares it (`dd_sdk.agent.describe`), beside what this
    deployment's profile assigns it."""

    agent_id: str
    version: str
    description: str
    action_class: str
    accepts: list[str]
    grounding_mode: Literal["retrieval", "input_only", "none", "delegation"]
    payload: str | None
    derivations: dict[str, Derivation]
    contract_version: str
    models: list[contract.RawModelUse]
    serves: list[str]
    """The process flow step ids it serves (docs/specs/orchestration.md)."""
    title: str
    """The persona's name as a researcher sees it; empty for none."""
    icon: str
    """The persona's icon, one emoji; empty for none."""
    settings: dict[str, AgentSetting]
    skills: list[contract.RawSkillUse]
    tools: list[contract.RawToolUse]
    schemas: dict[str, contract.RawSchemaEntry]
    assigned_action_class: str | None
    """The action class the profile assigns it; null if the profile does not list it, and the
    gate refuses it."""
    requires_approval: bool


class AgentsProfile(ResponseBody):
    ref: str
    digest: str
    orchestrator: str | None
    """The agent the profile names for the conversation; null when it names none."""
    attached_documents: Literal["allowed", "refused"]
    """Whether the profile lets people attach documents to a turn."""


class RawAgentsResponse(ResponseBody):
    """The agents the shell's capabilities panel is drawn from (`GET /api/agents`)."""

    agents: list[RawManifestEntry]
    unavailable: dict[str, str]
    """The configured agents it could not reach, by name, with why."""
    incompatible: dict[str, str]
    """The configured agents built against another contract, by name, with both versions."""
    profile: AgentsProfile
    acting_for: PrincipalSummary


class CheckReport(ResponseBody):
    """A check's stored summary."""

    passed: bool
    summary: str


class Checks(ResponseBody):
    """What the grounding linter and the source check reported; null where a run has none."""

    grounding: CheckReport | None
    sources: CheckReport | None


class RunResult(ResponseBody):
    """A run that has ended, as `POST /api/runs` or a conversation's turn answers it."""

    envelope: contract.Envelope
    checks: Checks


class StoredRun(RunResult):
    """A stored run with its request (`GET /api/runs/{id}`)."""

    request: contract.InvocationRequest | None


class RunRow(ResponseBody):
    """What a list of runs shows of one (`GET /api/runs`, `dd_harness.listing.run_summary`)."""

    invocation_id: str
    agent_id: str
    status: OutcomeStatus
    completed_at: str
    acting_for: str | None
    """The name of the person the run acted for; null for a run stored before runs named one."""


def routes(deps: Deps) -> list[Route]:
    return [
        Route("/api/agents", signed_in(deps, agents), methods=["GET"]),
        Route("/api/runs", signed_in(deps, start_run), methods=["POST"]),
        Route("/api/runs", signed_in(deps, list_runs), methods=["GET"]),
        Route("/api/runs/{invocation_id}", signed_in(deps, get_run), methods=["GET"]),
    ]


async def agents(request: Request, acting_for: Principal, deps: Deps) -> Response:
    # Off the event loop: refreshing the registry reads agent cards, which blocks.
    return respond(RawAgentsResponse, await run_in_threadpool(deps.governance.agents, acting_for))


async def start_run(request: Request, acting_for: Principal, deps: Deps) -> Response:
    body = await parse_body(request, StartRun, RUN_REFUSED)
    if isinstance(body, Response):
        return body
    try:
        return respond(RunResult, await deps.governance.run(body.agent_id, body.input, acting_for))
    except REFUSED_BEFORE_RUN as exc:
        return refused(str(exc))


async def list_runs(request: Request, reader: Principal, deps: Deps) -> Response:
    try:
        paging = page_params(request)
    except PagingError as exc:
        return refused(str(exc), "Data Director could not list the runs")
    page = await run_in_threadpool(lambda: deps.governance.runs(reader, **paging))
    return respond_page(request, page, RunRow)


async def get_run(request: Request, reader: Principal, deps: Deps) -> Response:
    invocation_id = request.path_params["invocation_id"]
    run = await run_in_threadpool(deps.governance.stored_run, invocation_id, reader)
    if run is None:
        return problem(404, "run-not-found", "No such run", f"No run {invocation_id!r}.")
    return respond(StoredRun, run)
