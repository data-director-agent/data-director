"""The admin service's pages (docs/guide/operations/admin.md).

Every route is a GET and changes nothing. There is no sign-in: the service listens on loopback
only (`dd_admin.cli`), and `LoopbackHosts` refuses a request whose Host header is not a loopback
name, so a web page the operator has open cannot reach it through their SSH tunnel by DNS
rebinding.
"""

from __future__ import annotations

import ipaddress
import json
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import jinja2
from starlette.applications import Starlette
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from dd_admin import agents as agents_module
from dd_admin import config_files, operations, spend, usage
from dd_admin.cache import Cached
from dd_admin.settings import AdminSettings
from dd_admin.system import System
from dd_harness.projects import ProjectError
from dd_harness.remote import ClientFactory, default_client
from dd_harness.settings import project_storage, redact_location, run_storage
from dd_harness.storage import ProjectStorage, RunStorage

HERE = Path(__file__).parent
PAGE_SIZE = 50
STATUSES = ("succeeded", "abstained", "referred", "failed", "suspended")
LOOPBACK_NAMES = frozenset({"localhost"})

CSP = (
    "default-src 'none'; style-src 'self'; img-src 'self' data:; "
    "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)


def is_loopback_host(host_header: str) -> bool:
    """Whether a Host header names this machine: `localhost` or a loopback address, with or
    without a port."""
    host = host_header.strip().lower()
    if host.startswith("["):
        host = host[1 : host.find("]")] if "]" in host else ""
    elif host.count(":") == 1:
        host = host.split(":", 1)[0]
    if host in LOOPBACK_NAMES or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class LoopbackHosts:
    """Refuse a request whose Host is not a loopback name, and add the headers every page
    carries: no caching, no framing, a content security policy that admits no script."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if not is_loopback_host(Headers(scope=scope).get("host", "")):
            response = PlainTextResponse(
                "The admin service answers only on loopback, through an SSH tunnel.",
                status_code=421,
            )
            await response(scope, receive, send)
            return

        async def with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                headers.extend(
                    [
                        (b"cache-control", b"no-store"),
                        (b"x-frame-options", b"DENY"),
                        (b"x-content-type-options", b"nosniff"),
                        (b"referrer-policy", b"no-referrer"),
                        (b"content-security-policy", CSP.encode()),
                    ]
                )
            await send(message)

        await self.app(scope, receive, with_headers)


@dataclass
class Admin:
    """What the pages read, each kept for a short while (`Cached`)."""

    settings: AdminSettings
    system: System = field(default_factory=System)
    client_factory: ClientFactory = default_client
    runs: RunStorage | None = None
    projects: ProjectStorage | None = None
    store_errors: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.usage = Cached(lambda: usage.count(self.runs, self.projects), ttl_s=60)
        self.doctor = Cached(lambda: operations.run_doctor(self.settings, self.system), ttl_s=60)
        self.agents = Cached(
            lambda: agents_module.probe(self.settings.agents_config, self.client_factory),
            ttl_s=30,
        )
        # The gateway's spend logs change by the call but are costly to read in full.
        self.gateway = Cached(lambda: spend.read_gateway(self.settings, self.system), ttl_s=300)
        self.about = Cached(
            lambda: self.system.get_json(self.settings.app_url.rstrip("/") + "/api/about"),
            ttl_s=30,
        )

    @classmethod
    def open(
        cls,
        settings: AdminSettings,
        system: System | None = None,
        client_factory: ClientFactory = default_client,
    ) -> Admin:
        """Open the stores the settings name. One that cannot be opened is reported on every
        page rather than stopping the service, which is what an operator needs to see."""
        admin = cls(settings, system or System(), client_factory)
        if settings.runs is not None:
            try:
                admin.runs = run_storage(settings.runs)
            except Exception as exc:  # noqa: BLE001 - shown on the page
                admin.store_errors.append(f"DD_RUNS_DIR cannot be opened: {exc}")
        if settings.projects is not None:
            try:
                admin.projects = project_storage(settings.projects)
            except Exception as exc:  # noqa: BLE001 - shown on the page
                admin.store_errors.append(f"DD_PROJECTS_DIR cannot be opened: {exc}")
        return admin

    def budget(self, gateway: spend.GatewaySpend) -> spend.Budget:
        return spend.Budget(
            self.settings.monthly_budget, gateway.month_to_date if gateway.answered else None
        )

    def units(self) -> list[str]:
        return operations.unit_names(agents_module.configured_names(self.settings.agents_config))


# --- Template helpers ----------------------------------------------------------------------------


def _when(value: object) -> str:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return str(value)
    if not isinstance(value, datetime):
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def _ago(value: object, now: datetime | None = None) -> str:
    if not isinstance(value, datetime):
        return "—"
    seconds = ((now or datetime.now(UTC)) - value).total_seconds()
    for unit, size in (("d", 86400), ("h", 3600), ("min", 60)):
        if seconds >= size:
            return f"{int(seconds // size)} {unit} ago"
    return "just now"


def _short(value: object, n: int = 8) -> str:
    text = str(value or "")
    return text if len(text) <= n else text[:n] + "…"


def _pretty(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True, default=str, ensure_ascii=False)


def _number(value: object) -> str:
    return f"{value:,}" if isinstance(value, int) else str(value)


def _money(value: object) -> str:
    """An amount in the gateway's currency (LiteLLM prices in US dollars)."""
    if not isinstance(value, int | float):
        return "—"
    if 0 < value < 0.01:
        return "<$0.01"
    return f"${value:,.2f}"


def _percent(value: object) -> str:
    return f"{value:.0%}" if isinstance(value, int | float) else "—"


def _orcid(principal_id: object) -> str | None:
    """The iD if `principal_id` is an ORCID iD URI, for a short label."""
    text = str(principal_id or "")
    for prefix in ("https://orcid.org/", "https://sandbox.orcid.org/"):
        if text.startswith(prefix):
            return text.removeprefix(prefix)
    return None


def build_templates() -> Jinja2Templates:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(HERE / "templates"),
        autoescape=True,
        undefined=jinja2.ChainableUndefined,
    )
    templates = Jinja2Templates(env=env)
    env.filters.update(
        when=_when,
        ago=_ago,
        short=_short,
        pretty=_pretty,
        number=_number,
        orcid=_orcid,
        money=_money,
        percent=_percent,
    )
    env.globals.update(statuses=STATUSES)
    return templates


