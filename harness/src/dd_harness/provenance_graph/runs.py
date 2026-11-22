"""A project's runs in its provenance graph (docs/specs/provenance.md, Runs and what happens
within them).

A run is a `dd:Invocation` associated with its agent, which acts for the run's principal through
a delegation tied to that run alone (invariant 4). Within it are its model calls, the child runs
it delegated to, its retrievals and tool calls, and the policy gate's decision where the gate
refused or referred it. Each is an activity the run `prov:wasInformedBy`.

The checks (the grounding linter, the source check, the shape check) and conversation turns are
not read yet, TODO(#800, #801).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dd_harness.provenance_graph.nodes import (
    Graph,
    agent_iri,
    dt,
    is_digest,
    model_iri,
    ref,
    uuid_iri,
)
from dd_harness.storage import RunStorage
from dd_sdk.evidence import input_hash

CRATE = "crate/ro-crate-metadata.json"
# The problems the policy gate refuses a run with (dd_sdk.contract.problem), and the reason code
# it refers one with (dd_harness.refusals).
GATE_REFUSALS = frozenset(
    {
        "agent-not-permitted",
        "action-class-mismatch",
        "setting-not-declared",
        "model-broker-bypassed",
    }
)
GATE_REFERRAL = "policy_requires_approval"


def add_run(graph: Graph, runs: RunStorage, envelope: Mapping[str, Any]) -> str:
    """The run `envelope` records, with what happened within it."""
    run = uuid_iri(envelope["invocation_id"])
    agent = put_agent(graph, envelope["agent_id"])
    outcome = envelope.get("outcome") or {}
    problem = envelope.get("problem") or {}
    graph.put(
        run,
        "prov:Activity",
        "dd:Invocation",
        prov__wasAssociatedWith=ref(agent),
        schema__softwareVersion=envelope.get("agent_version"),
        prov__endedAtTime=dt(envelope["completed_at"]) if envelope.get("completed_at") else None,
        dd__outcome=outcome.get("status"),
        dd__reasonCode=outcome.get("reason_code"),
        dd__referredTo=outcome.get("referred_to"),
        dd__problem=ref(problem["type"]) if problem.get("type") else None,
    )
    graph.acting_for(agent, run, envelope["acting_for"])
    if parent := envelope.get("parent_invocation_id"):
        graph.put(run, dd__parentInvocation=ref(uuid_iri(parent)))
        graph.link(uuid_iri(parent), "prov:wasInformedBy", run)
    policy = _policy(graph, envelope)
    request = runs.get_request(envelope["invocation_id"])
    if request is not None and "input" in request:
        graph.link(run, "prov:used", graph.content(input_hash(request["input"])))
    if policy:
        graph.link(run, "prov:used", policy)
    if runs.get_artifact(envelope["invocation_id"], CRATE) is not None:
        crate = graph.put(
            f"{run}#process-run-crate",
            "prov:Entity",
            schema__name="Process Run Crate",
            schema__encodingFormat="application/ld+json",
        )
        graph.link(run, "prov:has_provenance", crate)
    _model_calls(graph, run, envelope)
    _delegations(graph, run, envelope)
    _retrievals(graph, run, agent, envelope)
    _tool_calls(graph, run, agent, envelope)
    _gate(graph, run, policy, outcome, problem)
    return run


def named_run(
    graph: Graph, invocation_id: str, acted_for: Mapping[str, Any] | None, agent_id: str | None
) -> str:
    """A run the log names that the run store does not hold: what the log says of it."""
    run = graph.put(uuid_iri(invocation_id), "prov:Activity", "dd:Invocation")
    if agent_id:
        agent = put_agent(graph, agent_id)
        graph.put(run, prov__wasAssociatedWith=ref(agent))
        if acted_for:
            graph.acting_for(agent, run, acted_for)
    return run


def put_agent(graph: Graph, agent_id: str) -> str:
    return graph.put(
        agent_iri(agent_id),
        "prov:SoftwareAgent",
        "schema:SoftwareApplication",
        schema__name=agent_id,
    )


def _policy(graph: Graph, envelope: Mapping[str, Any]) -> str | None:
    digest = envelope.get("policy_digest")
    if not is_digest(digest):
        return None
    return graph.content(
        str(digest), "prov:Plan", schema__name=envelope.get("policy_bundle_ref") or None
    )


def _model_calls(graph: Graph, run: str, envelope: Mapping[str, Any]) -> None:
    """Each call to a model, as in the disclosure (docs/specs/disclosure.md, invariant 7)."""
    telemetry = envelope.get("telemetry") or {}
    calls = list(telemetry.get("model_calls") or [])
    if not calls and telemetry.get("model_id"):
        # A run stored before calls were recorded names its model only.
        calls = [{"model_provider": "", "model_id": telemetry["model_id"]}]
    for n, call in enumerate(calls, start=1):
        model = graph.put(
            model_iri(call.get("model_provider", ""), call["model_id"]),
            "prov:SoftwareAgent",
            "schema:SoftwareApplication",
            schema__name=call["model_id"],
            schema__provider=call.get("model_provider") or None,
        )
        iri = graph.put(
            f"{run}#model-call-{n}",
            "prov:Activity",
            prov__wasAssociatedWith=ref(model),
            prov__startedAtTime=dt(call["called_at"]) if call.get("called_at") else None,
            dd__modelAccount=call.get("model_account"),
        )
        if is_digest(digest := call.get("prompt_digest")):
            prompt = graph.content(
                str(digest), "prov:Plan", schema__name="Prompt sent to the model"
            )
            association = graph.put(
                f"{iri}-association",
                "prov:Association",
                prov__agent=ref(model),
                prov__hadPlan=ref(prompt),
            )
            graph.link(iri, "prov:used", prompt)
            graph.link(iri, "prov:qualifiedAssociation", association)
        graph.link(run, "prov:wasInformedBy", iri)


def _delegations(graph: Graph, run: str, envelope: Mapping[str, Any]) -> None:
    """Each child run, which the parent `prov:wasInformedBy`. A child the store holds is added
    from its own envelope; this records what the parent's envelope says of it."""
    for delegation in envelope.get("delegations") or []:
        child = uuid_iri(delegation["delegated_invocation_id"])
        agent = put_agent(graph, delegation["delegated_agent_id"])
        graph.put(
            child,
            "prov:Activity",
            "dd:Invocation",
            prov__wasAssociatedWith=ref(agent),
            dd__parentInvocation=ref(run),
        )
        graph.acting_for(agent, child, envelope["acting_for"])
        graph.link(run, "prov:wasInformedBy", child)


