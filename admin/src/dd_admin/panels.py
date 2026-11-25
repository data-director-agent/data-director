"""The LLM gateway's, the model broker's and the monitoring services' pages
(docs/guide/operations/admin.md), mounted by `dd_admin.pages.Pages.routes`. Each is a GET and
changes nothing; it names the command that does.
"""

from __future__ import annotations

from typing import Any, Protocol

from starlette.requests import Request
from starlette.responses import Response

from dd_admin import broker, config_files, operations, security_events
from dd_admin.reader import Admin

BROKER_UNIT = "data-director-model-broker.service"
BROKER_SETTINGS = "model-broker.env"


class Renders(Protocol):
    """What these pages need of `dd_admin.pages.Pages`."""

    admin: Admin

    def page(self, request: Request, name: str, **context: Any) -> Response: ...


def _fresh(request: Request) -> bool:
    return request.query_params.get("fresh") == "1"


def gateway_page(pages: Renders, request: Request) -> Response:
    found = pages.admin.gateway_state.get(fresh=_fresh(request))
    return pages.page(request, "gateway.html", state=found)


def monitoring_page(pages: Renders, request: Request) -> Response:
    return pages.page(
        request, "monitoring.html", found=pages.admin.monitoring.get(fresh=_fresh(request))
    )


def policy_page(pages: Renders, request: Request) -> Response:
    return pages.page(request, "policy.html", view=pages.admin.policy.get(fresh=_fresh(request)))


def escalations_page(pages: Renders, request: Request) -> Response:
    found = pages.admin.escalations.get(fresh=_fresh(request))
    return pages.page(request, "escalations.html", queue=found)


def security_page(pages: Renders, request: Request) -> Response:
    query = request.query_params
    try:
        days = int(query.get("days", ""))
    except ValueError:
        days = security_events.WINDOWS[0]
    if days not in security_events.WINDOWS:
        days = security_events.WINDOWS[0]
    found = pages.admin.security[days].get(fresh=_fresh(request))
    filters = {key: query.get(key, "").strip() for key in ("event", "outcome", "service")}
    return pages.page(
        request,
        "security.html",
        found=found,
        filters=filters,
        windows=security_events.WINDOWS,
        max_entries=security_events.MAX_ENTRIES,
        entries=security_events.select(found, **filters),
    )


def broker_page(pages: Renders, request: Request) -> Response:
    admin = pages.admin
    found = admin.broker.get(fresh=_fresh(request))
    agents = admin.agents.get(fresh=_fresh(request))
    states = operations.unit_states([BROKER_UNIT], admin.system) if admin.settings.systemd else []
    files = config_files.read(admin.settings.etc, admin.system) or []
    return pages.page(
        request,
        "broker.html",
        broker=found,
        coverage=broker.coverage(found, agents),
        unit=states[0] if states else None,
        unit_name=BROKER_UNIT,
        settings_file=next((f for f in files if f.name == BROKER_SETTINGS), None),
        peak=max([n for _, n in found.per_day] + [1]),
    )
