"""The organisation behind a funder a project names.

`GET /api/funders/ror/{id}` is the organisation the latest pinned ROR dump holds at a ROR
identifier, which may be given bare (`0abcdef12`) or as its `https://ror.org/` address: its names,
types, status, countries, Crossref Funder IDs and parents, the dump it was read from, and the
addresses that identify it. The page that shows a project's funder facts reads it, so that a
person can see what a name and identifier they decide on stand for. An identifier the dump does not
hold, or that is not a ROR identifier, is answered `404`; a server whose dump is not pinned and
built, `503` (docs/specs/app.md).
"""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from dd_app.project_service.funders import UnknownOrganisationError
from dd_app.routes.common import Deps, ResponseBody, problem, respond, signed_in
from dd_harness.sources import SourceConfigError
from dd_sdk.contract.models import Principal


class RorName(ResponseBody):
    """One of an organisation's names, with ROR's types for it."""

    value: str
    types: list[str]
    """ROR's types for the name: `ror_display`, `label`, `acronym` or `alias`."""
    lang: str | None


class RorLinks(ResponseBody):
    """Where the organisation is identified, as addresses to open."""

    ror: str
    """Its record at ROR."""
    crossref_funders: list[str]
    """Its Crossref Funder IDs, as doi.org addresses."""


class RorOrganisation(ResponseBody):
    """An organisation as the pinned ROR dump records it."""

    snapshot_ref: str
    """The dump it was read from."""
    ror_id: str
    """Its ROR identifier, as an address."""
    names: list[RorName]
    types: list[str]
    status: str
    country_codes: list[str]
    crossref_funder_ids: list[str]
    crossref_funder_preferred: str | None
    parents: list[str]
    """The organisations ROR names as its parents, by ROR identifier."""
    links: RorLinks


def routes(deps: Deps) -> list[Route]:
    return [
        Route("/api/funders/ror/{ror_id:path}", signed_in(deps, get_organisation), methods=["GET"])
    ]


async def get_organisation(request: Request, _: Principal, deps: Deps) -> Response:
    ror_id = request.path_params["ror_id"]
    try:
        found = await run_in_threadpool(deps.projects.funders.organisation, ror_id)
    except UnknownOrganisationError as exc:
        return problem(404, "organisation-not-found", "No such organisation", str(exc))
    except SourceConfigError as exc:
        return problem(503, "ror-unavailable", "Organisations cannot be looked up", str(exc))
    return respond(RorOrganisation, found)
