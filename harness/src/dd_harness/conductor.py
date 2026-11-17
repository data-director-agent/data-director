"""The conductor: policy gate → input check → agent → grounding linter → source check →
validation → project effects → shape check → store → provenance. Each is a named step of
`dd_harness.pipeline`, run in order over the invocation's `RunState`.

`invoke` is a plain function. Every transport (CLI, A2A, AG-UI) is a wrapper around it
(docs/specs/transport.md). It fills in everything an agent must not decide about itself:
identifiers, timestamps, telemetry, the grounding mode and input hash it is held to, the human it
acted for, and whether the output passed the grounding check and the source check. It knows nothing
about any payload class.

The grounding linter checks the agent's account of its run for consistency; the source check
re-hashes what the evidence cites against a copy of the source the harness holds
(docs/specs/grounding.md). A violation of either withholds a succeeded result. Their verdicts are
stored separately, in `grounding.txt` and `sources.txt`.

The shape check runs a payload the envelope still carries against the SHACL shapes its class
brings on the card, where it brings any (docs/specs/contract.md). It only reports: the SHACL
Validation Report is kept as `validation-report.jsonld` beside the run and in its crate, and the
outcome is the same whatever it says.

Delegation (docs/specs/orchestration.md). When the conductor runs a remote agent in grounding mode
`delegation`, and it knows its own A2A address (`harness_url`), it issues that invocation a grant: a
random token, sent with the request (never in `RunContext`), that the agent may present while the
invocation runs to ask the harness to invoke another agent. `invoke_delegated` runs such a request
as an ordinary invocation, sets its lineage from the grant, and records the child against the
parent. The parent's envelope lists those records in `delegations`, which is what the linter checks
a relayed reply against. Delegation is one level deep: a child is never issued a grant.

The human (docs/specs/policy-and-identity.md). Every invocation acts for a principal, which the
transport takes from its authentication boundary and passes to `invoke`; the conductor keeps none of
its own, so an invocation without one cannot be written. A delegated child acts for its parent's
principal, carried on the grant: the caller on that path is an agent, not the human. The principal
is recorded in the envelope and the crate and is never sent to the agent.

Projects (docs/specs/projects.md). A run belongs to a project when its conversation was started
in one, or, for a delegated child, when its parent did. The conductor sets `project_id` on the
request and the envelope; a caller may not, and the agent is never sent it. A run in a project
whose principal may not read it (`project_access`) is refused with `UnknownProjectError` before
anything is stored, and a run in a deleted project with `ProjectDeletedError`; a run already going
when its project is deleted finishes and is recorded, its draft included. Before the input is
hashed, the conductor puts the project's facts into an input class that asks for them
(`project_facts`). Once a run in a project has finished, the project takes its effects (a
proposed version, a title or an entry point) through `ProjectEffects`, which holds those rules
(`dd_harness.project_effects`); a draft the project refuses fails the run instead.

Threads (#171). `invoke` may be called from any thread, and several invocations may run at
once. Async code calls `ainvoke` and `ainvoke_delegated` instead, which keep the one rule that
matters inside the conductor: a parent holds its thread until its children have ended, so the
two run on separate pools and a child never queues behind its parent.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import secrets
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from opentelemetry.trace import SpanContext
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from dd_harness import grounding, pipeline, policy, project_access, project_facts
from dd_harness import sources as source_check
from dd_harness.model_grants import GrantMinter
from dd_harness.observe import RunObserver, Watch
from dd_harness.project_effects import ProjectEffects
from dd_harness.project_facts import FactSource
from dd_harness.projects import (
    ProjectDeletedError,
    UnknownProjectError,
)
from dd_harness.registry import Registered, Registry
from dd_harness.remote import RemoteAgent
from dd_harness.storage import SPANS, RunStorage
from dd_sdk.agent import ModelUse
from dd_sdk.contract import validate
from dd_sdk.contract.models import (
    Delegation,
    Envelope,
    InvocationRequest,
    Principal,
    to_document,
)
from dd_sdk.evidence import envelope_hash
from dd_sdk.model_grant import Account
from dd_sdk.security_log import SecurityEvent, emit
from dd_sdk.tracing import (
    ATTR_OUTCOME,
    Tracing,
    invoke_agent_span,
    make_tracing,
)

log = logging.getLogger(__name__)


class RunProjects(FactSource, ProjectEffects, Protocol):
    """The project areas a run reads facts from (every area but deposits, which no run records),
    and what a finished run does to its project (`dd_harness.project_effects`)."""

    def snapshot(self, project_id: str) -> FactSource:
        """The project's facts as its log reads now, read once for one invocation's questions
        (`dd_harness.projects.SnapshotLog`, docs/specs/storage.md, invariant 12)."""
        ...


class UnknownAgent(Exception):
    pass


class DelegationError(ValueError):
    """A request's lineage is not one the conductor issued: a caller error, never an outcome."""