def _retrievals(graph: Graph, run: str, agent: str, envelope: Mapping[str, Any]) -> None:
    """Each item of evidence, as the agent reported retrieving it (TODO(#246))."""
    for n, item in enumerate(envelope.get("evidence") or [], start=1):
        iri = f"{run}#retrieval-{n}"
        digest = item.get("content_hash")
        evidence = (
            graph.content(str(digest), dd__sourceId=item.get("source_id"))
            if is_digest(digest)
            else graph.put(f"{run}#evidence-{n}", "prov:Entity", dd__sourceId=item.get("source_id"))
        )
        source = item.get("source_uri")
        graph.put(
            iri,
            "prov:Activity",
            prov__wasAssociatedWith=ref(agent),
            prov__used=ref(source) if source and ":" in source else None,
            prov__endedAtTime=dt(item["retrieved_at"]) if item.get("retrieved_at") else None,
        )
        graph.put(evidence, prov__wasGeneratedBy=ref(iri))
        graph.link(run, "prov:wasInformedBy", iri)
        graph.link(run, "prov:used", evidence)


def _tool_calls(graph: Graph, run: str, agent: str, envelope: Mapping[str, Any]) -> None:
    """Each call to a tool through the gateway, as the conductor recorded it."""
    for n, call in enumerate(envelope.get("tool_retrievals") or [], start=1):
        iri = graph.put(
            f"{run}#tool-{n}",
            "prov:Activity",
            prov__wasAssociatedWith=ref(agent),
            schema__name=call.get("tool_name"),
            dd__toolServer=call.get("tool_server"),
            prov__endedAtTime=dt(call["retrieved_at"]) if call.get("retrieved_at") else None,
        )
        if is_digest(digest := call.get("content_hash")):
            result = graph.content(str(digest), dd__sourceId=call.get("source_id"))
            graph.put(result, prov__wasGeneratedBy=ref(iri))
            graph.link(run, "prov:used", result)
        graph.link(run, "prov:wasInformedBy", iri)


def _gate(
    graph: Graph,
    run: str,
    policy: str | None,
    outcome: Mapping[str, Any],
    problem: Mapping[str, Any],
) -> None:
    """The policy gate's decision, where it refused or referred the run (invariant 8)."""
    slug = str(problem.get("type", "")).rsplit("/", 1)[-1]
    if slug in GATE_REFUSALS:
        decision = "refused"
    elif outcome.get("status") == "referred" and outcome.get("reason_code") == GATE_REFERRAL:
        decision = "referred"
    else:
        return
    gate = graph.put(
        f"{run}#policy-gate",
        "prov:Activity",
        prov__wasAssociatedWith=ref(graph.harness()),
        prov__used=ref(policy) if policy else None,
        dd__decision=decision,
    )
    graph.link(run, "prov:wasInformedBy", gate)
