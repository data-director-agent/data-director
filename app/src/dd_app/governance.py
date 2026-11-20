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
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from dd_app.about_refresh import AboutRefresh
from dd_app.attached import keep_attached
from dd_app.config import DEFAULT_PROJECTS_DIR, DEFAULT_REPOSITORIES_DIR
from dd_app.documentation_check import accept
from dd_app.run_checks import stored_checks
from dd_app.turn_body import AttachedDocument, Turn
from dd_app.turn_lock import hold_turn
from dd_harness import conversations, project_access
from dd_harness.conductor import Conductor
from dd_harness.identity import Authenticator, IdentityError, OperatorAssertion
from dd_harness.listing import Readable
from dd_harness.observe import RunObserver
from dd_harness.policy import check_attached_document
from dd_harness.project_access import Action, Role
from dd_harness.projects import UnknownProjectError
from dd_harness.requirements import Requirements, load_requirements
from dd_harness.settings import (
    Settings,
    build_conductor,
    conversation_locks,
    project_storage,
    projects_dir,
    repositories_dir,
)
from dd_harness.storage import ProjectStorage
from dd_harness.turn_locks import ConversationLocks, LocalConversationLocks
from dd_sdk.contract.models import (
    UUID7_PATTERN,
    Envelope,
    InvocationRequest,
    Principal,
    new_invocation_id,
)

CONVERSATION_ID = re.compile(UUID7_PATTERN)
# What a turn says when the researcher attached an inventory and wrote nothing, so that the
# history reads as what happened (docs/specs/app.md).
INVENTORY_ONLY_TEXT = "I have attached an inventory of my dataset's files."
# What a turn says when the researcher attached a document and wrote nothing.
DOCUMENTATION_ONLY_TEXT = "I have attached a document about my dataset."
# What a turn says when the researcher attached both and wrote nothing.
BOTH_ONLY_TEXT = "I have attached an inventory of my dataset's files and a document about it."
# The cause recorded for a project a person creates on purpose (`POST /api/projects`), which is
# listed before it holds anything (docs/specs/app.md, rule 27).
CREATED_BY_ROUTE = "POST /api/projects"


def _attached_text(
    inventory: Mapping[str, Any] | None, documentation: AttachedDocument | None
) -> str:
    """What a turn says when the researcher attached something and wrote nothing."""
    if inventory is not None and documentation is not None:
        return BOTH_ONLY_TEXT
    return INVENTORY_ONLY_TEXT if inventory is not None else DOCUMENTATION_ONLY_TEXT


class UnknownConversationError(LookupError):
    """No conversation has this identifier: it was neither started here nor has a stored turn."""


