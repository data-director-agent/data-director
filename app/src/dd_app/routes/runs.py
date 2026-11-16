"""The agents and their runs.

`GET /api/agents` is what the shell draws its capabilities panel from. `POST /api/runs` runs an
agent through the conductor and answers when the run has ended, with its envelope and the
checks' reports; `GET /api/runs` and `GET /api/runs/{id}` read the run store. The run endpoint is
a stopgap until runs stream over AG-UI (#69). Each person sees only their own runs (#153);
someone else's is answered with 404, as one that does not exist.
"""

from __future__ import annotations

from typing import Any, ClassVar

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from dd_app.routes.common import Deps, RequestBody, parse_body, problem, refused, signed_in
from dd_harness.conductor import UnknownAgent
from dd_harness.identity import IdentityError
from dd_harness.policy import PolicyError
from dd_harness.transport.paging import PagingError, page_params, page_response
from dd_sdk.contract.models import Principal
from dd_sdk.contract.validate import ContractViolation

RUN_REFUSED = "Data Director could not start this run"
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


def routes(deps: Deps) -> list[Route]:
    return [
        Route("/api/agents", signed_in(deps, agents), methods=["GET"]),
        Route("/api/runs", signed_in(deps, start_run), methods=["POST"]),
        Route("/api/runs", signed_in(deps, list_runs), methods=["GET"]),
        Route("/api/runs/{invocation_id}", signed_in(deps, get_run), methods=["GET"]),
    ]


async def agents(request: Request, acting_for: Principal, deps: Deps) -> Response:
    # Off the event loop: refreshing the registry reads agent cards, which blocks.
    return JSONResponse(await run_in_threadpool(deps.governance.agents, acting_for))


async def start_run(request: Request, acting_for: Principal, deps: Deps) -> Response:
    body = await parse_body(request, StartRun, RUN_REFUSED)
    if isinstance(body, Response):
        return body
    try:
        return JSONResponse(await deps.governance.run(body.agent_id, body.input, acting_for))
    except REFUSED_BEFORE_RUN as exc:
        return refused(str(exc))


async def list_runs(request: Request, reader: Principal, deps: Deps) -> Response:
    try:
        paging = page_params(request)
    except PagingError as exc:
        return refused(str(exc), "Data Director could not list the runs")
    page = await run_in_threadpool(lambda: deps.governance.runs(reader, **paging))
    return page_response(request, page)


async def get_run(request: Request, reader: Principal, deps: Deps) -> Response:
    invocation_id = request.path_params["invocation_id"]
    run = await run_in_threadpool(deps.governance.stored_run, invocation_id, reader)
    if run is None:
        return problem(404, "run-not-found", "No such run", f"No run {invocation_id!r}.")
    return JSONResponse(run)
