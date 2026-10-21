"""The conductor the app runs agents through, and the principal every run acts for.

R3 (`r3.standards-advisor`) runs in this process, registered beside the app's agent list, so
each run passes the policy gate, the input check, the grounding linter and the source check, and
is stored with whom it acted for (ADR-0018, issue #60).
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from dd_agent_r3 import factory as r3
from dd_harness.conductor import Conductor
from dd_harness.settings import Settings, build_authenticator, build_conductor
from dd_sdk.contract.models import Envelope, InvocationRequest, Principal

R3_AGENT_ID = "r3.standards-advisor"


@dataclass
class Governance:
    """The conductor and the principal its runs act for.

    A conductor is called on the thread that built it, one invocation at a time
    (`workbench/evaluation.py`), so both are built on one worker thread and every invocation is
    submitted to it. `create` builds them at start-up, so a bad setting stops the app before it
    serves a page.
    """

    conductor: Conductor
    acting_for: Principal
    worker: ThreadPoolExecutor = field(repr=False)

    @classmethod
    def create(cls, settings: Settings) -> Governance:
        worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dd-app")

        def build() -> tuple[Conductor, Principal]:
            # The stub authenticator: the operator's assertion until there is authentication
            # (ADR-0018, #17), not the person using the page.
            acting_for = build_authenticator(settings).principal_for(None)
            return build_conductor(settings, agents=[r3.build()]), acting_for

        try:
            conductor, acting_for = worker.submit(build).result()
        except BaseException:
            worker.shutdown()
            raise
        return cls(conductor, acting_for, worker)

    async def invoke(self, request: InvocationRequest) -> Envelope:
        future = self.worker.submit(self.conductor.invoke, request, acting_for=self.acting_for)
        return await asyncio.wrap_future(future)

    def agents(self) -> dict[str, Any]:
        """What the shell's capabilities panel is drawn from (`GET /api/agents`).

        Each registered agent's manifest, as its card declares it, beside what this deployment's
        profile assigns it: the action class, and whether that class needs approval (ADR-0017).
        An agent the profile does not list is shown with `assigned_action_class: null`; the gate
        refuses it. The profile and the principal are named so the page can say whose rules
        apply and whom runs act for.
        """
        profile = self.conductor.profile
        listing = self.conductor.registry.listing()
        for entry in listing["agents"]:
            assigned = profile.agents.get(entry["agent_id"])
            entry["assigned_action_class"] = assigned
            entry["requires_approval"] = (
                assigned is not None and assigned in profile.actions_requiring_approval
            )
        return {
            **listing,
            "profile": {"ref": profile.ref, "digest": profile.digest},
            "acting_for": {
                "name": self.acting_for.name,
                "assurance": self.acting_for.assurance.value,
            },
        }
