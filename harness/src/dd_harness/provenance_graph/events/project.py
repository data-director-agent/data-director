"""The project's own events: its lifecycle and conversations, what it holds, who is in it, the
repository chosen and the flow a person follows (docs/specs/provenance.md, Project log
events)."""

from __future__ import annotations

from dd_harness.progress import ENTRY_CHOSEN, INTAKE_ANSWERED, INTAKE_DISMISSED, STEP_MARKED
from dd_harness.projects.rules import (
    CONVERSATION_DELETED,
    CONVERSATION_RESTORED,
    CONVERSATION_STARTED,
    DOCUMENTATION_ADDED,
    INVENTORY_ADDED,
    MEMBER_ADDED,
    MEMBER_REMOVED,
    MEMBER_ROLE_CHANGED,
    PROJECT_CREATED,
    PROJECT_DELETED,
    PROJECT_RENAMED,
    PROJECT_RESTORED,
    REPOSITORY_CHOSEN,
    RESEARCHER_ADDED,
    RESEARCHER_WITHDRAWN,
)
from dd_harness.provenance_graph.events.base import (
    Context,
    Event,
    EventMapping,
    conversation,
    generated,
    invalidated,
    uses,
)
from dd_harness.provenance_graph.nodes import digest_of, is_digest, ni, ref


def _created(ctx: Context, activity: str, event: Event) -> None:
    ctx.graph.put(ctx.project, "prov:Entity", schema__name=event.get("title"))
    generated(ctx, activity, ctx.project, event)


def _renamed(ctx: Context, activity: str, event: Event) -> None:
    uses(ctx, activity, ctx.project)
    ctx.graph.put(
        activity, schema__name=event.get("title"), dd__titleSource=event.get("title_source")
    )


def _uses_project(ctx: Context, activity: str, event: Event) -> None:
    uses(ctx, activity, ctx.project)


def _conversation_started(ctx: Context, activity: str, event: Event) -> None:
    iri = ctx.graph.put(
        conversation(event["conversation_id"]),
        "prov:Entity",
        schema__isPartOf=ref(ctx.project),
    )
    generated(ctx, activity, iri, event)


def _uses_conversation(ctx: Context, activity: str, event: Event) -> None:
    uses(ctx, activity, conversation(event["conversation_id"]))


def _inventory(ctx: Context, activity: str, event: Event) -> None:
    previous = ni(event["revises"]) if is_digest(event.get("revises")) else ctx.inventory
    inventory = ctx.graph.content(
        event["digest"], prov__wasRevisionOf=ref(previous) if previous else None
    )
    generated(ctx, activity, inventory, event)
    ctx.inventory = inventory


def _documentation(ctx: Context, activity: str, event: Event) -> None:
    source = (
        ctx.graph.content(
            event["source_digest"], schema__encodingFormat=event.get("source_media_type")
        )
        if is_digest(event.get("source_digest"))
        else None
    )
    documentation = ctx.graph.content(
        event["digest"],
        schema__name=event.get("name"),
        schema__encodingFormat=event.get("media_type"),
        prov__wasDerivedFrom=ref(source) if source else None,
    )
    uses(ctx, activity, source)
    generated(ctx, activity, documentation, event)


def _researcher_added(ctx: Context, activity: str, event: Event) -> None:
    facts = ctx.graph.content(event["digest"], schema__about=ref(event["orcid_id"]))
    generated(ctx, activity, facts, event)
    ctx.researchers[event["orcid_id"]] = facts


def _researcher_withdrawn(ctx: Context, activity: str, event: Event) -> None:
    invalidated(ctx, activity, ctx.researchers.pop(event["orcid_id"], None), event)


def _member(ctx: Context, activity: str, event: Event) -> None:
    """A member is named by their principal's identifier alone; the log keeps no more."""
    member = ctx.graph.put(event["member_id"], "prov:Agent")
    uses(ctx, activity, ctx.project)
    ctx.graph.put(activity, dd__member=ref(member), dd__role=event.get("role"))


def _repository(ctx: Context, activity: str, event: Event) -> None:
    record = (
        ctx.graph.content(
            event["record_hash"],
            schema__name=event.get("repository_name"),
            schema__identifier=event.get("re3data_id") or event.get("repository_id"),
        )
        if is_digest(event.get("record_hash"))
        else None
    )
    sets = [
        ctx.graph.content(s["sha256"], schema__name=s.get("ref"))
        for s in [*(event.get("requirement_sets") or []), event.get("standard") or {}]
        if is_digest(s.get("sha256"))
    ]
    uses(ctx, activity, record, *sets)
    merged = ctx.graph.content(
        event["digest"], prov__wasDerivedFrom=[ref(s) for s in ([record] if record else []) + sets]
    )
    generated(ctx, activity, merged, event)
    ctx.requirements = merged


def _entry(ctx: Context, activity: str, event: Event) -> None:
    ctx.graph.put(activity, dd__entry=event.get("entry"), dd__entrySource=event.get("entry_source"))


def _step(ctx: Context, activity: str, event: Event) -> None:
    ctx.graph.put(activity, dd__step=event.get("step_id"), dd__mark=event.get("mark"))


def _intake_answered(ctx: Context, activity: str, event: Event) -> None:
    answer = ctx.graph.content(digest_of(event.get("answer_values") or []))
    ctx.graph.put(activity, dd__question=event.get("question_id"))
    generated(ctx, activity, answer, event)


MAPPINGS: dict[str, EventMapping] = {
    PROJECT_CREATED: EventMapping("dd:ProjectCreation", _created),
    PROJECT_RENAMED: EventMapping("dd:ProjectRenaming", _renamed),
    PROJECT_DELETED: EventMapping("dd:ProjectDeletion", _uses_project),
    PROJECT_RESTORED: EventMapping("dd:ProjectRestoration", _uses_project),
    CONVERSATION_STARTED: EventMapping("dd:ConversationStart", _conversation_started),
    CONVERSATION_DELETED: EventMapping("dd:ConversationDeletion", _uses_conversation),
    CONVERSATION_RESTORED: EventMapping("dd:ConversationRestoration", _uses_conversation),
    INVENTORY_ADDED: EventMapping("dd:InventoryAddition", _inventory),
    DOCUMENTATION_ADDED: EventMapping("dd:DocumentationAddition", _documentation),
    RESEARCHER_ADDED: EventMapping("dd:ResearcherFactsAddition", _researcher_added),
    RESEARCHER_WITHDRAWN: EventMapping("dd:ResearcherFactsWithdrawal", _researcher_withdrawn),
    MEMBER_ADDED: EventMapping("dd:MemberAddition", _member),
    MEMBER_ROLE_CHANGED: EventMapping("dd:MemberRoleChange", _member),
    MEMBER_REMOVED: EventMapping("dd:MemberRemoval", _member),
    REPOSITORY_CHOSEN: EventMapping("dd:RepositoryChoice", _repository),
    ENTRY_CHOSEN: EventMapping("dd:EntryChoice", _entry),
    STEP_MARKED: EventMapping("dd:StepMarking", _step),
    INTAKE_ANSWERED: EventMapping("dd:IntakeAnswer", _intake_answered),
    INTAKE_DISMISSED: EventMapping("dd:IntakeDismissal"),
}