class ProjectAssignmentError(ValueError):
    """A request that names its own project: a caller error, never an outcome. The conductor
    takes a run's project from its conversation or its parent's grant."""


class DuplicateInvocation(ValueError):
    """A request reuses an `invocation_id` the conductor has run or is running: a caller error.

    Running it would overwrite the stored run, or collide with a parent still in flight.
    """


# The most recent grounding reports kept in memory, for a caller that reads one straight after
# `invoke` (the CLI, the evaluation). Each run's `grounding.txt` artifact is the durable copy.
GROUNDING_REPORTS_KEPT = 256


@dataclass
class Grant:
    """One delegation grant, live while its parent invocation runs."""

    token: str
    parent_invocation_id: str
    parent_agent_id: str
    conversation_id: str | None
    project_id: str | None
    acting_for: Principal
    delegations: list[Delegation] = field(default_factory=list)
    # Children admitted under this grant and not yet finished; revocation waits for them.
    in_flight: int = 0
    watch: Watch = field(default_factory=lambda: Watch(None, None))  # told of each child


@dataclass
class Conductor:
    registry: Registry
    store: RunStorage
    # The deployment's institutional profile, loaded once by whoever builds the conductor. Every
    # invocation, delegated or not, is gated by it; a request cannot name another
    # (docs/specs/policy-and-identity.md).
    profile: policy.Profile
    tracing: Tracing = field(default_factory=make_tracing)
    write_crate: bool = True
    grounding_reports: dict[str, grounding.GroundingReport] = field(default_factory=dict)
    # The copies of sources the source check resolves evidence against (docs/specs/grounding.md).
    # None held means every externally sourced evidence item is reported as unresolved.
    sources: source_check.Sources = field(default_factory=source_check.Sources.none)
    # The harness's own A2A address, sent to delegation agents as their callback. None (the
    # CLI) means no grant is issued and a delegation agent runs without `delegate`.
    harness_url: str | None = None
    # The projects runs may belong to (docs/specs/projects.md), as `RunProjects`. None (most
    # tests, the workbench without DD_PROJECTS_DIR) means no run is in a project.
    projects: RunProjects | None = None
    # Mints the model grant each invocation of a model-backed agent is sent
    # (docs/specs/model-accounts.md). None (the default) mints none.
    model_grants: GrantMinter | None = None
    _grants: dict[str, Grant] = field(default_factory=dict, repr=False)
    _grants_lock: threading.Condition = field(default_factory=threading.Condition, repr=False)
    _running: set[str] = field(default_factory=set, repr=False)
    _running_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _reports_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    # Top-level invocations from `ainvoke`, built on its first call so a caller that only uses
    # `invoke` (the CLI, most tests) starts no threads. Delegated children run on the default
    # executor instead, so parents waiting on them can never take every thread a child needs.
    _parents: ThreadPoolExecutor | None = field(default=None, repr=False)
    _parents_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self) -> None:
        # A profile that lets people's own accounts pay is in force only if grants carry that
        # to the broker (docs/specs/policy-and-identity.md, invariant 4).
        if self.profile.model_accounts.own != "off" and self.model_grants is None:
            raise policy.PolicyError(
                f"profile {self.profile.profile_id!r} sets model_accounts.own to "
                f"{self.profile.model_accounts.own}, but the harness mints no model grants; set "
                "DD_MODEL_GRANT_SIGNING_KEY, DD_MODEL_BROKER_SUBJECT_KEY and DD_PSEUDONYM_SECRET "
                "(docs/specs/model-accounts.md)"
            )
        # Each run of these is refused; say so once at start-up, where the operator looks.
        for agent in self.registry:
            if self._bypasses_broker(agent):
                log.warning(
                    "profile %r lets people's own model accounts pay, and agent %r calls a model "
                    "without the agent configuration stating model_broker: true; its runs will "
                    "be refused (docs/specs/model-accounts.md, invariant 14)",
                    self.profile.profile_id,
                    agent.spec.agent_id,
                )

    async def ainvoke(
        self,
        request: InvocationRequest,
        *,
        acting_for: Principal,
        observer: RunObserver | None = None,
        cancel: threading.Event | None = None,
    ) -> Envelope:
        """`invoke`, awaited from async code without blocking its event loop."""
        with self._parents_lock:
            if self._parents is None:
                self._parents = ThreadPoolExecutor(thread_name_prefix="dd-conductor")
            parents = self._parents
        call = functools.partial(
            self.invoke, request, acting_for=acting_for, observer=observer, cancel=cancel
        )
        return await asyncio.get_running_loop().run_in_executor(parents, call)

    def close(self) -> None:
        """Wait for the invocations `ainvoke` started and release their threads. The conductor
        may still be used afterwards: the next `ainvoke` starts a new pool."""
        with self._parents_lock:
            parents, self._parents = self._parents, None
        if parents is not None:
            parents.shutdown()

    async def ainvoke_delegated(
        self, request: InvocationRequest, token: str, traceparent: str = ""
    ) -> Envelope:
        """`invoke_delegated`, awaited from async code, off the pool parents run on."""
        return await asyncio.to_thread(self.invoke_delegated, request, token, traceparent)

    def invoke(
        self,
        request: InvocationRequest,
        *,
        acting_for: Principal,
        observer: RunObserver | None = None,
        cancel: threading.Event | None = None,
    ) -> Envelope:
        """Run one top-level invocation on behalf of `acting_for`, the principal the caller's
        transport authenticated. Lineage is the conductor's to set, never the caller's.

        `observer` is told the run's stages and its checks' reports as they happen
        (`dd_harness.observe`). Setting `cancel` cancels the run: the conductor looks at it before
        each stage and when the agent answers, and a cancelled run is stored as failed with the
        problem `run-cancelled`, whatever the agent answered (docs/specs/transport.md)."""
        if request.parent_invocation_id is not None:
            raise DelegationError(
                "parent_invocation_id is set by the conductor from a delegation grant; "
                "a caller may not set it"
            )
        if request.project_id is not None:
            raise ProjectAssignmentError(
                "project_id is set by the conductor from the conversation; a caller may not set it"
            )
        project_id = (
            self.projects.project_of(request.conversation_id)
            if self.projects is not None and request.conversation_id is not None
            else None
        )
        # Everything this run asks of its project before it runs is read from one snapshot.
        facts = (
            self.projects.snapshot(project_id)
            if self.projects is not None and project_id is not None
            else None
        )
        # Only someone who may read the project runs anything in it; anyone else is answered as
        # for a project that does not exist (docs/specs/projects.md, invariant 17). A delegated
        # child is not checked again: its grant carries its parent's project.
        if (
            project_id is not None
            and facts is not None
            and not project_access.may(facts, project_id, acting_for, project_access.Action.READ)
        ):
            raise UnknownProjectError(f"no project {project_id!r}")
        # A deleted project takes no new run, not even its owner's (invariant 24).
        if project_id is not None and facts is not None and facts.is_deleted(project_id):
            raise ProjectDeletedError(f"project {project_id} is deleted")
        return self._invoke(
            request, acting_for, project_id=project_id, facts=facts, watch=Watch(observer, cancel)
        )

    def invoke_delegated(
        self, request: InvocationRequest, token: str, traceparent: str = ""
    ) -> Envelope:
        """Run a request a delegation agent sent back under its grant, and record it.

        Raises `DelegationError` for an unknown or expired token or an agent delegating to
        itself. The child's conversation and principal are the parent's, whatever the request or
        its caller says; its policy is the conductor's, as every invocation's is.
        """
        with self._grants_lock:
            grant = self._grants.get(token)
            if grant is None:
                raise DelegationError("unknown or expired delegation token")
            if request.agent_id == grant.parent_agent_id:
                raise DelegationError(f"{request.agent_id} may not delegate to itself")
            grant.in_flight += 1
        try:
            return self._invoke_child(grant, request, traceparent)
        finally:
            with self._grants_lock:
                grant.in_flight -= 1
                self._grants_lock.notify_all()

    def _invoke_child(self, grant: Grant, request: InvocationRequest, traceparent: str) -> Envelope:
        child = request.model_copy(
            update={
                "parent_invocation_id": grant.parent_invocation_id,
                "conversation_id": grant.conversation_id,
                "project_id": None,
            }
        )
        link = _span_context(traceparent)
        envelope = grant.watch.child(
            child, lambda: self._invoke(child, grant.acting_for, link, project_id=grant.project_id)
        )
        record = Delegation(
            delegated_invocation_id=envelope.invocation_id,
            delegated_agent_id=envelope.agent_id,
            delegated_agent_version=envelope.agent_version,
            delegated_status=envelope.outcome.status,
            content_hash=envelope_hash(envelope.to_document()),
        )
        with self._grants_lock:
            grant.delegations.append(record)
        return envelope

    def _bypasses_broker(self, agent: Registered) -> bool:
        """Whether `agent` may call a model without the model broker while the profile lets
        people's own accounts pay (docs/specs/model-accounts.md, invariant 14).

        Only the operator's statement in the registry's configuration (`model_broker`) counts,
        never the agent's card. An agent run in this process is never sent a grant, so it cannot
        call through the broker.
        """
        if self.profile.model_accounts.own == "off" or not agent.spec.models:
            return False
        return not (isinstance(agent, RemoteAgent) and agent.model_broker)

    def _model_grant(
        self, agent: Registered, request: InvocationRequest, acting_for: Principal
    ) -> str | None:
        """The model grant for this invocation, or None (docs/specs/model-accounts.md).

        Minted afresh for every invocation of a remote agent whose card declares `models`,
        delegated children included, and only here: a request cannot carry one. It expires with
        the agent's transport timeout, and is passed to the agent alone: it never enters the
        envelope, a span or a store (invariant 6).
        """
        spec = agent.spec
        if self.model_grants is None or not spec.models or not isinstance(agent, RemoteAgent):
            return None
        # Who pays is the profile's decision, never the agent's or the request's; the broker
        # enforces what the grant says.
        accounts = self.profile.model_accounts
        account = accounts.account
        own = account is not Account.DEPLOYMENT
        minted = self.model_grants.mint(
            agent_id=spec.agent_id,
            invocation_id=request.invocation_id,
            models=(model.model for model in spec.models),
            account=account,
            acting_for=acting_for,
            lifetime_s=agent.timeout_s,
            providers=accounts.provider_names if own else (),
            base_urls=accounts.base_urls if own else (),
            model_map=accounts.model_map(spec.models) if own else None,
        )
        # The security event names the grant's terms, never the grant (docs/specs/security.md).
        emit(
            SecurityEvent.GRANT_MINTED,
            outcome="success",
            service="harness",
            principal=acting_for.principal_id,
            agent_id=spec.agent_id,
            invocation_id=request.invocation_id,
            models=[model.model for model in spec.models],
            account=account.value,
        )
        return minted

    def _issue_grant(
        self, request: InvocationRequest, acting_for: Principal, watch: Watch
    ) -> Grant:
        grant = Grant(
            token=secrets.token_urlsafe(32),
            parent_invocation_id=request.invocation_id,
            parent_agent_id=request.agent_id,
            conversation_id=request.conversation_id,
            project_id=request.project_id,
            acting_for=acting_for,
            watch=watch,
        )
        with self._grants_lock:
            self._grants[grant.token] = grant
        return grant

    def _revoke_grant(self, grant: Grant) -> list[Delegation]:
        """Refuse further children, wait for those already admitted, and return the records.

        A child still running when its parent finishes (the parent's delegate call timed out, or
        the parent did not wait) is stored with the parent's id, so the parent must list it. The
        wait needs no timeout of its own: each child is bounded by its agent's transport timeout.
        """
        with self._grants_lock:
            self._grants.pop(grant.token, None)
            self._grants_lock.wait_for(lambda: grant.in_flight == 0)
            return list(grant.delegations)

    def _invoke(
        self,
        request: InvocationRequest,
        acting_for: Principal,
        link: SpanContext | None = None,
        *,
        project_id: str | None = None,
        facts: FactSource | None = None,
        watch: Watch | None = None,
    ) -> Envelope:
        # The project's facts go in before anything is hashed or stored, so the input hash and
        # request.json cover what the agent was shown; outside a project, what only the conductor
        # may fill is removed (docs/specs/projects.md). They are read from one snapshot of the
        # project: the caller's, or one taken here for a delegated child.
        in_project = project_id if self.projects is not None else None
        if facts is None and self.projects is not None and in_project is not None:
            facts = self.projects.snapshot(in_project)
        sent = to_document(request.input)
        filled = project_facts.give(facts, in_project, sent)
        given = project_facts.given(facts, in_project, filled)
        # Researcher facts the profile keeps from this agent's hosted model are left out, not
        # refused (docs/specs/projects.md, invariant 8): no agent needs them.
        if project_facts.RESEARCHER in given:
            hostings = [model.hosting for model in self._models_of(request.agent_id)]
            out = frozenset(policy.withheld(self.profile, hostings, {project_facts.RESEARCHER}))
            filled, given = project_facts.leave_out(filled, out), given - out
        refused = project_facts.refusal(facts, in_project, filled)
        if in_project is not None or filled != sent:
            request = InvocationRequest.model_validate(
                {**to_document(request), "input": filled, "project_id": in_project}
            )
        request_doc = to_document(request)
        validate.validate_request(request_doc)  # raises: a malformed request is a caller bug
        invocation_id = request.invocation_id
        with self._running_lock:
            if invocation_id in self._running or self.store.has(invocation_id):
                raise DuplicateInvocation(
                    f"invocation_id {invocation_id} has already been used; "
                    "send each request with a new one"
                )
            self._running.add(invocation_id)
        try:
            return self._run(
                request, request_doc, acting_for, link, given, refused, watch or Watch(None, None)
            )
        finally:
            with self._running_lock:
                self._running.discard(invocation_id)

    def _models_of(self, agent_id: str) -> tuple[ModelUse, ...]:
        """The models the agent's card declares; none for an agent not registered, which `_run`
        refuses."""
        agent = self.registry.get(agent_id)
        if agent is None:
            self.registry.refresh()
            agent = self.registry.get(agent_id)
        return tuple(agent.spec.models) if agent is not None else ()

    def _run(
        self,
        request: InvocationRequest,
        request_doc: dict[str, Any],
        acting_for: Principal,
        link: SpanContext | None,
        given: frozenset[str] = frozenset(),
        unfillable: str | None = None,
        watch: Watch | None = None,
    ) -> Envelope:
        """Run the steps of `dd_harness.pipeline` in order. `given` is the classes of project
        content the conductor put into the input, and `unfillable` why it could not fill it from
        the project, if it could not."""
        agent = self.registry.get(request.agent_id)
        if agent is None:
            self.registry.refresh()  # it may have started since the registry was built
            agent = self.registry.get(request.agent_id)
        if agent is None:
            raise UnknownAgent(
                f"no agent registered as {request.agent_id!r}; known: {self.registry.ids()}"
                + self.registry.not_registered()
            )
        watch = watch or Watch(None, None)
        watch.plan()
        run = pipeline.RunState(
            request, request_doc, acting_for, agent, watch, link, given, unfillable
        )
        spec = agent.spec
        with invoke_agent_span(
            self.tracing.tracer, spec.agent_id, spec.grounding_mode.value, run.input_hash, link=link
        ) as root:
            run.trace_id = format(root.get_span_context().trace_id, "032x")
            for step in pipeline.INSIDE_SPAN:
                step(self, run)
            root.set_attribute(ATTR_OUTCOME, run.finished.outcome.status.value)
        try:
            for step in pipeline.AFTER_SPAN:
                step(self, run)
        finally:
            # spans.jsonl is the durable copy; a long-running server must not keep them all.
            self.tracing.discard(run.trace_id)
        return run.finished

    def _keep_report(self, invocation_id: str, report: grounding.GroundingReport) -> None:
        """Keep the run's grounding report in memory, dropping the oldest past
        `GROUNDING_REPORTS_KEPT`."""
        with self._reports_lock:  # invocations finish side by side
            self.grounding_reports[invocation_id] = report
            while len(self.grounding_reports) > GROUNDING_REPORTS_KEPT:
                del self.grounding_reports[next(iter(self.grounding_reports))]

    def _spans(self, trace_id: str) -> bytes:
        """The trace's finished spans as JSON Lines, the bytes of `spans.jsonl`."""
        with tempfile.TemporaryDirectory(prefix="dd-spans-") as tmp:
            path = Path(tmp) / SPANS
            self.tracing.write_jsonl(path, trace_id)
            return path.read_bytes()


def _span_context(traceparent: str) -> SpanContext | None:
    """The span a W3C `traceparent` names, or None if it names none."""
    from opentelemetry import trace

    ctx = TraceContextTextMapPropagator().extract({"traceparent": traceparent})
    span_context = trace.get_current_span(ctx).get_span_context()
    return span_context if span_context.is_valid else None
