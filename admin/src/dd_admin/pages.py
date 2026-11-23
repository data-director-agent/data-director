"""The admin service's route handlers, one method per page (docs/guide/operations/admin.md).

Every handler is a GET and changes nothing. `dd_admin.app.build_app` mounts them behind
`LoopbackHosts`.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import BaseRoute, Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from dd_admin import config_files, operations, spend, usage
from dd_harness.projects import ProjectError
from dd_harness.settings import redact_location

if TYPE_CHECKING:
    from dd_admin.reader import Admin

PAGE_SIZE = 50

# The run list's filters, each by the run row field it matches.
RUN_FILTERS = {
    "agent": "agent_id",
    "status": "status",
    "principal": "principal_id",
    "project": "project_id",
    "conversation": "conversation_id",
}


class Pages:
    """The pages of one `Admin`, rendered with `templates`."""

    def __init__(self, admin: Admin, templates: Jinja2Templates) -> None:
        self.admin = admin
        self.templates = templates

    def routes(self, static: Path) -> list[BaseRoute]:
        """Every page's route, and the static files from `static`."""
        pages = {
            "/": self.overview,
            "/operations": self.operations_page,
            "/operations/journal/{unit}": self.journal_page,
            "/agents": self.agents_page,
            "/agents/{name}": self.agent_page,
            "/people": self.people_page,
            "/person": self.person_page,
            "/runs": self.runs_page,
            "/runs/{invocation_id}": self.run_page,
            "/spend": self.spend_page,
            "/projects": self.projects_page,
            "/projects/{project_id}": self.project_page,
            "/config": self.config_page,
            "/feedback": self.feedback_page,
            "/healthz": self.healthz,
        }
        routes: list[BaseRoute] = [
            Route(path, handler, methods=["GET"]) for path, handler in pages.items()
        ]
        routes.append(Mount("/static", StaticFiles(directory=str(static)), name="static"))
        return routes

    def page(self, request: Request, name: str, **context: Any) -> Response:
        fresh = request.query_params.get("fresh") == "1"
        kept = [(k, v) for k, v in request.query_params.multi_items() if k != "fresh"]
        refresh_url = f"{request.url.path}?{urlencode([*kept, ('fresh', '1')])}"
        return self.templates.TemplateResponse(
            request,
            name,
            {
                "nav": request.url.path,
                "store_errors": self.admin.store_errors,
                "fresh": fresh,
                "refresh_url": refresh_url,
                "settings": self.admin.settings,
                "now": datetime.now(UTC),
                **context,
            },
        )

    def gateway(self, request: Request) -> spend.GatewaySpend:
        return self.admin.gateway.get(fresh=_fresh(request))

    def overview(self, request: Request) -> Response:
        admin = self.admin
        found = admin.usage.get(fresh=_fresh(request))
        spent = self.gateway(request)
        return self.page(
            request,
            "overview.html",
            usage=found,
            doctor=admin.doctor.get(fresh=_fresh(request)),
            agents=admin.agents.get(fresh=_fresh(request)),
            about=admin.about.get(fresh=_fresh(request)),
            peak=max([n for _, n in found.per_day] + [1]),
            gateway=spent,
            budget=admin.budget(spent),
            tokens_30=found.tokens_since(30),
        )

    def spend_page(self, request: Request) -> Response:
        found = self.admin.usage.get(fresh=_fresh(request))
        spent = self.gateway(request)
        return self.page(
            request,
            "spend.html",
            usage=found,
            gateway=spent,
            budget=self.admin.budget(spent),
            estimate=spend.estimate(found, spent.prices),
            tokens_30=found.tokens_since(30),
            peak=max([n for _, n in spent.per_day] + [0.01]),
        )

    def operations_page(self, request: Request) -> Response:
        admin = self.admin
        units = admin.units()
        return self.page(
            request,
            "operations.html",
            doctor=admin.doctor.get(fresh=_fresh(request)),
            releases=operations.releases(admin.settings, admin.system),
            units=operations.unit_states(units, admin.system) if admin.settings.systemd else None,
            about=admin.about.get(fresh=_fresh(request)),
        )

    def journal_page(self, request: Request) -> Response:
        admin = self.admin
        unit = request.path_params["unit"]
        # Only a unit this deployment has: the name never reaches journalctl otherwise.
        if unit not in admin.units():
            raise HTTPException(404, f"{unit} is not one of this deployment's units")
        if not admin.settings.systemd:
            raise HTTPException(404, "DD_ADMIN_SYSTEMD is not set, so journals are not read")
        return self.page(
            request, "journal.html", unit=unit, text=operations.journal(unit, admin.system)
        )

    def agents_page(self, request: Request) -> Response:
        admin = self.admin
        units = None
        found = admin.agents.get(fresh=_fresh(request))
        if admin.settings.systemd:
            states = operations.unit_states(
                [operations.agent_unit(a.name) for a in found.agents], admin.system
            )
            units = {s.get("Id", ""): s for s in states}
        return self.page(request, "agents.html", agents=found, units=units)

    def agent_page(self, request: Request) -> Response:
        found = self.admin.agents.get(fresh=_fresh(request)).get(request.path_params["name"])
        if found is None:
            raise HTTPException(404, "no agent of that name in agents.yaml")
        return self.page(request, "agent.html", agent=found, unit=operations.agent_unit(found.name))

    def people_page(self, request: Request) -> Response:
        return self.page(request, "people.html", usage=self.admin.usage.get(fresh=_fresh(request)))

    def person_page(self, request: Request) -> Response:
        found = self.admin.usage.get(fresh=_fresh(request))
        principal_id = request.query_params.get("id", "")
        person = found.person(principal_id)
        if person is None:
            raise HTTPException(404, "nobody with that identifier is in the stores")
        runs = [r for r in found.runs if r["principal_id"] == principal_id]
        projects = [
            p
            for p in found.projects
            if (p.get("created_by") or {}).get("principal_id") == principal_id
        ]
        return self.page(
            request,
            "person.html",
            cost=spend.cost_of_runs(runs, self.gateway(request).prices),
            prices=bool(self.gateway(request).prices),
            person=person,
            runs=runs[:PAGE_SIZE],
            run_count=len(runs),
            projects=projects,
        )

    def runs_page(self, request: Request) -> Response:
        found = self.admin.usage.get(fresh=_fresh(request))
        filters = {key: request.query_params.get(key, "").strip() for key in RUN_FILTERS}
        rows = [
            r
            for r in found.runs
            if all(not v or r[RUN_FILTERS[k]] == v for k, v in filters.items())
        ]
        pages = max(1, math.ceil(len(rows) / PAGE_SIZE))
        try:
            number = min(max(1, int(request.query_params.get("page", "1"))), pages)
        except ValueError:
            number = 1
        active = {k: v for k, v in filters.items() if v}

        def link(n: int) -> str:
            return "/runs?" + urlencode({**active, "page": n})

        return self.page(
            request,
            "runs.html",
            runs=rows[(number - 1) * PAGE_SIZE : number * PAGE_SIZE],
            total=len(rows),
            filters=filters,
            active=active,
            agent_ids=sorted(found.by_agent),
            number=number,
            pages=pages,
            previous=link(number - 1) if number > 1 else None,
            next=link(number + 1) if number < pages else None,
        )

    def run_page(self, request: Request) -> Response:
        runs = self.admin.runs
        if runs is None:
            raise HTTPException(404, "no run store is configured")
        invocation_id = request.path_params["invocation_id"]
        envelope = runs.get(invocation_id)
        if envelope is None:
            raise HTTPException(404, "no run with that identifier")
        row = usage.run_row(envelope)
        children = [
            {
                "invocation_id": d.get("delegated_invocation_id"),
                "agent_id": d.get("delegated_agent_id"),
                "status": d.get("delegated_status"),
            }
            for d in envelope.get("delegations") or []
            if isinstance(d, dict)
        ]
        return self.page(
            request,
            "run.html",
            cost=spend.cost_of(row["calls"], self.gateway(request).prices),
            calls=row["calls"],
            prices=bool(self.gateway(request).prices),
            envelope=envelope,
            request_doc=runs.get_request(invocation_id),
            where=runs.where(invocation_id),
            children=children,
        )

    def projects_page(self, request: Request) -> Response:
        return self.page(
            request, "projects.html", usage=self.admin.usage.get(fresh=_fresh(request))
        )

    def project_page(self, request: Request) -> Response:
        projects = self.admin.projects
        if projects is None:
            raise HTTPException(404, "no project store is configured")
        project_id = request.path_params["project_id"]
        try:
            summary = projects.summary(project_id)
            events = projects.events(project_id)
        except ProjectError:
            raise HTTPException(404, "no project with that identifier") from None
        runs = [r for r in self.admin.usage.get().runs if r["project_id"] == project_id]
        return self.page(
            request,
            "project.html",
            cost=spend.cost_of_runs(runs, self.gateway(request).prices),
            prices=bool(self.gateway(request).prices),
            summary=summary,
            events=events,
            runs=runs[:PAGE_SIZE],
            run_count=len(runs),
        )

    def config_page(self, request: Request) -> Response:
        settings = self.admin.settings
        return self.page(
            request,
            "config.html",
            files=config_files.read(settings.etc, self.admin.system),
            about=self.admin.about.get(fresh=_fresh(request)),
            runs_location=_location(settings.runs),
            projects_location=_location(settings.projects),
        )

    def feedback_page(self, request: Request) -> Response:
        repo = self.admin.settings.feedback_repo
        query = urlencode({"q": 'is:issue label:"source: feedback form"', "sort": "created-desc"})
        return self.page(
            request,
            "feedback.html",
            repo=repo,
            issues_url=f"https://github.com/{repo}/issues?{query}",
        )

    def healthz(self, _: Request) -> Response:
        return PlainTextResponse("ok")

    async def not_found(self, request: Request, exc: Exception) -> Response:
        detail = exc.detail if isinstance(exc, HTTPException) else "Not found"
        status = exc.status_code if isinstance(exc, HTTPException) else 404
        response = self.page(request, "error.html", detail=detail, status=status)
        response.status_code = status
        return response


def _fresh(request: Request) -> bool:
    return request.query_params.get("fresh") == "1"


def _location(location: object) -> str | None:
    if location is None:
        return None
    return redact_location(str(location))
