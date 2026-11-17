"""The admin service's pages (docs/guide/operations/admin.md).

Every route is a GET and changes nothing; the handlers are in `dd_admin.pages`. There is no
sign-in: the service listens on loopback only (`dd_admin.cli`), and `LoopbackHosts` refuses a
request whose Host header is not a loopback name, so a web page the operator has open cannot reach
it through their SSH tunnel by DNS rebinding.
"""

from __future__ import annotations

import ipaddress
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import jinja2
from starlette.applications import Starlette
from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse
from starlette.templating import Jinja2Templates
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from dd_admin import agents as agents_module
from dd_admin import operations, spend, usage
from dd_admin.cache import Cached
from dd_admin.pages import Pages
from dd_admin.settings import AdminSettings
from dd_admin.system import System
from dd_harness.remote import ClientFactory, default_client
from dd_harness.settings import project_storage, run_storage
from dd_harness.storage import ProjectStorage, RunStorage

HERE = Path(__file__).parent
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
    pages = Pages(admin, build_templates())
    app = Starlette(routes=pages.routes(HERE / "static"), exception_handlers={404: pages.not_found})
    app.add_middleware(LoopbackHosts)
    return app
