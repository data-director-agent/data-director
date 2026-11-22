"""A project's runs of one payload class, newest first (docs/specs/app.md).

`GET /api/projects/{id}/runs?payload=<class>` answers with the envelopes of the succeeded runs in
the project whose payload is of that class, turns and delegated children alike, so that the shell
can show how one kind of result has changed over the project, such as the FAIR feedback on its
metadata record (#433). The shell names the class; the server names none, and lists only runs in
conversations the person may read. `limit` caps how many come back (default 20, at most 100).
"""

from __future__ import annotations

import re

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from dd_app import contract_shapes as contract
from dd_app.routes.common import Deps, ResponseBody, in_project, refused, respond
from dd_harness.project_access import Action
from dd_sdk.contract.models import Principal

RUNS_REFUSED = "Data Director could not list the project's runs"
# A payload class is a LinkML class name.
PAYLOAD_CLASS = re.compile(r"[A-Z][A-Za-z0-9]{0,99}")
DEFAULT_LIMIT = 20
MAX_LIMIT = 100


class ProjectRuns(ResponseBody):
    """The succeeded runs in a project whose payload is of one class, newest first."""

    runs: list[contract.Envelope]


def routes(deps: Deps) -> list[Route]:
    return [
        Route(
            "/api/projects/{project_id}/runs",
            in_project(deps, Action.READ, project_runs),
            methods=["GET"],
        )
    ]


async def project_runs(request: Request, reader: Principal, deps: Deps) -> Response:
    payload_class = request.query_params.get("payload", "")
    if not PAYLOAD_CLASS.fullmatch(payload_class):
        return refused("`payload` names a payload class, such as `Document`.", RUNS_REFUSED)
    raw_limit = request.query_params.get("limit", str(DEFAULT_LIMIT))
    if not raw_limit.isdigit() or not 1 <= int(raw_limit) <= MAX_LIMIT:
        return refused(f"`limit` is a whole number from 1 to {MAX_LIMIT}.", RUNS_REFUSED)
    project_id = request.path_params["project_id"]
    runs = await run_in_threadpool(
        deps.reads.project_runs, project_id, reader, payload_class, limit=int(raw_limit)
    )
    return respond(ProjectRuns, {"runs": runs})
