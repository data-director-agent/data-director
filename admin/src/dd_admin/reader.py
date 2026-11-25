"""What the admin service's pages read: the deployment's settings, its stores and what it probes,
each kept for a short while (docs/guide/operations/admin.md). `dd_admin.pages` reads an `Admin`;
`dd_admin.app` opens one and mounts the pages over it.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field

from dd_admin import agents as agents_module
from dd_admin import (
    broker,
    escalation_queue,
    gateway,
    monitoring,
    operations,
    policy_view,
    security_events,
    spend,
    usage,
)
from dd_admin.cache import Cached
from dd_admin.settings import AdminSettings
from dd_admin.system import System
from dd_harness.remote import ClientFactory, default_client
from dd_harness.settings import project_storage, run_storage
from dd_harness.storage import ProjectStorage, RunStorage


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
        # How the gateway is set up, and the broker's summary: both change slowly.
        self.gateway_state = Cached(
            lambda: gateway.read_state(self.settings, self.system), ttl_s=300
        )
        self.broker = Cached(lambda: broker.read_broker(self.settings, self.system), ttl_s=60)
        # What the monitoring services say they are alerting on, a little fresher than the rest.
        self.monitoring = Cached(lambda: monitoring.read(self.settings, self.system), ttl_s=30)
        self.about = Cached(
            lambda: self.system.get_json(self.settings.app_url.rstrip("/") + "/api/about"),
            ttl_s=30,
        )
        self.policy = Cached(
            lambda: policy_view.read(
                self.settings, self.system, self.agents.get(), self.about.get()
            ),
            ttl_s=30,
        )
        # The journal is read whole for a window, so each window is kept for a while.
        self.security = {
            days: Cached(
                functools.partial(security_events.read, self.settings, self.system, days),
                ttl_s=60,
            )
            for days in security_events.WINDOWS
        }
        self.escalations = Cached(
            lambda: escalation_queue.read(self.projects, self.policy.get()), ttl_s=60
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
