"""The conductor the app runs agents through, and how it learns whom each run acts for.

Every agent is a separate service that the conductor reaches over A2A (ADR-0011, ADR-0027), so
each run passes the policy gate, the input check, the grounding linter and the source check, and
is stored with whom it acted for (ADR-0018). Whom a run acts for comes from the request that
started it, through the `Authenticator`: the signed-in person's session (ADR-0029), or on a
development server the operator's assertion. The app runs no agent in its own process, so it never
holds an agent's model key (ADR-0026).
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dd_harness import conversations
from dd_harness.conductor import Conductor
from dd_harness.identity import Authenticator, IdentityError, OperatorAssertion
from dd_harness.settings import Settings, build_conductor
from dd_sdk.contract.models import (
    UUID7_PATTERN,
    Envelope,
    InvocationRequest,
    Principal,
    new_invocation_id,
)

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
    """The conductor, and the authenticator that says whom each request's runs act for.

    `create` builds them at start-up, so a bad setting stops the app before it serves a page.
    Runs are awaited through `Conductor.ainvoke`, so several may run at once.

    The conductor's delegation callback (`conductor.harness_url`, ADR-0012) is the app itself,
    which serves the conductor's A2A routes for delegation callbacks only (#129). A delegated
    child comes in over those routes, as under `dd-harness serve`.
    """

    conductor: Conductor
    authenticator: Authenticator
    # Conversations started in this process that have no turn yet. There is no conversation
    # store (ADR-0012 §4): once a turn is stored the store holds the conversation, and an id
    # never used is forgotten when the app stops.
    _started: set[str] = field(default_factory=set, repr=False)
    # One lock per conversation, held from reading its history until its turn is stored, with
    # the number of turns holding or waiting for it; the entry goes when that reaches nought.
    _turn_locks: dict[str, tuple[asyncio.Lock, int]] = field(default_factory=dict, repr=False)

    @classmethod
    def create(
        cls, settings: Settings, base_url: str, authenticator: Authenticator | None = None
    ) -> Governance:
        """`base_url` is where the app is reached; `DD_HARNESS_URL` (`settings.harness_url`)
        overrides it as the delegation callback. `authenticator` is the sign-in's
        (`dd_app.signin.SignIn`). Without one the app is a development server, and every run
        acts for the operator's assertion (ADR-0029)."""
        if authenticator is None:
            if settings.oidc_issuer is not None:
                raise IdentityError(
                    "DD_OIDC_ISSUER is set, so the app signs people in, and it needs the "
                    "sign-in's authenticator"
                )
            authenticator = OperatorAssertion(settings.principal())
        conductor = build_conductor(settings)
        conductor.harness_url = settings.harness_url or base_url
        return cls(conductor, authenticator)

    async def invoke(self, request: InvocationRequest, acting_for: Principal) -> Envelope:
        return await self.conductor.ainvoke(request, acting_for=acting_for)

    async def run(
        self, agent_id: str, input: dict[str, Any], acting_for: Principal
    ) -> dict[str, Any]:
        """One run, start to finish (`POST /api/runs`): its envelope and the checks' reports.

        A stopgap until the shell streams runs over AG-UI (#68, #69): the page learns nothing
        until the run has ended, and infers the stages from what comes back. Raises what
        `Conductor.invoke` raises for a request it refuses before running.
        """
        envelope = await self.invoke(InvocationRequest(agent_id=agent_id, input=input), acting_for)
        document = envelope.to_document()
        return {"envelope": document, "checks": self.checks(envelope.invocation_id)}

    def start_conversation(self) -> str:
        """A new conversation's identifier (`POST /api/conversations`). The server mints it, so a
        turn can be sent only to a conversation the app started or has stored."""
        conversation_id = new_invocation_id()
        self._started.add(conversation_id)
        return conversation_id

    async def turn(
        self, conversation_id: str, agent_id: str, message_text: str, acting_for: Principal
    ) -> dict[str, Any]:
        """One turn of a conversation, start to finish (`POST /api/conversations/{id}/turns`): a
        `Message` to `agent_id`, answered as `run` answers.

        The history is built here from the stored turns, never taken from the caller, so the
        input hash covers what the agent was really shown (ADR-0024 §17). It is read under the
        conversation's lock, held until the turn is stored, so two turns sent to one
        conversation at once are run one after the other and the second is shown the first;
        turns to different conversations run side by side. A turn goes only to the orchestrator the
        profile names (ADR-0024 §10); a turn to any other agent, or under a profile that names
        none, is refused with `ValueError` before anything runs. Raises
        `UnknownConversationError`, or what `Conductor.invoke` raises for a request it refuses
        before running.
        """
        orchestrator = self.conductor.profile.orchestrator
        if orchestrator is None:
            raise ValueError(
                f"The profile {self.conductor.profile.ref} names no orchestrator, so there is no "
                "conversation."
            )
        if agent_id != orchestrator:
            raise ValueError(
                f"A turn goes to the orchestrator the profile names, {orchestrator!r}, "
                f"not {agent_id!r}."
            )

        async with self._turn_lock(conversation_id):
            found = await asyncio.to_thread(self._conversation, conversation_id)
            if found is None:
                raise UnknownConversationError(conversation_id)
            message = {
                "schema_class": "Message",
                "message_text": message_text,
                "history": found["history"],
            }
            run = asyncio.ensure_future(
                self.invoke(
                    InvocationRequest(
                        agent_id=agent_id, conversation_id=conversation_id, input=message
                    ),
                    acting_for,
                )
            )
            try:
                envelope = await asyncio.shield(run)
            except asyncio.CancelledError:
                # The invocation runs on in its thread whatever happens to this turn, so the
                # lock is kept until it is stored: the next turn must be shown this one.
                await asyncio.wait({run})
                raise
        self._started.discard(conversation_id)
        return {"envelope": envelope.to_document(), "checks": self.checks(envelope.invocation_id)}

    @asynccontextmanager
    async def _turn_lock(self, conversation_id: str) -> AsyncIterator[None]:
        lock, count = self._turn_locks.get(conversation_id, (asyncio.Lock(), 0))
        self._turn_locks[conversation_id] = (lock, count + 1)
        try:
            async with lock:
                yield
        finally:
            lock, count = self._turn_locks[conversation_id]
            if count == 1:
                del self._turn_locks[conversation_id]
            else:
                self._turn_locks[conversation_id] = (lock, count - 1)

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

    def agents(self, acting_for: Principal) -> dict[str, Any]:
        """What the shell's capabilities panel is drawn from (`GET /api/agents`).

        Each registered agent's manifest, as its card declares it, beside what this deployment's
        profile assigns it: the action class, and whether that class needs approval (ADR-0017).
        An agent the profile does not list is shown with `assigned_action_class: null`; the gate
        refuses it. The profile and `acting_for`, the caller's principal, are named so the page
        can say whose rules apply and whom runs act for, and the profile's `orchestrator` so the
        home page converses with that agent and no other (ADR-0024 §10).
        """
        profile = self.conductor.profile
        self.conductor.registry.refresh()  # an agent started since the app was is found now
        listing = self.conductor.registry.listing()
        for entry in listing["agents"]:
            assigned = profile.agents.get(entry["agent_id"])
            entry["assigned_action_class"] = assigned
            entry["requires_approval"] = (
                assigned is not None and assigned in profile.actions_requiring_approval
            )
        return {
            **listing,
            "profile": {
                "ref": profile.ref,
                "digest": profile.digest,
                "orchestrator": profile.orchestrator,
            },
            "acting_for": principal_summary(acting_for),
        }


def principal_summary(principal: Principal) -> dict[str, Any]:
    """What the shell is told about a principal: whom runs act for, and who vouched for them."""
    summary: dict[str, Any] = {"name": principal.name, "assurance": principal.assurance.value}
    if principal.vouched_by is not None:
        summary["vouched_by"] = str(principal.vouched_by)
    return summary