# --- Pages ---------------------------------------------------------------------------------------


def build_app(admin: Admin) -> Starlette:
    templates = build_templates()

    def page(request: Request, name: str, **context: Any) -> Response:
        fresh = request.query_params.get("fresh") == "1"
        kept = [(k, v) for k, v in request.query_params.multi_items() if k != "fresh"]
        refresh_url = f"{request.url.path}?{urlencode([*kept, ('fresh', '1')])}"
        return templates.TemplateResponse(
            request,
            name,
            {
                "nav": request.url.path,
                "store_errors": admin.store_errors,
                "fresh": fresh,
                "refresh_url": refresh_url,
                "settings": admin.settings,
                "now": datetime.now(UTC),
                **context,
            },
        )

    def fresh(request: Request) -> bool:
        return request.query_params.get("fresh") == "1"

    def gateway(request: Request) -> spend.GatewaySpend:
        return admin.gateway.get(fresh=fresh(request))

    def overview(request: Request) -> Response:
        found = admin.usage.get(fresh=fresh(request))
        spent = gateway(request)
        return page(
            request,
            "overview.html",
            usage=found,
            doctor=admin.doctor.get(fresh=fresh(request)),
            agents=admin.agents.get(fresh=fresh(request)),
            about=admin.about.get(fresh=fresh(request)),
            peak=max([n for _, n in found.per_day] + [1]),
            gateway=spent,
            budget=admin.budget(spent),
            tokens_30=found.tokens_since(30),
        )

    def spend_page(request: Request) -> Response:
        found = admin.usage.get(fresh=fresh(request))
        spent = gateway(request)
        return page(
            request,
            "spend.html",
            usage=found,
            gateway=spent,
            budget=admin.budget(spent),
            estimate=spend.estimate(found, spent.prices),
            tokens_30=found.tokens_since(30),
            peak=max([n for _, n in spent.per_day] + [0.01]),
        )

    def operations_page(request: Request) -> Response:
        units = admin.units()
        return page(
            request,
            "operations.html",
            doctor=admin.doctor.get(fresh=fresh(request)),
            releases=operations.releases(admin.settings, admin.system),
            units=operations.unit_states(units, admin.system) if admin.settings.systemd else None,
            about=admin.about.get(fresh=fresh(request)),
        )

    def journal_page(request: Request) -> Response:
        unit = request.path_params["unit"]
        # Only a unit this deployment has: the name never reaches journalctl otherwise.
        if unit not in admin.units():
            raise HTTPException(404, f"{unit} is not one of this deployment's units")
        if not admin.settings.systemd:
            raise HTTPException(404, "DD_ADMIN_SYSTEMD is not set, so journals are not read")
        return page(request, "journal.html", unit=unit, text=operations.journal(unit, admin.system))

    def agents_page(request: Request) -> Response:
        units = None
        found = admin.agents.get(fresh=fresh(request))
        if admin.settings.systemd:
            states = operations.unit_states(
                [operations.agent_unit(a.name) for a in found.agents], admin.system
            )
            units = {s.get("Id", ""): s for s in states}
        return page(request, "agents.html", agents=found, units=units)

    def agent_page(request: Request) -> Response:
        found = admin.agents.get(fresh=fresh(request)).get(request.path_params["name"])
        if found is None:
            raise HTTPException(404, "no agent of that name in agents.yaml")
        return page(request, "agent.html", agent=found, unit=operations.agent_unit(found.name))

    def people_page(request: Request) -> Response:
        return page(request, "people.html", usage=admin.usage.get(fresh=fresh(request)))

    def person_page(request: Request) -> Response:
        found = admin.usage.get(fresh=fresh(request))
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
        return page(
            request,
            "person.html",
            cost=spend.cost_of_runs(runs, gateway(request).prices),
            prices=bool(gateway(request).prices),
            person=person,
            runs=runs[:PAGE_SIZE],
            run_count=len(runs),
            projects=projects,
        )

    def runs_page(request: Request) -> Response:
        found = admin.usage.get(fresh=fresh(request))
        filters = {
            key: request.query_params.get(key, "").strip()
            for key in ("agent", "status", "principal", "project", "conversation")
        }
        fields = {
            "agent": "agent_id",
            "status": "status",
            "principal": "principal_id",
            "project": "project_id",
            "conversation": "conversation_id",
        }
        rows = [
            r for r in found.runs if all(not v or r[fields[k]] == v for k, v in filters.items())
        ]
        pages = max(1, math.ceil(len(rows) / PAGE_SIZE))
        try:
            number = min(max(1, int(request.query_params.get("page", "1"))), pages)
        except ValueError:
            number = 1
        active = {k: v for k, v in filters.items() if v}

        def link(n: int) -> str:
            return "/runs?" + urlencode({**active, "page": n})

        return page(
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

    def run_page(request: Request) -> Response:
        if admin.runs is None:
            raise HTTPException(404, "no run store is configured")
        invocation_id = request.path_params["invocation_id"]
        envelope = admin.runs.get(invocation_id)
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
        return page(
            request,
            "run.html",
            cost=spend.cost_of(row["calls"], gateway(request).prices),
            calls=row["calls"],
            prices=bool(gateway(request).prices),
            envelope=envelope,
            request_doc=admin.runs.get_request(invocation_id),
            where=admin.runs.where(invocation_id),
            children=children,
        )

    def projects_page(request: Request) -> Response:
        return page(request, "projects.html", usage=admin.usage.get(fresh=fresh(request)))

    def project_page(request: Request) -> Response:
        if admin.projects is None:
            raise HTTPException(404, "no project store is configured")
        project_id = request.path_params["project_id"]
        try:
            summary = admin.projects.summary(project_id)
            events = admin.projects.events(project_id)
        except ProjectError:
            raise HTTPException(404, "no project with that identifier") from None
        runs = [r for r in admin.usage.get().runs if r["project_id"] == project_id]
        return page(
            request,
            "project.html",
            cost=spend.cost_of_runs(runs, gateway(request).prices),
            prices=bool(gateway(request).prices),
            summary=summary,
            events=events,
            runs=runs[:PAGE_SIZE],
            run_count=len(runs),
        )

    def config_page(request: Request) -> Response:
        return page(
            request,
            "config.html",
            files=config_files.read(admin.settings.etc, admin.system),
            about=admin.about.get(fresh=fresh(request)),
            runs_location=_location(admin.settings.runs),
            projects_location=_location(admin.settings.projects),
        )

    def feedback_page(request: Request) -> Response:
        repo = admin.settings.feedback_repo
        query = urlencode({"q": 'is:issue label:"area: app"', "sort": "created-desc"})
        return page(
            request,
            "feedback.html",
            repo=repo,
            issues_url=f"https://github.com/{repo}/issues?{query}",
        )

    def healthz(_: Request) -> Response:
        return PlainTextResponse("ok")

    async def not_found(request: Request, exc: Exception) -> Response:
        detail = exc.detail if isinstance(exc, HTTPException) else "Not found"
        status = exc.status_code if isinstance(exc, HTTPException) else 404
        response = page(request, "error.html", detail=detail, status=status)
        response.status_code = status
        return response

    routes = [
        Route("/", overview, methods=["GET"]),
        Route("/operations", operations_page, methods=["GET"]),
        Route("/operations/journal/{unit}", journal_page, methods=["GET"]),
        Route("/agents", agents_page, methods=["GET"]),
        Route("/agents/{name}", agent_page, methods=["GET"]),
        Route("/people", people_page, methods=["GET"]),
        Route("/person", person_page, methods=["GET"]),
        Route("/runs", runs_page, methods=["GET"]),
        Route("/runs/{invocation_id}", run_page, methods=["GET"]),
        Route("/spend", spend_page, methods=["GET"]),
        Route("/projects", projects_page, methods=["GET"]),
        Route("/projects/{project_id}", project_page, methods=["GET"]),
        Route("/config", config_page, methods=["GET"]),
        Route("/feedback", feedback_page, methods=["GET"]),
        Route("/healthz", healthz, methods=["GET"]),
        Mount("/static", StaticFiles(directory=str(HERE / "static")), name="static"),
    ]
    app = Starlette(routes=routes, exception_handlers={404: not_found})
    app.add_middleware(LoopbackHosts)
    return app


def _location(location: object) -> str | None:
    if location is None:
        return None
    return redact_location(str(location))