class TurnConflictError(Exception):
    """A turn that does not follow the conversation's latest turn, or that arrives while another
    turn of the conversation is still running (docs/specs/orchestration.md). Nothing was run."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


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
    projects: ProjectStorage | None = None
    # The requirement sets a chosen repository resolves to (docs/specs/deposit.md), from
    # `DD_REPOSITORIES_DIR`. None where the app lets nobody choose, as in a test that needs none.
    requirements: Requirements | None = None
    # Each conversation's turn lock: the run store's, shared by app processes over one store, or,
    # built without one (a test), this process's alone (docs/specs/app.md, "Turn locks").
    turn_locks: ConversationLocks = field(default_factory=LocalConversationLocks, repr=False)
    # Conversations started in this process that have no turn yet, in no project, each with the
    # `principal_id` of whoever started it. Only an app that keeps no projects (a test) fills it,
    # so it is this process's alone. There is no conversation store (docs/specs/orchestration.md):
    # once a turn is stored the store holds the conversation, and an id never used is forgotten.
    _started: dict[str, str] = field(default_factory=dict, repr=False)
    # How often `GET /api/about` may retry the missing agents (`DeploymentView.deployment`): one
    # throttle for the process, whichever request asks.
    about_refresh: AboutRefresh = field(default_factory=AboutRefresh, repr=False)

    @classmethod
    def create(
        cls, settings: Settings, base_url: str, authenticator: Authenticator | None = None
    ) -> Governance:
        """`base_url` is where the app is reached; `DD_HARNESS_URL` (`settings.harness_url`)
        overrides it as the delegation callback. `authenticator` is the sign-in's
        (`dd_harness.signin.SignIn`). Without one the app is a development server, and every run
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
        # A location that cannot be used (a directory that cannot be made, a database that
        # cannot be reached or is not migrated) stops start-up with `SettingsError`.
        projects = project_storage(projects_dir(DEFAULT_PROJECTS_DIR), "DD_PROJECTS_DIR")
        requirements = load_requirements(repositories_dir(DEFAULT_REPOSITORIES_DIR))
        locks = conversation_locks(settings.runs_dir, "DD_RUNS_DIR")
        return cls(conductor, authenticator, projects, requirements, turn_locks=locks)

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

        A stopgap until the shell streams runs over AG-UI (#69): the page learns nothing
        until the run has ended, and infers the stages from what comes back. Raises what
        `Conductor.invoke` raises for a request it refuses before running.
        """
        envelope = await self.invoke(InvocationRequest(agent_id=agent_id, input=input), acting_for)
        document = envelope.to_document()
        return {
            "envelope": document,
            "checks": await asyncio.to_thread(
                stored_checks, self.conductor.store, envelope.invocation_id
            ),
        }

    def start_conversation(self, acting_for: Principal, project_id: str | None = None) -> str:
        """A new conversation's identifier (`POST /api/conversations`). The server mints it, so a
        turn can be sent only to a conversation the app started or has stored.

        Where the app keeps projects, every conversation is in one, so that what the researcher
        attaches and what the agents draft are kept together (docs/specs/app.md). With
        `project_id` the conversation is started in that project, which `acting_for` must be able
        to read; without one, in a new project. Raises `UnknownProjectError` for a project that
        does not exist or that they may not read, and for any project where the app keeps none."""
        if self.projects is None:
            if project_id is not None:
                raise UnknownProjectError(f"no project {project_id!r}")
            conversation_id = new_invocation_id()
            self._started[conversation_id] = acting_for.principal_id
            return conversation_id
        caused_by = "POST /api/conversations"
        if project_id is None:
            project_id = self.projects.create(acted_for=acting_for, caused_by=caused_by)
        elif not self.may_read_project(project_id, acting_for):
            raise UnknownProjectError(f"no project {project_id!r}")
        return self.projects.start_conversation(
            project_id, acted_for=acting_for, caused_by=caused_by
        )

    async def turn(
        self,
        conversation_id: str,
        sent: Turn,
        acting_for: Principal,
        *,
        observer: RunObserver | None = None,
        cancel: threading.Event | None = None,
    ) -> Envelope:
        """One turn of a conversation (`POST /api/conversations/{id}/turns`, and its stream): a
        `Message` to `agent_id`, and the envelope of its run. `sent` is what the turn gives, as
        `Turn` names it; `observer` and `cancel` are the conductor's, through which the turn's
        stream watches the run and may cancel it.

        A turn may attach an `inventory`, which is added to the conversation's project before the
        orchestrator runs, so the conductor tells it what the project now holds
        (docs/specs/projects.md). An inventory the project refuses raises `ProjectError`, and one
        sent to a conversation in no project `ValueError`; either way nothing is run or recorded.
        With an inventory, `message_text` may be blank.

        A turn may also attach `documentation`, a supporting document's text, which is added to
        the project in the same way and listed to the orchestrator without its text. A document
        the project would refuse is refused before the inventory is added, so a refused turn adds
        neither. With either attached, `message_text` may be blank.

        A turn may carry the researcher's `answer` to the questions the latest turn asked, beside
        `message_text`, which says the same in words. The harness checks it against those
        questions (`conversations.answer_problem`); one it refuses raises `ValueError` and nothing
        is run (docs/specs/app.md).

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
        agent_id, message_text, follows = sent.agent_id, sent.message_text, sent.follows
        inventory, answer, documentation = sent.inventory, sent.answer, sent.documentation
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

        release = await hold_turn(self.turn_locks, conversation_id)
        if release is None:
            raise TurnConflictError(
                "Another turn of this conversation is still running. Nothing was run: read the "
                "conversation once it has been answered, then send the message again if it is "
                "still needed."
            )
        try:
            found = await asyncio.to_thread(self.stored_conversation, conversation_id)
            # Someone else's conversation is answered as one that does not exist (#153).
            if found is None or not await asyncio.to_thread(
                self.may_read_conversation, conversation_id, acting_for
            ):
                raise UnknownConversationError(conversation_id)
            latest = found["turns"][-1]["invocation_id"] if found["turns"] else None
            if follows != latest:
                raise TurnConflictError(
                    f"This turn follows {follows!r}, but the conversation's latest turn is "
                    f"{latest!r}. Nothing was run: read the conversation, then send the message "
                    "again if it is still needed."
                )
            if answer is not None and (problem := conversations.answer_problem(found, answer)):
                raise ValueError(f"The answer was not sent: {problem}. Nothing was run.")
            if inventory is not None or documentation is not None:
                await asyncio.to_thread(
                    self._attach, conversation_id, inventory, documentation, acting_for
                )
                message_text = message_text.strip() or _attached_text(inventory, documentation)
            message = {
                "schema_class": "Message",
                "message_text": message_text,
                "history": found["history"],
            }
            if answer is not None:
                message["reply_answers"] = answer.model_dump(mode="json", exclude_none=True)
            request = InvocationRequest(
                agent_id=agent_id, conversation_id=conversation_id, input=message
            )
            run = asyncio.ensure_future(
                self.conductor.ainvoke(
                    request, acting_for=acting_for, observer=observer, cancel=cancel
                )
            )
            try:
                envelope = await asyncio.shield(run)
            except asyncio.CancelledError:
                # The invocation runs on in its thread whatever happens to this turn, so the
                # lock is kept until it is stored: the next turn must be shown this one.
                await asyncio.wait({run})
                raise
        finally:
            await asyncio.shield(asyncio.to_thread(release))
        self._started.pop(conversation_id, None)
        return envelope

    def _attach(
        self,
        conversation_id: str,
        inventory: Mapping[str, Any] | None,
        documentation: AttachedDocument | None,
        acting_for: Principal,
    ) -> None:
        """Add all a turn attached to the conversation's project, or none if any is refused."""
        project_id = self.projects.project_of(conversation_id) if self.projects else None
        if self.projects is None or project_id is None:
            what = "an inventory" if inventory is not None else "a document"
            raise ValueError(
                f"This conversation is in no project, so there is nowhere to keep {what}."
            )
        caused_by = f"POST /api/conversations/{conversation_id}/turns"
        if documentation is not None:
            check_attached_document(self.conductor.profile)
            accept(documentation)
        if inventory is not None:
            self.projects.add_inventory(
                project_id, inventory, acted_for=acting_for, caused_by=caused_by
            )
        if documentation is not None:
            keep_attached(self.projects, project_id, documentation, acting_for, caused_by)

    # Who may read what (#153, docs/specs/app.md). Each person sees their own work: a run or
    # conversation in a project is readable by whoever may read the project, and one in no project
    # by the principal it acted for. Ownership is read from what the run store and the project logs
    # already record, never from a second record that could disagree with them. A delegated child
    # carries its parent's `acting_for` and `project_id`, so it belongs where its parent does.
    # The run store lists what a reader may read (`readable`), decided from the logs of the projects
    # that name them, read at once (`project_access.readable_logs`): no listing reads every
    # project's log, or makes a read per project.

    def role(self, project_id: str, principal: Principal) -> Role | None:
        """`principal`'s role in the project `project_id`, as the harness's access check reads it
        from the project's log (`dd_harness.project_access`), or None if they have none, the
        project does not exist, or the app keeps no projects. Every check of a project goes
        through here."""
        if self.projects is None:
            return None
        return project_access.role_of(self.projects, project_id, principal)

    def is_deleted(self, project_id: str) -> bool:
        """Whether the project `project_id` is deleted (docs/specs/projects.md, invariant 22)."""
        return self.projects is not None and self.projects.is_deleted(project_id)

    def may_read_project(self, project_id: str, reader: Principal) -> bool:
        """Whether `reader` may read the project `project_id`."""
        return project_access.allowed(self.role(project_id, reader), Action.READ)

    def may_read_run(self, envelope: Mapping[str, Any], reader: Principal) -> bool:
        """Whether `reader` may read the stored run whose envelope is `envelope`."""
        project_id = envelope.get("project_id")
        if project_id and self.projects is not None:
            return self.may_read_project(project_id, reader)
        acting_for = envelope.get("acting_for") or {}
        return bool(acting_for.get("principal_id") == reader.principal_id)

    def may_read_conversation(self, conversation_id: str, reader: Principal) -> bool:
        """Whether `reader` may read, and add a turn to, the conversation `conversation_id`: one
        in a project follows the project unless it is deleted; one in no project belongs to
        whoever started it, which is whom its first turn acted for once it has one."""
        project_id = self.projects.project_of(conversation_id) if self.projects else None
        if project_id is not None and self.projects is not None:
            hidden = project_access.conversation_deleted(self.projects, project_id, conversation_id)
            return not hidden and self.may_read_project(project_id, reader)
        if conversation_id in self._started:
            return self._started[conversation_id] == reader.principal_id
        first = next(
            (
                e
                for e in self.conductor.store.iter_envelopes(conversation_id=conversation_id)
                if not e.get("parent_invocation_id")
            ),
            None,
        )
        return first is not None and self.may_read_run(first, reader)

    def readable(self, reader: Principal) -> Readable:
        """What the run store lists for `reader`: runs in the projects they may read, but not in
        their deleted conversations, and runs in no project that acted for them."""
        if self.projects is None:
            return Readable(reader.principal_id, None)
        logs = project_access.readable_logs(self.projects, reader)
        return project_access.readable_from(reader, logs)

    def stored_conversation(self, conversation_id: str) -> dict[str, Any] | None:
        """A conversation as `dd_harness.conversations` derives it, with what its project holds
        now, whoever asks: `Reads.conversation` is the one a reader is answered with. One started
        but given no turn yet has no turns; one that does not exist is None."""
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
            summary = self.projects.summary(project_id)
            found["project_id"] = project_id
            found["inventory"] = summary["inventory"]
            # Where the project is in the process flow, derived from its log now
            # (docs/specs/orchestration.md).
            found["progress"] = summary["progress"]
        return found
