"""The conductor: policy gate → input check → agent → grounding linter → source check →
validation → shape check → store → provenance.

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
anything is stored. Before the input is
hashed, the conductor puts the project's facts into an input class that asks for them
(`project_facts`). A run in a project that succeeds with a `Document` is recorded in the project
as a proposed version, caused by the run; a draft the project refuses fails the run instead.

Threads (#171). `invoke` may be called from any thread, and several invocations may run at
once. Async code calls `ainvoke` and `ainvoke_delegated` instead, which keep the one rule that
matters inside the conductor: a parent holds its thread until its children have ended, so the
two run on separate pools and a child never queues behind its parent.
"""

from __future__ import annotations

import asyncio
import functools
import secrets
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from opentelemetry.trace import SpanContext
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from dd_harness import grounding, policy, project_access, project_facts, shacl
from dd_harness import sources as source_check
from dd_harness.projects import ProjectError, UnknownProjectError
from dd_harness.provenance import process_run_crate
from dd_harness.registry import Registry
from dd_harness.remote import Received, RemoteAgent
from dd_harness.storage import (
    CRATE,
    GROUNDING,
    SOURCES,
    SPANS,
    VALIDATION,
    ProjectStorage,
    RunStorage,
)
from dd_sdk.agent import AgentResult, AgentSpec, RunContext, typed_request
from dd_sdk.contract import problem as problems
from dd_sdk.contract import validate
from dd_sdk.contract.models import (
    Delegation,
    Envelope,
    GroundingMode,
    InvocationRequest,
    ModelCall,
    Outcome,
    OutcomeStatus,
    Principal,
    ReasonCode,
    Telemetry,
    input_source_id,
    to_document,
)
from dd_sdk.contract.version import CONTRACT_VERSION
from dd_sdk.delegate import DelegationGrant
from dd_sdk.evidence import envelope_hash
from dd_sdk.evidence import input_hash as compute_input_hash
from dd_sdk.prompts import prompt_digest
from dd_sdk.tracing import (
    ATTR_OUTCOME,
    Tracing,
    invoke_agent_span,
    make_tracing,
    policy_gate_span,
)

