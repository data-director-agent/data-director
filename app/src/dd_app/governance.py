"""The conductor the app runs agents through, and how it learns whom each run acts for.

Every agent is a separate service that the conductor reaches over A2A (docs/specs/agents.md,
docs/specs/app.md), so each run passes the policy gate, the input check, the grounding linter and
the source check, and is stored with whom it acted for (docs/specs/policy-and-identity.md). Whom a
run acts for comes from the request that started it, through the `Authenticator`: the signed-in
person's session (docs/specs/policy-and-identity.md), or on a development server the operator's
assertion. The app runs no agent in its own process, so it never holds an agent's model key
(docs/specs/policy-and-identity.md).
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dd_app.config import DEFAULT_PROJECTS_DIR
from dd_harness import conversations
from dd_harness.conductor import Conductor
from dd_harness.identity import Authenticator, IdentityError, OperatorAssertion
from dd_harness.projects import ProjectStore
from dd_harness.settings import Settings, SettingsError, build_conductor, projects_dir
from dd_sdk.contract.models import (
    UUID7_PATTERN,
    Envelope,
    InvocationRequest,
    Principal,
    new_invocation_id,
)

RUN_ID = re.compile(r"[0-9A-Za-z-]{1,64}")
CONVERSATION_ID = re.compile(UUID7_PATTERN)
# What a turn says when the researcher attached an inventory and wrote nothing, so that the
# history reads as what happened (docs/specs/app.md).
INVENTORY_ONLY_TEXT = "I have attached an inventory of my dataset's files."


class UnknownConversationError(LookupError):
    """No conversation has this identifier: it was neither started here nor has a stored turn."""


class TurnConflictError(Exception):
    """A turn that does not follow the conversation's latest turn, or that arrives while another
    turn of the conversation is still running (docs/specs/orchestration.md). Nothing was run."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


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

    The conductor's delegation callback (`conductor.harness_url`, docs/specs/orchestration.md) is
    the app itself, which serves the conductor's A2A routes for delegation callbacks only (#129). A
    delegated child comes in over those routes, as under `dd-harness serve`.
    """

    conductor: Conductor
    authenticator: Authenticator
    # The projects' logs, which the harness alone writes (docs/specs/projects.md). None where the
    # app keeps no projects, as in a test that needs none.
    projects: ProjectStore | None = None
    # Conversations started in this process that have no turn yet. There is no conversation store
    # (docs/specs/orchestration.md): once a turn is stored the store holds the conversation, and an
    # id never used is forgotten when the app stops.
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
        acts for the operator's assertion (docs/specs/policy-and-identity.md)."""
        if authenticator is None:
            if settings.oidc_issuer is not None:
                raise IdentityError(
                    "DD_OIDC_ISSUER is set, so the app signs people in, and it needs the "
                    "sign-in's authenticator"
                )
            authenticator = OperatorAssertion(settings.principal())
        conductor = build_conductor(settings)
        conductor.harness_url = settings.harness_url or base_url
        root = projects_dir(DEFAULT_PROJECTS_DIR)
        try:
            projects = ProjectStore(root)
        except OSError as exc:
            # One line at start-up, like any other setting that is wrong.
            raise SettingsError(
                f"DD_PROJECTS_DIR {root} cannot be used: {exc.strerror or exc}"
            ) from exc
        return cls(conductor, authenticator, projects)

    def __post_init__(self) -> None:
        # The conductor takes each run's project from the same logs the app reads.
        if self.projects is not None:
            self.conductor.projects = self.projects

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

    def start_conversation(self, acting_for: Principal) -> str:
        """A new conversation's identifier (`POST /api/conversations`). The server mints it, so a
        turn can be sent only to a conversation the app started or has stored.

        Where the app keeps projects, each conversation is started in a project of its own, so
        that what the researcher attaches and what the agents draft are kept together
        (docs/specs/app.md). Starting one in an existing project is TODO(#160)."""
        if self.projects is None:
            conversation_id = new_invocation_id()
            self._started.add(conversation_id)
            return conversation_id
        caused_by = "POST /api/conversations"
        project_id = self.projects.create(acted_for=acting_for, caused_by=caused_by)
        return self.projects.start_conversation(
            project_id, acted_for=acting_for, caused_by=caused_by
        )

    async def turn(
        self,
        conversation_id: str,
        agent_id: str,
        message_text: str,
        follows: str | None,
        acting_for: Principal,
        inventory: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """One turn of a conversation, start to finish (`POST /api/conversations/{id}/turns`): a
        `Message` to `agent_id`, answered as `run` answers.

        A turn may attach an `inventory`, which is added to the conversation's project before the
        orchestrator runs, so the conductor tells it what the project now holds
        (docs/specs/projects.md). An inventory the project refuses raises `ProjectError`, and one
        sent to a conversation in no project `ValueError`; either way nothing is run or recorded.
        With an inventory, `message_text` may be blank.

        The history is built here from the stored turns, never taken from the caller, so the
        input hash covers what the agent was really shown (docs/specs/app.md). It is read under the
        conversation's lock, held until the turn is stored, even if the request that sent it has
        gone; turns to different conversations run side by side.

        A turn names the turn it `follows` by that turn's `invocation_id`, or None for the first
        (docs/specs/orchestration.md). One that does not follow the latest stored turn, or that
        arrives while another turn of the conversation is still running, is refused with
        `TurnConflictError` before anything runs. So a message sent again after a dropped
        connection runs only if the first attempt never arrived (#337), and two windows cannot
        fork a conversation.

        A turn goes only to the orchestrator the profile names (docs/specs/app.md); a turn to any
        other agent, or under a profile that names none, is refused with `ValueError` before
        anything runs. Raises `UnknownConversationError`, or what `Conductor.invoke` raises for a
        request it refuses before running.
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

        # No await between this check and taking the lock, so no other turn can come between.
        held = self._turn_locks.get(conversation_id)
        if held is not None and held[0].locked():
            raise TurnConflictError(
                "Another turn of this conversation is still running. Nothing was run: read the "
                "conversation once it has been answered, then send the message again if it is "
                "still needed."
            )
        async with self._turn_lock(conversation_id):
            found = await asyncio.to_thread(self._conversation, conversation_id)
            if found is None:
                raise UnknownConversationError(conversation_id)
            latest = found["turns"][-1]["invocation_id"] if found["turns"] else None
            if follows != latest:
                raise TurnConflictError(
                    f"This turn follows {follows!r}, but the conversation's latest turn is "
                    f"{latest!r}. Nothing was run: read the conversation, then send the message "
                    "again if it is still needed."
                )
            if inventory is not None:
                await asyncio.to_thread(self._add_inventory, conversation_id, inventory, acting_for)
                message_text = message_text.strip() or INVENTORY_ONLY_TEXT
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

    def _add_inventory(
        self, conversation_id: str, inventory: Mapping[str, Any], acting_for: Principal
    ) -> None:
        project_id = self.projects.project_of(conversation_id) if self.projects else None
        if self.projects is None or project_id is None:
            raise ValueError(
                "This conversation is in no project, so there is nowhere to keep an inventory."
            )
        self.projects.add_inventory(
            project_id,
            inventory,
            acted_for=acting_for,
            caused_by=f"POST /api/conversations/{conversation_id}/turns",
        )

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
        project_id = self.projects.project_of(conversation_id) if self.projects else None
        if found is None and (conversation_id in self._started or project_id is not None):
            found = {
                "conversation_id": conversation_id,
                "turns": [],
                "inputs": {},
                "version_changes": [],
                "history": [],
            }
        if found is not None and self.projects is not None and project_id is not None:
            # What the project holds now, which a turn's input shows only as it was then.
            found["project_id"] = project_id
            found["inventory"] = self.projects.summary(project_id)["inventory"]
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
        profile assigns it: the action class, and whether that class needs approval
        (docs/specs/policy-and-identity.md). An agent the profile does not list is shown with
        `assigned_action_class: null`; the gate refuses it. The profile and `acting_for`, the
        caller's principal, are named so the page can say whose rules apply and whom runs act for,
        and the profile's `orchestrator` so the home page converses with that agent and no other
        (docs/specs/app.md).
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

    def deployment(self) -> dict[str, Any]:
        """What this deployment runs, for an operator's check (`GET /api/about`, open to all).

        The profile the conductor holds runs to, and which configured agents it reaches. An agent
        is named by its entry in the agent configuration, never with its address or the reason it
        is missing: the answer is public, and a reason can carry an internal address.
        """
        profile = self.conductor.profile
        registry = self.conductor.registry
        registry.refresh()  # retries only the agents still missing, as `agents` does
        return {
            "profile": {
                "id": profile.profile_id,
                "version": profile.version,
                "digest": profile.digest,
                "orchestrator": profile.orchestrator,
            },
            "unavailable": sorted(registry.unavailable),
            "incompatible": sorted(registry.incompatible),
        }


def principal_summary(principal: Principal) -> dict[str, Any]:
    """What the shell is told about a principal: whom runs act for, and who vouched for them."""
    summary: dict[str, Any] = {"name": principal.name, "assurance": principal.assurance.value}
    if principal.vouched_by is not None:
        summary["vouched_by"] = str(principal.vouched_by)
    return summary
