"""Each event of the project log as PROV (docs/specs/provenance.md, The mapping).

The common rule: an event a person caused is a `prov:Activity` at the event's IRI, associated
with the principal it acted for, at the event's time, with `dd:causedBy` the command or request.
An event a run caused is either the generation of what the run produced (a drafted version, a
proposed fact), or an activity that `prov:wasInformedBy` the run and is associated with the run's
agent. Where the harness carried the action out, it is associated too, and acts for the
principal in that activity alone (invariant 4). Each event type's mapping adds what it used and
generated.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from dd_harness.provenance_graph.events import deposit, documents, project
from dd_harness.provenance_graph.events.base import Context, Event, EventMapping
from dd_harness.provenance_graph.nodes import agent_iri, dt, ref, uuid_iri
from dd_sdk.contract.models import UUID7_PATTERN

MAPPINGS: dict[str, EventMapping] = {
    **project.MAPPINGS,
    **documents.MAPPINGS,
    **deposit.MAPPINGS,
}
_RUN = re.compile(UUID7_PATTERN)


def run_of(event: Event) -> str | None:
    """The invocation id of the run that caused `event`, or None if a person did."""
    if drafted_by := event.get("drafted_by"):
        return str(drafted_by["invocation_id"])
    caused_by = str(event.get("caused_by", ""))
    return caused_by if _RUN.fullmatch(caused_by) else None


def runs_named(events: Iterable[Event]) -> dict[str, tuple[Event, str | None]]:
    """Every run the log names, with the first event that names it and the agent an event says
    ran it, where one says."""
    named: dict[str, tuple[Event, str | None]] = {}

    def name(invocation_id: object, event: Event, agent_id: object = None) -> None:
        if not isinstance(invocation_id, str):
            return
        first, known = named.get(invocation_id, (event, None))
        named[invocation_id] = (first, known or (str(agent_id) if agent_id else None))

    for event in events:
        drafted_by = event.get("drafted_by") or {}
        name(run_of(event), event, drafted_by.get("agent_id") or event.get("agent_id"))
        for invocation_id in event.get("runs") or []:
            name(invocation_id, event)
        origin = event.get("origin") or {}
        name(origin.get("invocation_id"), event, origin.get("agent_id"))
    return named


def map_event(ctx: Context, event: Event) -> str:
    """`event`, by the common rule and its type's mapping. Raises `KeyError` for an event type
    with no mapping: every type the log can hold has one (invariant 2)."""
    mapping = MAPPINGS[event["event"]]
    iri = uuid_iri(event["event_id"])
    graph, run_id = ctx.graph, run_of(event)
    run = uuid_iri(run_id) if run_id else None
    if run and mapping.generation:
        graph.put(
            iri,
            "prov:Generation",
            mapping.class_of(event),
            prov__activity=ref(run),
            prov__atTime=dt(event["at"]),
        )
    else:
        graph.put(
            iri,
            "prov:Activity",
            mapping.class_of(event),
            prov__startedAtTime=dt(event["at"]),
            prov__endedAtTime=dt(event["at"]),
        )
        if run and run_id:
            graph.link(iri, "prov:wasInformedBy", run)
            if agent_id := ctx.agents.get(run_id):
                agent = agent_iri(agent_id)
                graph.link(iri, "prov:wasAssociatedWith", agent)
                graph.acting_for(agent, iri, event["acted_for"])
        else:
            graph.link(iri, "prov:wasAssociatedWith", graph.principal(event["acted_for"]))
            graph.put(iri, dd__causedBy=event.get("caused_by"))
        if mapping.harness:
            harness = graph.harness()
            graph.link(iri, "prov:wasAssociatedWith", harness)
            graph.acting_for(harness, iri, event["acted_for"])
    mapping.adds(ctx, iri, event)
    return iri
