"""The monitoring services an operator uses beside the admin service
(docs/guide/operations/admin.md, "Monitoring"): where they are, whether they answer, and what
they are alerting on.

The LLM gateway's optional `monitoring` profile (`deploy/llm-gateway/`) runs Prometheus,
Alertmanager and Grafana, each bound to loopback, so a link works only through an SSH tunnel
(`docs/guide/operations/tunnels.md`) or at an address the operator publishes and names in a
setting. A service with no setting is shown at its tunnel address and is not probed. One with a
setting is asked, from this service, whether it is up: Grafana at `/api/health`, Prometheus and
Alertmanager at their alerts, which the page lists. Nothing here writes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from dd_admin.settings import AdminSettings
from dd_admin.system import System

# How many alerts of each service the page lists; it says when there are more.
MAX_ALERTS = 50

PROMETHEUS_ALERTS = "/api/v1/alerts"
ALERTMANAGER_ALERTS = "/api/v2/alerts?active=true&silenced=false&inhibited=false"
GRAFANA_HEALTH = "/api/health"


@dataclass(frozen=True)
class Alert:
    """One alert as the service that raised it reports it."""

    source: str
    name: str
    severity: str
    state: str
    since: datetime | None
    summary: str


@dataclass
class Link:
    """A service: where an operator's browser reaches it, and what is known of it.

    `state` is `up` or `down` when it was asked, and `unchecked` when it was not (no setting, or
    a service that only has a page).
    """

    key: str
    name: str
    purpose: str
    url: str
    configured: bool
    state: str = "unchecked"
    detail: str | None = None
    alerts: list[Alert] = field(default_factory=list)
    more_alerts: int = 0

    @property
    def through_tunnel(self) -> bool:
        """Shown at its default loopback address, which an operator reaches by SSH tunnel."""
        return not self.configured


@dataclass
class Monitoring:
    links: list[Link] = field(default_factory=list)

    @property
    def probed(self) -> bool:
        return any(link.state != "unchecked" for link in self.links)

    @property
    def firing(self) -> int | None:
        """Alerts firing now, from Prometheus or else Alertmanager; None if neither answered."""
        for key in ("prometheus", "alertmanager"):
            link = next((x for x in self.links if x.key == key), None)
            if link is not None and link.state == "up":
                return sum(1 for a in link.alerts if a.state == "firing") + link.more_alerts
        return None


def _when(value: object) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def prometheus_alerts(doc: object) -> list[Alert] | None:
    """The alerts in Prometheus's `/api/v1/alerts`, None if it is not that document."""
    data = doc.get("data") if isinstance(doc, dict) else None
    rows = data.get("alerts") if isinstance(data, dict) else None
    if not isinstance(rows, list) or not (isinstance(doc, dict) and doc.get("status") == "success"):
        return None
    return [
        _alert("prometheus", row, row.get("state"), row.get("activeAt"))
        for row in rows
        if isinstance(row, dict)
    ]


def alertmanager_alerts(doc: object) -> list[Alert] | None:
    """The alerts in Alertmanager's `/api/v2/alerts`, None if it is not that document."""
    if not isinstance(doc, list):
        return None
    return [
        _alert("alertmanager", row, "firing", row.get("startsAt"))
        for row in doc
        if isinstance(row, dict)
    ]


def _alert(source: str, row: dict[str, Any], state: object, since: object) -> Alert:
    labels = _mapping(row.get("labels"))
    notes = _mapping(row.get("annotations"))
    return Alert(
        source=source,
        name=_text(labels.get("alertname")) or "unnamed",
        severity=_text(labels.get("severity")),
        state=_text(state) or "firing",
        since=_when(since),
        summary=_text(notes.get("summary")) or _text(notes.get("description")),
    )


def _ask(link: Link, system: System, path: str, read: Any) -> None:
    """Ask the service at `path`; `read` turns its document into alerts (or, for a service
    without any, into an empty list), and None for a document that is not the expected one."""
    doc = system.get_json(link.url + path)
    alerts = read(doc)
    if alerts is None:
        link.state = "down"
        link.detail = f"{link.url} did not answer as {link.name} does"
        return
    link.state = "up"
    link.alerts = alerts[:MAX_ALERTS]
    link.more_alerts = max(len(alerts) - MAX_ALERTS, 0)


def _grafana(doc: object) -> list[Alert] | None:
    return [] if isinstance(doc, dict) and "database" in doc else None


def read(settings: AdminSettings, system: System) -> Monitoring:
    """The links, with each configured service asked whether it is up."""
    gateway_ui = f"{settings.litellm_url}/ui" if settings.litellm_url else None
    services: list[tuple[Link, str | None, Any]] = [
        (
            Link(
                "grafana",
                "Grafana",
                "Dashboards over Prometheus. Shipped without any: add Prometheus as a data "
                "source, as deploy/llm-gateway/README.md describes.",
                settings.grafana_url or "http://localhost:3000",
                settings.grafana_url is not None,
            ),
            GRAFANA_HEALTH,
            _grafana,
        ),
        (
            Link(
                "prometheus",
                "Prometheus",
                "Metrics the LLM gateway exports, and the alert rules over them.",
                settings.prometheus_url or "http://localhost:9090",
                settings.prometheus_url is not None,
            ),
            PROMETHEUS_ALERTS,
            prometheus_alerts,
        ),
        (
            Link(
                "alertmanager",
                "Alertmanager",
                "Where Prometheus sends its alerts. As shipped it sends them nowhere: add a "
                "receiver to deploy/llm-gateway/monitoring/alertmanager.yml.",
                settings.alertmanager_url or "http://localhost:9093",
                settings.alertmanager_url is not None,
            ),
            ALERTMANAGER_ALERTS,
            alertmanager_alerts,
        ),
    ]
    found = Monitoring()
    for link, path, parse in services:
        if link.configured and path:
            _ask(link, system, path, parse)
        found.links.append(link)
    if gateway_ui:
        found.links.append(
            Link(
                "gateway",
                "LLM gateway",
                "LiteLLM's own admin page, for the keys, teams and models the Gateway page "
                "shows read-only.",
                gateway_ui,
                configured=True,
            )
        )
    if settings.langfuse_url:
        found.links.append(
            Link(
                "langfuse",
                "Langfuse",
                "Traces of the gateway's model calls, if the gateway's Langfuse callback is on.",
                settings.langfuse_url,
                configured=True,
            )
        )
    return found
