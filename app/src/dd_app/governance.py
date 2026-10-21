"""The conductor the app runs agents through, and the principal every run acts for.

The standards advisor (`standards.advisor`) runs in this process, registered beside the app's agent
list, so each run passes the policy gate, the input check, the grounding linter and the source
check, and is stored with whom it acted for (ADR-0018, issue #60).
"""

from __future__ import annotations

import asyncio
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dd_agent_standards import factory as standards
from dd_harness import conversations
from dd_harness.conductor import Conductor
from dd_harness.settings import Settings, build_authenticator, build_conductor
from dd_sdk.contract.models import (
    UUID7_PATTERN,
    Envelope,
    InvocationRequest,
    Principal,
    new_invocation_id,
)

STANDARDS_AGENT_ID = "standards.advisor"
RUN_ID = re.compile(r"[0-9A-Za-z-]{1,64}")
CONVERSATION_ID = re.compile(UUID7_PATTERN)


class UnknownConversationError(LookupError):
    """No conversation has this identifier: it was neither started here nor has a stored turn."""


def _report(path: Path) -> dict[str, Any] | None:
    """A check's stored summary (`GroundingReport.summary`, `SourceReport.summary`), which says
    `FAILED` when the check failed."""
    if not path.is_file():
        return None
    summary = path.read_text(encoding="utf-8").strip()
    return {"passed": "FAILED" not in summary, "summary": summary}