DATA_STEWARD = "data_steward"
# The core payload class a run in a project records as a document version.
DOCUMENT = "Document"


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
    # The projects runs may belong to (docs/specs/projects.md). None (most tests, the workbench
    # without DD_PROJECTS_DIR) means no run is in a project.
    projects: ProjectStorage | None = None
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

    async def ainvoke(self, request: InvocationRequest, *, acting_for: Principal) -> Envelope:
        """`invoke`, awaited from async code without blocking its event loop."""
        with self._parents_lock:
            if self._parents is None:
                self._parents = ThreadPoolExecutor(thread_name_prefix="dd-conductor")
            parents = self._parents
        call = functools.partial(self.invoke, request, acting_for=acting_for)
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

    def invoke(self, request: InvocationRequest, *, acting_for: Principal) -> Envelope:
        """Run one top-level invocation on behalf of `acting_for`, the principal the caller's
        transport authenticated. Lineage is the conductor's to set, never the caller's."""
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
        # Only someone who may read the project runs anything in it; anyone else is answered as
        # for a project that does not exist (docs/specs/projects.md, invariant 17). A delegated
        # child is not checked again: its grant carries its parent's project.
        if (
            project_id is not None
            and self.projects is not None
            and not project_access.may(
                self.projects, project_id, acting_for, project_access.Action.READ
            )
        ):
            raise UnknownProjectError(f"no project {project_id!r}")
        return self._invoke(request, acting_for, project_id=project_id)

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
        envelope = self._invoke(
            child, grant.acting_for, link=_span_context(traceparent), project_id=grant.project_id
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

    def _issue_grant(self, request: InvocationRequest, acting_for: Principal) -> Grant:
        grant = Grant(
            token=secrets.token_urlsafe(32),
            parent_invocation_id=request.invocation_id,
            parent_agent_id=request.agent_id,
            conversation_id=request.conversation_id,
            project_id=request.project_id,
            acting_for=acting_for,
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
    ) -> Envelope:
        # The project's facts go in before anything is hashed or stored, so the input hash and
        # request.json cover what the agent was shown; outside a project, what only the conductor
        # may fill is removed (docs/specs/projects.md).
        in_project = project_id if self.projects is not None else None
        sent = to_document(request.input)
        filled = project_facts.give(self.projects, in_project, sent)
        given = project_facts.given(self.projects, in_project, filled)
        refused = project_facts.refusal(self.projects, in_project, filled)
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
            return self._run(request, request_doc, acting_for, link, given, refused)
        finally:
            with self._running_lock:
                self._running.discard(invocation_id)

    def _run(
        self,
        request: InvocationRequest,
        request_doc: dict[str, Any],
        acting_for: Principal,
        link: SpanContext | None,
        given: frozenset[str] = frozenset(),
        unfillable: str | None = None,
    ) -> Envelope:
        """`given` is the classes of project content the conductor put into the input, and
        `unfillable` why it could not fill it from the project, if it could not."""
        agent = self.registry.get(request.agent_id)
        if agent is None:
            self.registry.refresh()  # it may have started since the registry was built
            agent = self.registry.get(request.agent_id)
        if agent is None:
            raise UnknownAgent(
                f"no agent registered as {request.agent_id!r}; known: {self.registry.ids()}"
                + self.registry.not_registered()
            )
        spec = agent.spec
        started = datetime.now(UTC)
        tracer = self.tracing.tracer
        input_hash = compute_input_hash(request_doc["input"])
        # The class schema the card carries for the input, if the agent accepts its class.
        accepted = spec.accepted(str(request_doc["input"].get("schema_class")))
        input_ref = input_source_id(request.invocation_id)

        delegations: list[Delegation] = []
        grant: Grant | None = None
        from_agent = False
        # The agent's model calls and the prompts they name, kept whatever becomes of its result
        # (docs/specs/disclosure.md).
        model_calls: tuple[ModelCall, ...] = ()
        prompts: dict[str, dict[str, Any]] = {}
        with invoke_agent_span(
            tracer, spec.agent_id, spec.grounding_mode.value, input_hash, link=link
        ) as root:
            trace_id = format(root.get_span_context().trace_id, "032x")

            # 1. Policy gate, against the deployment's profile.
            profile = self.profile
            with policy_gate_span(tracer, spec.agent_id):
                decision = policy.gate(profile, spec.agent_id, spec.action_class)
            result: AgentResult
            if not decision.allowed:
                result = AgentResult(
                    outcome=Outcome(
                        status=OutcomeStatus.FAILED,
                        statement=f"{decision.reason}. The agent was not run.",
                    ),
                )
                prob = (
                    problems.action_class_mismatch(
                        spec.agent_id,
                        spec.action_class,
                        profile.agents[spec.agent_id],
                        profile.profile_id,
                    )
                    if decision.refusal == "action-class-mismatch"
                    else problems.agent_not_permitted(spec.agent_id, profile.profile_id)
                )
            elif decision.requires_approval:
                result = AgentResult(
                    outcome=Outcome(
                        status=OutcomeStatus.REFERRED,
                        reason_code=ReasonCode.POLICY_REQUIRES_APPROVAL,
                        referred_to=DATA_STEWARD,
                        statement=f"{decision.reason}. The agent was not run.",
                    )
                )
                prob = None
            elif refused := _input_refusal(spec, request_doc["input"]):
                # 2. Input check, against the class schema the agent's card carries
                # (docs/specs/contract.md).
                # A valid request addressed to an agent that does not read this input is an
                # outcome, not an exception: the caller, the store and a reviewer all see the
                # refusal as an envelope, as they do a policy refusal.
                got, errors = refused
                statement = (
                    f"The input is not a valid {got}: {'; '.join(errors)}."
                    if errors
                    else f"{spec.agent_id} accepts {', '.join(spec.accepts_names())}, not {got}."
                )
                result = AgentResult(
                    outcome=Outcome(
                        status=OutcomeStatus.FAILED,
                        statement=f"{statement} The agent was not run.",
                    )
                )
                prob = problems.input_not_accepted(
                    spec.agent_id, got, spec.accepts_names(), tuple(errors)
                )
            elif unfillable is not None:
                # 3. Project facts: the document a redraft names must be one of the project's,
                # of the kind asked for (docs/specs/projects.md, invariant 6).
                result = AgentResult(
                    outcome=Outcome(
                        status=OutcomeStatus.FAILED,
                        statement=f"{unfillable}. The agent was not run.",
                    )
                )
                prob = problems.revision_refused(unfillable)
            elif kept_back := policy.withheld(
                profile, (model.hosting for model in spec.models), given
            ):
                # 4. Project content, against the profile's `hosted_models`
                # (docs/specs/projects.md, invariant 8): nothing is sent that the profile does not
                # let an agent calling a hosted model see.
                result = AgentResult(
                    outcome=Outcome(
                        status=OutcomeStatus.FAILED,
                        statement=(
                            f"{spec.agent_id} calls a hosted model, and profile "
                            f"{profile.profile_id!r} does not let one be given the project's "
                            f"{' or '.join(kept_back)}. The agent was not run."
                        ),
                    )
                )
                prob = problems.project_content_withheld(
                    spec.agent_id, tuple(kept_back), profile.profile_id
                )
            else:
                # 5. Run the agent. An exception becomes a failed outcome; never a crash.
                prob = None
                # A grant travels on the A2A wire, so only a remote agent can be sent one.
                sent_grant: DelegationGrant | None = None
                if (
                    spec.grounding_mode == GroundingMode.DELEGATION
                    and request.parent_invocation_id is None
                    and self.harness_url is not None
                    and isinstance(agent, RemoteAgent)
                ):
                    grant = self._issue_grant(request, acting_for)
                    sent_grant = DelegationGrant(url=self.harness_url, token=grant.token)
                ctx = RunContext(tracer=tracer, input_ref=input_ref, input_hash=input_hash)
                # The agent is never told which project it works in (docs/specs/projects.md).
                sent = request.model_copy(update={"project_id": None})
                try:
                    # An in-process agent records its spans in this trace already.
                    received = (
                        agent.call(sent, ctx, sent_grant)
                        if isinstance(agent, RemoteAgent)
                        else Received(agent.run(typed_request(spec, sent), ctx))
                    )
                except Exception as exc:  # noqa: BLE001 — converted to a failed outcome by design
                    result = AgentResult(
                        outcome=Outcome(
                            status=OutcomeStatus.FAILED, statement=f"Agent raised: {exc}"
                        )
                    )
                    prob = problems.agent_error(spec.agent_id, exc)
                else:
                    from_agent = True
                    # A remote agent's spans were recorded in its own process; bring them into
                    # this trace so the linter reads one tree (docs/specs/agents.md).
                    self.tracing.import_spans(trace_id, received.spans)
                    result = received.result
                    model_calls = result.model_calls
                    prompts, unmatched = _matched_prompts(result)
                    # An agent that returns a payload other than the class it declared, or one
                    # its own class schema does not admit, or prompts that are not those its
                    # calls name, is contradicting its specification: a programmer error, handled
                    # the same way as an exception.
                    if unmatched:
                        result = AgentResult(
                            outcome=Outcome(
                                status=OutcomeStatus.FAILED,
                                statement=f"Agent contradicted its specification: {unmatched}",
                            )
                        )
                        prob = problems.agent_error(spec.agent_id, ValueError(unmatched))
                    elif result.payload is not None and (
                        mismatch := _payload_mismatch(spec, to_document(result.payload))
                    ):
                        result = AgentResult(
                            outcome=Outcome(
                                status=OutcomeStatus.FAILED,
                                statement=f"Agent contradicted its specification: {mismatch}",
                            )
                        )
                        prob = problems.agent_error(spec.agent_id, mismatch)

            if grant is not None:
                # Recorded whatever the agent did afterwards: the children ran and are stored.
                delegations = self._revoke_grant(grant)

            envelope = Envelope(
                invocation_id=request.invocation_id,
                agent_id=spec.agent_id,
                agent_version=spec.version,
                completed_at=datetime.now(UTC),
                grounding_mode=spec.grounding_mode,
                policy_bundle_ref=profile.ref,
                policy_digest=profile.digest,
                acting_for=acting_for,
                contract_version=CONTRACT_VERSION,
                input_schema=accepted.digest if accepted else None,
                outcome=result.outcome,
                payload=result.payload,
                payload_schema=(
                    spec.payload.digest if result.payload is not None and spec.payload else None
                ),
                evidence=result.evidence,
                telemetry=Telemetry(
                    trace_id=trace_id,
                    model_id=result.model_id,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    model_calls=list(model_calls),
                ),
                problem=prob,
                conversation_id=request.conversation_id,
                project_id=request.project_id,
                parent_invocation_id=request.parent_invocation_id,
                delegations=delegations,
            )
            root.set_attribute(ATTR_OUTCOME, envelope.outcome.status.value)

        try:
            # 6. Grounding linter, over the finished tree of this trace.
            records = self.tracing.finished_records(trace_id)
            report = grounding.lint(records, envelope.to_document())
            with self._reports_lock:  # invocations finish side by side
                self.grounding_reports[request.invocation_id] = report
                while len(self.grounding_reports) > GROUNDING_REPORTS_KEPT:
                    del self.grounding_reports[next(iter(self.grounding_reports))]
            # 6a. Source check, over the evidence the linter has just read
            # (docs/specs/grounding.md).
            source_report = source_check.check(envelope.to_document(), self.sources)
            withheld = [
                (check, found)
                for check, found in (
                    ("the grounding linter", report.violations),
                    ("the source check", source_report.violations),
                )
                if found
            ]
            if withheld and envelope.outcome.status == OutcomeStatus.SUCCEEDED:
                violations = [v for _, found in withheld for v in found]
                envelope = envelope.model_copy(
                    update={
                        "outcome": Outcome(
                            status=OutcomeStatus.FAILED,
                            statement="Output withheld: it failed "
                            + " and ".join(check for check, _ in withheld)
                            + ". "
                            + "; ".join(violations),
                        ),
                        "payload": None,
                        "payload_schema": None,
                        "evidence": [],
                        "problem": problems.grounding_violation(violations),
                    }
                )

            # 7. Validate, store, trace file, provenance. A result the agent returned that still
            # breaks the contract is the agent's error, as a payload of the wrong class is: it is
            # stored as failed(agent-error), not raised past the store. An envelope the conductor
            # built itself that breaks the contract is a conductor bug, and raises.
            doc = envelope.to_document()
            if from_agent:
                try:
                    validate.validate_envelope(doc)
                except validate.ContractViolation as exc:
                    envelope = envelope.model_copy(
                        update={
                            "outcome": Outcome(
                                status=OutcomeStatus.FAILED,
                                statement="Agent result violates the contract: "
                                + "; ".join(exc.messages),
                            ),
                            "payload": None,
                            "payload_schema": None,
                            "evidence": [],
                            "problem": problems.agent_error(spec.agent_id, exc),
                        }
                    )
                    doc = envelope.to_document()
            validate.validate_envelope(doc)
            # 7a. A draft in a project becomes a proposed version of it, caused by this run. A
            # draft the project refuses fails the run, and that failed run is the record.
            if (
                self.projects is not None
                and envelope.project_id is not None
                and envelope.outcome.status == OutcomeStatus.SUCCEEDED
                and doc.get("payload", {}).get("schema_class") == DOCUMENT
            ):
                try:
                    self.projects.record_draft(envelope.project_id, envelope)
                except ProjectError as exc:
                    envelope = envelope.model_copy(
                        update={
                            "outcome": Outcome(
                                status=OutcomeStatus.FAILED,
                                statement=f"The draft was not kept in the project: {exc}.",
                            ),
                            "payload": None,
                            "payload_schema": None,
                            "evidence": [],
                            "problem": problems.revision_refused(str(exc)),
                        }
                    )
                    doc = envelope.to_document()
                    validate.validate_envelope(doc)
            # The schemas the run was checked against, kept by digest for the viewer
            # (docs/specs/contract.md).
            checked = [accepted] if accepted else []
            if envelope.payload is not None and spec.payload is not None:
                checked.append(spec.payload)
            # 7b. The payload against its class's SHACL shapes. Reported, never withheld.
            shapes_report: bytes | None = None
            if (
                envelope.payload is not None
                and spec.payload is not None
                and spec.payload.shapes is not None
            ):
                shapes_report = shacl.validate_payload(
                    envelope.invocation_id,
                    doc["payload"],
                    spec.payload,
                    envelope.completed_at,
                ).report_bytes()
            # Everything else a run keeps is a named artifact beside it (docs/specs/storage.md).
            self.store.append(doc, request_doc, checked, prompts)
            run_id = envelope.invocation_id
            spans = self._spans(trace_id)
            self.store.put_artifact(run_id, SPANS, spans)
            self.store.put_artifact(run_id, GROUNDING, (report.summary() + "\n").encode())
            self.store.put_artifact(run_id, SOURCES, (source_report.summary() + "\n").encode())
            if shapes_report is not None:
                self.store.put_artifact(run_id, VALIDATION, shapes_report)
            if self.write_crate:
                crate = process_run_crate(doc, request_doc, spans, started, shapes_report)
                for name, data in crate.items():
                    self.store.put_artifact(run_id, f"{CRATE}/{name}", data)
        finally:
            # spans.jsonl is the durable copy; a long-running server must not keep them all.
            self.tracing.discard(trace_id)
        return envelope

    def _spans(self, trace_id: str) -> bytes:
        """The trace's finished spans as JSON Lines, the bytes of `spans.jsonl`."""
        with tempfile.TemporaryDirectory(prefix="dd-spans-") as tmp:
            path = Path(tmp) / SPANS
            self.tracing.write_jsonl(path, trace_id)
            return path.read_bytes()


def _input_refusal(spec: AgentSpec, document: dict[str, Any]) -> tuple[str, list[str]] | None:
    """Why the agent will not read this input: the class it names, and how the input fails that
    class's schema (no errors: the agent does not accept the class at all). None if it will."""
    got = str(document.get("schema_class"))
    accepted = spec.accepted(got)
    if accepted is None:
        return got, []
    errors = accepted.errors(document)
    return (got, errors) if errors else None


def _matched_prompts(result: AgentResult) -> tuple[dict[str, dict[str, Any]], str | None]:
    """The prompts the result's model calls name, each checked against its digest, and what is
    wrong if the prompts are not exactly those (docs/specs/disclosure.md). Only prompts that hash
    to their key are kept."""
    kept = {
        digest: dict(prompt)
        for digest, prompt in result.prompts.items()
        if prompt_digest(prompt) == digest
    }
    named = {call.prompt_digest for call in result.model_calls}
    problems_found = []
    if wrong := sorted(set(result.prompts) - set(kept)):
        problems_found.append(f"prompts that do not hash to their digest: {', '.join(wrong)}")
    if missing := sorted(named - set(kept)):
        problems_found.append(f"model calls whose prompt was not returned: {', '.join(missing)}")
    if extra := sorted(set(kept) - named):
        problems_found.append(f"prompts no model call names: {', '.join(extra)}")
        kept = {d: p for d, p in kept.items() if d in named}
    return kept, "; ".join(problems_found) or None


def _payload_mismatch(spec: AgentSpec, document: dict[str, Any]) -> TypeError | None:
    """How a returned payload contradicts the agent's declared payload class, or None."""
    got = document.get("schema_class")
    if spec.payload is None or got != spec.payload.name:
        declared = spec.payload.name if spec.payload else "none"
        return TypeError(f"returned {got}, declared {declared}")
    errors = spec.payload.errors(document)
    if errors:
        return TypeError(f"returned a {got} its class schema does not admit: {'; '.join(errors)}")
    return None


def _span_context(traceparent: str) -> SpanContext | None:
    """The span a W3C `traceparent` names, or None if it names none."""
    from opentelemetry import trace

    ctx = TraceContextTextMapPropagator().extract({"traceparent": traceparent})
    span_context = trace.get_current_span(ctx).get_span_context()
    return span_context if span_context.is_valid else None
