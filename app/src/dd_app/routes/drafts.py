"""Depositing a draft through the repository's API, after a person approves it
(docs/specs/deposit.md, Depositing through an API).

`GET /api/projects/{id}/deposits` says whether the repository chosen can be deposited to through
its API here, and lists each deposit approved with its outcome. `POST` on it, with a package's
`digest`, records the signed-in person's approval and asks the deposit broker for a draft, made
with that person's own repository account. It answers `201` with the deposit, whether a draft was
made or the attempt failed, which is an outcome too (invariant 15), and `409` when nothing could be
approved. Approving is a decision, so it needs the role that decides on documents.
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import MISSING, ConfigDict, Field
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from dd_app.project_service import RepositoriesUnavailableError
from dd_app.routes.common import (
    Deps,
    ProblemDetails,
    RequestBody,
    ResponseBody,
    in_project,
    parse_body,
    respond,
)
from dd_harness.deposit_api import DepositRefusedError
from dd_harness.project_access import Action
from dd_harness.projects import DepositInProgressError
from dd_sdk.contract.models import Principal
from dd_sdk.contract.problem import PROBLEM_BASE


class DepositConnection(ResponseBody):
    """How the project's repository is deposited to: through its API here, when `available`, or
    by hand, and why not through the API (`unavailable`, a reason code)."""

    repository_name: str
    transport: str | None
    """The transport its override names, such as zenodo; null when it names none."""
    base_url: str | None
    sandbox: bool
    """Whether the API is the platform's test installation, whose items and DOIs are not real."""
    available: bool
    unavailable: str | None


class DepositShown(ResponseBody):
    """One deposit a person approved, and its outcome."""

    approved_at: str
    approved_by: str | None
    digest: str
    """The RO-Crate package deposited."""
    repository_name: str
    transport: str
    sandbox: bool
    state: Literal["pending", "recorded", "failed"]
    draft_url: str | MISSING = MISSING
    """Where the draft is in the repository, once it was made."""
    deposit_id: str | MISSING = MISSING
    doi: str | MISSING = MISSING
    reason: str | MISSING = MISSING
    """Why it failed, as a reason code."""
    status: int | MISSING = MISSING
    unplaced: list[str] | MISSING = MISSING
    """The metadata record's properties the repository's form had no place for."""


class Deposits(ResponseBody):
    """Whether the project can be deposited to through an API here, and each deposit approved."""

    connection: DepositConnection | None
    """Null when no repository has been chosen."""
    deposits: list[DepositShown]


class DepositRefusedProblem(ProblemDetails):
    """Nothing was approved or sent: `refusal` says why, as a code; `draft_url` names the
    earlier draft when the package was already deposited."""

    model_config = ConfigDict(extra="forbid")

    refusal: str
    draft_url: str | MISSING = MISSING


class StartDeposit(RequestBody):
    """The package a person approves for deposit, by its digest."""

    refusal: ClassVar[str] = "`digest` is the SHA-256 of a package the project built."

    digest: str = Field(pattern=r"^[0-9a-f]{64}$")


def routes(deps: Deps) -> list[Route]:
    deposits = "/api/projects/{project_id}/deposits"
    return [
        Route(deposits, in_project(deps, Action.READ, get_deposits), methods=["GET"]),
        Route(deposits, in_project(deps, Action.DECIDE, start_deposit), methods=["POST"]),
    ]


def _connection(found: Any) -> dict[str, Any] | None:
    if found is None:
        return None
    connector = found.connector
    return {
        "repository_name": found.repository_name,
        "transport": connector.transport if connector else None,
        "base_url": connector.base_url if connector else None,
        "sandbox": bool(connector and connector.sandbox),
        "available": found.available,
        "unavailable": found.unavailable.value if found.unavailable else None,
    }


async def get_deposits(request: Request, _: Principal, deps: Deps) -> Response:
    project_id = request.path_params["project_id"]
    service = deps.projects.deposit
    found = await run_in_threadpool(service.connection, project_id)
    shown = await run_in_threadpool(service.deposits, project_id)
    return respond(Deposits, {"connection": _connection(found), "deposits": shown})


async def start_deposit(request: Request, acting_for: Principal, deps: Deps) -> Response:
    """The signed-in person's approval of a deposit, and the draft it made or the failure
    (`deposit_api.approve_and_deposit`)."""
    project_id = request.path_params["project_id"]
    body = await parse_body(request, StartDeposit, "Data Director could not start this deposit")
    if isinstance(body, Response):
        return body
    try:
        shown = await run_in_threadpool(
            lambda: deps.projects.deposit.deposit(
                project_id,
                body.digest,
                acted_for=acting_for,
                caused_by=f"POST {request.url.path}",
            )
        )
    except (DepositRefusedError, RepositoriesUnavailableError) as exc:
        refusal = exc.refusal.value if isinstance(exc, DepositRefusedError) else "by-hand"
        return _deposit_refused("deposit-refused", str(exc), refusal)
    except DepositInProgressError as exc:
        return _deposit_refused(
            "already-deposited", str(exc), "already-deposited", exc.earlier.get("draft_url")
        )
    return respond(DepositShown, shown, status_code=201)


def _deposit_refused(
    slug: str, detail: str, refusal: str, draft_url: str | None = None
) -> Response:
    return respond(
        DepositRefusedProblem,
        {
            "type": PROBLEM_BASE + slug,
            "title": "Nothing was deposited",
            "status": 409,
            "detail": detail,
            "refusal": refusal,
            **({"draft_url": draft_url} if draft_url else {}),
        },
        status_code=409,
        media_type="application/problem+json",
    )