@dataclass
class Governance:
    """The conductor and the principal its runs act for.

    A conductor is called on the thread that built it, one invocation at a time
    (`workbench/evaluation.py`), so both are built on one worker thread and every invocation is
    submitted to it. `create` builds them at start-up, so a bad setting stops the app before it
    serves a page.

    The conductor's delegation callback (`conductor.harness_url`, ADR-0012) is the app itself,
    which serves the conductor's A2A routes for delegation callbacks only (#129). A delegated
    child comes in over those routes and runs off the worker, as under `dd-harness serve`: its
    parent holds the worker until the child has ended, so a child submitted to it would wait
    for ever.
    """

    conductor: Conductor
    acting_for: Principal
    worker: ThreadPoolExecutor = field(repr=False)
    # Conversations started in this process that have no turn yet. There is no conversation
    # store (ADR-0012 §4): once a turn is stored the store holds the conversation, and an id
    # never used is forgotten when the app stops.
    _started: set[str] = field(default_factory=set, repr=False)

    @classmethod
    def create(cls, settings: Settings, base_url: str) -> Governance:
        """`base_url` is where the app is reached; `DD_HARNESS_URL` (`settings.harness_url`)
        overrides it as the delegation callback."""
        worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dd-app")

        def build() -> tuple[Conductor, Principal]:
            # The stub authenticator: the operator's assertion until there is authentication
            # (ADR-0018, #17), not the person using the page.
            acting_for = build_authenticator(settings).principal_for(None)
            conductor = build_conductor(settings, agents=[standards.build()])
            conductor.harness_url = settings.harness_url or base_url
            return conductor, acting_for

        try:
            conductor, acting_for = worker.submit(build).result()
        except BaseException:
            worker.shutdown()
            raise
        return cls(conductor, acting_for, worker)

    async def invoke(self, request: InvocationRequest) -> Envelope:
        future = self.worker.submit(self.conductor.invoke, request, acting_for=self.acting_for)
        return await asyncio.wrap_future(future)

    async def run(self, agent_id: str, input: dict[str, Any]) -> dict[str, Any]:
        """One run, start to finish (`POST /api/runs`): its envelope and the checks' reports.

        A stopgap until the shell streams runs over AG-UI (#68, #69): the page learns nothing
        until the run has ended, and infers the stages from what comes back. Raises what
        `Conductor.invoke` raises for a request it refuses before running.
        """
        envelope = await self.invoke(InvocationRequest(agent_id=agent_id, input=input))
        document = envelope.to_document()
        return {"envelope": document, "checks": self.checks(envelope.invocation_id)}

    def start_conversation(self) -> str:
        """A new conversation's identifier (`POST /api/conversations`). The server mints it, so a
        turn can be sent only to a conversation the app started or has stored."""
        conversation_id = new_invocation_id()
        self._started.add(conversation_id)
        return conversation_id

    async def turn(self, conversation_id: str, agent_id: str, message_text: str) -> dict[str, Any]:
        """One turn of a conversation, start to finish (`POST /api/conversations/{id}/turns`): a
        `Message` to `agent_id`, answered as `run` answers.

        The history is built here from the stored turns, never taken from the caller, so the
        input hash covers what the agent was really shown (ADR-0024 §17). It is read on the
        worker, in the same call as the invocation, so two turns sent at once are run one after
        the other and the second is shown the first. Raises `UnknownConversationError`, or what
        `Conductor.invoke` raises for a request it refuses before running.
        """

        def invoke() -> Envelope:
            found = self._conversation(conversation_id)
            if found is None:
                raise UnknownConversationError(conversation_id)
            message = {
                "schema_class": "Message",
                "message_text": message_text,
                "history": found["history"],
            }
            request = InvocationRequest(
                agent_id=agent_id, conversation_id=conversation_id, input=message
            )
            return self.conductor.invoke(request, acting_for=self.acting_for)

        envelope = await asyncio.wrap_future(self.worker.submit(invoke))
        self._started.discard(conversation_id)
        return {"envelope": envelope.to_document(), "checks": self.checks(envelope.invocation_id)}

    def conversations(self) -> list[dict[str, Any]]:
        """Every stored conversation, most recently active first (`GET /api/conversations`). One
        started but given no turn yet is not listed."""
        return conversations.list_conversations(self.conductor.store)

    def conversation(self, conversation_id: str) -> dict[str, Any] | None:
        """A conversation as `dd_harness.conversations` derives it (`GET /api/conversations/{id}`),
        or None. One started but given no turn yet has no turns."""
        if not CONVERSATION_ID.fullmatch(conversation_id):
            return None
        return self._conversation(conversation_id)

    def _conversation(self, conversation_id: str) -> dict[str, Any] | None:
        found = conversations.get_conversation(self.conductor.store, conversation_id)
        if found is None and conversation_id in self._started:
            found = {
                "conversation_id": conversation_id,
                "turns": [],
                "inputs": {},
                "version_changes": [],
                "history": [],
            }
        return found

    def runs(self) -> list[dict[str, Any]]:
        """Every stored run, newest first (`GET /api/runs`)."""
        rows = [
            {
                "invocation_id": e["invocation_id"],
                "agent_id": e["agent_id"],
                "status": e["outcome"]["status"],
                "completed_at": e["completed_at"],
                "acting_for": (e.get("acting_for") or {}).get("name"),
            }
            for e in self.conductor.store.iter_envelopes()
        ]
        return list(reversed(rows))

    def stored_run(self, invocation_id: str) -> dict[str, Any] | None:
        """A stored run as `run` returned it, with its request (`GET /api/runs/{id}`), or None.

        Only an identifier made of letters, digits and hyphens names a run, so no path outside
        the store can be read.
        """
        if not RUN_ID.fullmatch(invocation_id):
            return None
        store = self.conductor.store
        envelope = store.get(invocation_id)
        if envelope is None:
            return None
        return {
            "envelope": envelope,
            "request": store.get_request(invocation_id),
            "checks": self.checks(invocation_id),
        }

    def checks(self, invocation_id: str) -> dict[str, Any]:
        """What the grounding linter and the source check reported on a run, from the summaries
        the conductor stores beside it. The conductor runs both over every envelope it stores,
        even one the gate refused; a report missing from the run's directory is None."""
        run_dir = self.conductor.store.root / invocation_id
        return {name: _report(run_dir / f"{name}.txt") for name in ("grounding", "sources")}

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
