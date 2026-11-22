"""A project's documents and facts: each version drafted or edited, each decision on one, each
refused change, answer and request to revise, and each fact proposed and decided
(docs/specs/provenance.md, Project log events)."""

from __future__ import annotations

from typing import Any

from dd_harness.document_origin import document_name
from dd_harness.projects.rules import (
    DOCUMENT_CHANGE_REFUSED,
    DOCUMENT_QUESTION_ANSWERED,
    DOCUMENT_REVISION_REQUESTED,
    DOCUMENT_VERSION_ADDED,
    DOCUMENT_VERSION_DECIDED,
    FACT_DECIDED,
    FACT_PROPOSED,
)
from dd_harness.provenance_graph.events.base import (
    Context,
    Event,
    EventMapping,
    generated,
    invalidated,
    uses,
)
from dd_harness.provenance_graph.nodes import agent_iri, digest_of, ref, uuid_iri, version_id

DRAFTED = "dd:VersionDrafting"
EDITED = "dd:VersionEdit"


def version_class(event: Event) -> str:
    """A version an agent drafted, or one a person wrote."""
    return DRAFTED if event.get("drafted_by") else EDITED


def _version(ctx: Context, activity: str, event: Event) -> None:
    document_id, number = event["document_id"], int(event["version"])
    revises = event.get("revises")
    iri = ctx.graph.put(
        version_id(document_id, number),
        "prov:Entity",
        "schema:CreativeWork",
        schema__name=document_name(event["document_kind"], event.get("document_title")),
        schema__additionalType=event["document_kind"],
        schema__encodingFormat=event.get("media_type"),
        schema__sha256=event["digest"],
        schema__version=number,
        prov__wasRevisionOf=ref(version_id(revises["document_id"], revises["version"]))
        if revises
        else None,
    )
    if drafted_by := event.get("drafted_by"):
        # The run generated the version; this event names that generation (The mapping).
        run = uuid_iri(drafted_by["invocation_id"])
        ctx.graph.put(
            iri,
            prov__wasGeneratedBy=ref(run),
            prov__qualifiedGeneration=ref(activity),
            prov__wasAttributedTo=ref(agent_iri(drafted_by["agent_id"])),
            dd__derivation=drafted_by.get("document_derivation"),
        )
    else:
        if revises:
            uses(ctx, activity, version_id(revises["document_id"], revises["version"]))
        generated(ctx, activity, iri, event)
    ctx.versions[(document_id, number)] = event
    ctx.latest[document_id] = max(number, ctx.latest.get(document_id, 0))


def _named_version(event: Event) -> str | None:
    if event.get("document_id") and event.get("version") is not None:
        return version_id(event["document_id"], int(event["version"]))
    return None


def _decided(ctx: Context, activity: str, event: Event) -> None:
    uses(ctx, activity, _named_version(event))
    ctx.graph.put(
        activity, dd__decision=event.get("decision"), schema__description=event.get("reason")
    )
    if event.get("decision") == "approved":
        ctx.approvals[(event["document_id"], int(event["version"]))] = activity


def _refused(ctx: Context, activity: str, event: Event) -> None:
    uses(ctx, activity, _named_version(event))
    ctx.graph.put(activity, dd__refusal=event.get("refusal"))


def _answered(ctx: Context, activity: str, event: Event) -> None:
    uses(ctx, activity, _named_version(event))
    answer = ctx.graph.content(digest_of(event.get("answer_text") or ""))
    ctx.graph.put(activity, dd__question=event.get("question_id"))
    generated(ctx, activity, answer, event)


def _revision_requested(ctx: Context, activity: str, event: Event) -> None:
    uses(ctx, activity, _named_version(event))
    ctx.graph.put(activity, schema__description=event.get("instruction"))


def _fact(ctx: Context, iri: str, fact: dict[str, Any]) -> str:
    """A fact, named by the event that proposed or decided it: two runs may propose the same
    fact, and an entity has one generation."""
    return ctx.graph.put(
        iri,
        "prov:Entity",
        schema__sha256=digest_of(fact),
        dd__factKind=fact.get("fact_kind"),
        dd__factSubject=fact.get("fact_subject"),
    )


def _proposed(ctx: Context, generation: str, event: Event) -> None:
    fact = _fact(ctx, f"{generation}#fact", event["fact"])
    if event.get("agent_id"):
        ctx.graph.put(fact, prov__wasAttributedTo=ref(agent_iri(event["agent_id"])))
    run = ctx.graph.nodes.get(generation, {}).get("prov:activity")
    if run:
        ctx.graph.put(fact, prov__wasGeneratedBy=run[0], prov__qualifiedGeneration=ref(generation))
    else:
        generated(ctx, generation, fact, event)
    ctx.proposals[event["event_id"]] = fact


def _fact_decided(ctx: Context, activity: str, event: Event) -> None:
    proposal = ctx.proposals.get(str(event.get("proposal")))
    uses(ctx, activity, proposal)
    fact = event.get("fact") or {}
    key = (str(fact.get("fact_kind")), str(fact.get("fact_subject")))
    ctx.graph.put(
        activity, dd__decision=event.get("verdict"), schema__description=event.get("reason")
    )
    if event.get("verdict") == "rejected":
        invalidated(ctx, activity, ctx.facts.pop(key, None), event)
        return
    # The fact that stands is this decision's, even where it is the proposal unchanged: an
    # entity has one generation.
    standing = _fact(ctx, f"{activity}#fact", fact)
    if proposal:
        ctx.graph.put(standing, prov__wasDerivedFrom=ref(proposal))
    if (previous := ctx.facts.get(key)) and previous != standing:
        ctx.graph.put(standing, prov__wasRevisionOf=ref(previous))
    generated(ctx, activity, standing, event)
    ctx.facts[key] = standing


MAPPINGS: dict[str, EventMapping] = {
    # A version an agent drafted is a run's generation; one a person wrote is their activity.
    DOCUMENT_VERSION_ADDED: EventMapping(EDITED, _version, generation=True, classify=version_class),
    DOCUMENT_VERSION_DECIDED: EventMapping("dd:VersionDecision", _decided),
    DOCUMENT_CHANGE_REFUSED: EventMapping("dd:ChangeRefusal", _refused),
    DOCUMENT_QUESTION_ANSWERED: EventMapping("dd:QuestionAnswer", _answered),
    DOCUMENT_REVISION_REQUESTED: EventMapping("dd:RevisionRequest", _revision_requested),
    FACT_PROPOSED: EventMapping("dd:FactProposal", _proposed, generation=True),
    FACT_DECIDED: EventMapping("dd:FactDecision", _fact_decided),
}
