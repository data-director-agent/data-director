"""Validation, the package and its deposit, and a project's escalations to a data steward
(docs/specs/provenance.md, Project log events)."""

from __future__ import annotations

from dd_harness.projects.rules import (
    DEPOSIT_APPROVED,
    DEPOSIT_CHECKS_CONFIRMED,
    DEPOSIT_FAILED,
    DEPOSIT_ITEM_DECIDED,
    DEPOSIT_RECORDED,
    ESCALATION_HANDED_BACK,
    ESCALATION_OPENED,
    ESCALATION_REASSIGNED,
    ESCALATION_RELEASED,
    ESCALATION_REOPENED,
    ESCALATION_REPLIED,
    ESCALATION_REROUTED,
    ESCALATION_RESOLVED,
    ESCALATION_TAKEN,
    ESCALATION_TRANSFERRED,
    ESCALATION_WAITING,
    ESCALATION_WITHDRAWN,
    GATE_CLEARED,
    GATE_REFUSED,
    PACKAGE_BUILT,
    PROJECT_PAUSED,
    PROJECT_RESUMED,
    PROJECT_VALIDATED,
    STEWARD_MESSAGE,
    STEWARD_VIEWED,
    SUPPORT_TEAM_CHOSEN,
)
from dd_harness.provenance_graph.events.base import Context, Event, EventMapping, generated, uses
from dd_harness.provenance_graph.nodes import digest_of, is_digest, ni, ref, uuid_iri, version_id


def _content(ctx: Context, digest: object) -> str | None:
    return ctx.graph.content(str(digest)) if is_digest(digest) else None


def _validated(ctx: Context, activity: str, event: Event) -> None:
    validated = [version_id(d, v) for d, v in sorted(ctx.latest.items())]
    uses(ctx, activity, ctx.inventory, _content(ctx, event.get("requirements_digest")), *validated)
    report = ctx.graph.content(event["digest"], dd__conforms=event.get("conforms"))
    generated(ctx, activity, report, event)


def _package(ctx: Context, activity: str, event: Event) -> None:
    held = [version_id(d["document_id"], d["version"]) for d in event.get("documents") or []]
    runs = [uuid_iri(r) for r in event.get("runs") or []]
    uses(
        ctx,
        activity,
        _content(ctx, event.get("report_digest")),
        _content(ctx, event.get("requirements_digest")),
        _content(ctx, event.get("derived_from")),
        *held,
        *runs,
    )
    package = ctx.graph.content(
        event["digest"],
        schema__encodingFormat=event.get("media_type") or event.get("format"),
        prov__wasDerivedFrom=ref(ni(event["derived_from"]))
        if is_digest(event.get("derived_from"))
        else None,
    )
    generated(ctx, activity, package, event)


def _item(ctx: Context, activity: str, event: Event) -> None:
    item = event.get("item") or {}
    uses(ctx, activity, _content(ctx, event.get("inventory_digest")))
    ctx.graph.put(
        activity,
        schema__about=item.get("path"),
        dd__decision=event.get("decision"),
        schema__description=event.get("note"),
    )


def _checks(ctx: Context, activity: str, event: Event) -> None:
    uses(ctx, activity, _content(ctx, event.get("inventory_digest")))
    ctx.graph.put(activity, schema__description=[s["text"] for s in event.get("statements") or []])


def _deposit_approved(ctx: Context, activity: str, event: Event) -> None:
    uses(ctx, activity, _content(ctx, event.get("digest")), _content(ctx, event.get("item_digest")))
    ctx.graph.put(
        activity,
        dd__repository=event.get("repository_id"),
        dd__transport=event.get("transport"),
        dd__sandbox=event.get("sandbox"),
    )
    ctx.deposit_approvals[event["event_id"]] = activity


def _deposit_outcome(ctx: Context, activity: str, event: Event) -> None:
    """A deposit made or failed, under the approval it names."""
    approval = ctx.deposit_approvals.get(str(event.get("approval")))
    if approval:
        ctx.graph.link(activity, "prov:wasInformedBy", approval)
    uses(ctx, activity, _content(ctx, event.get("digest")), _content(ctx, event.get("item_digest")))
    ctx.graph.put(activity, dd__repository=event.get("repository_id"))
    if event["event"] == DEPOSIT_FAILED:
        ctx.graph.put(
            activity, dd__status=event.get("status"), schema__description=event.get("reason")
        )
        return
    deposit = ctx.graph.put(
        f"{activity}#deposit",
        "prov:Entity",
        schema__identifier=[i for i in (event.get("doi"), event.get("deposit_id")) if i],
        schema__url=event.get("draft_url"),
        prov__wasDerivedFrom=ref(ni(event["item_digest"]))
        if is_digest(event.get("item_digest"))
        else None,
    )
    generated(ctx, activity, deposit, event)


def _team(ctx: Context, activity: str, event: Event) -> None:
    uses(ctx, activity, ctx.project)
    ctx.graph.put(activity, dd__team=event.get("team_id"))


def _note(ctx: Context, activity: str, event: Event, key: str = "note") -> None:
    """A note a person wrote, named by its digest (invariant 5)."""
    if event.get(key):
        note = ctx.graph.content(digest_of(event[key]))
        generated(ctx, activity, note, event)
        ctx.graph.link(activity, "dd:note", note)


def escalation(opened: str) -> str:
    return f"{uuid_iri(opened)}#escalation"


def _opened(ctx: Context, activity: str, event: Event) -> None:
    origin = event.get("origin") or {}
    iri = ctx.graph.put(
        escalation(event["event_id"]),
        "prov:Entity",
        dd__team=event.get("team_id"),
        dd__origin=origin.get("kind"),
        dd__scopeShared=list(event.get("scope_shared") or []),
    )
    generated(ctx, activity, iri, event)
    if origin.get("invocation_id"):
        ctx.graph.link(activity, "prov:wasInformedBy", uuid_iri(origin["invocation_id"]))
    _note(ctx, activity, event)


def _move(ctx: Context, activity: str, event: Event) -> None:
    uses(ctx, activity, escalation(event["escalation_id"]))
    ctx.graph.put(activity, dd__actingAs=event.get("acting_as"))
    _note(ctx, activity, event)


def _rerouted(ctx: Context, activity: str, event: Event) -> None:
    """The escalation sent to its team again, by the deployment, because nobody took it."""
    uses(ctx, activity, escalation(event["escalation_id"]))
    ctx.graph.put(activity, dd__team=event.get("team_id"))


def _reassigned(ctx: Context, activity: str, event: Event) -> None:
    """The escalation given to a colleague in its team, named by their principal's identifier
    alone, as a member is."""
    _move(ctx, activity, event)
    colleague = ctx.graph.put(event["to_steward"]["principal_id"], "prov:Agent")
    ctx.graph.put(activity, dd__steward=ref(colleague))


def _transferred(ctx: Context, activity: str, event: Event) -> None:
    """The escalation sent to another team, from the team it was with."""
    _move(ctx, activity, event)
    ctx.graph.put(activity, dd__team=event.get("team_id"), dd__fromTeam=event.get("from_team"))


def _viewed(ctx: Context, activity: str, event: Event) -> None:
    uses(ctx, activity, ctx.project)
    ctx.graph.put(activity, dd__actingAs=event.get("acting_as"))


def _steward_message(ctx: Context, activity: str, event: Event) -> None:
    uses(ctx, activity, ctx.project)
    ctx.graph.put(activity, dd__actingAs=event.get("acting_as"))
    _note(ctx, activity, event)


def _pause(ctx: Context, activity: str, event: Event) -> None:
    """A pause or its lifting, by the team that holds it, with its reason named by digest."""
    uses(ctx, activity, ctx.project)
    ctx.graph.put(activity, dd__team=event.get("team_id"), dd__actingAs=event.get("acting_as"))
    _note(ctx, activity, event, "reason")


def _gate(ctx: Context, activity: str, event: Event) -> None:
    """A steward's decision on a run the policy gate referred."""
    if event.get("invocation_id"):
        ctx.graph.link(activity, "prov:wasInformedBy", uuid_iri(event["invocation_id"]))
    ctx.graph.put(activity, dd__actingAs=event.get("acting_as"))
    _note(ctx, activity, event, "reason")


MAPPINGS: dict[str, EventMapping] = {
    PROJECT_VALIDATED: EventMapping("dd:ProjectValidation", _validated, harness=True),
    PACKAGE_BUILT: EventMapping("dd:PackageBuild", _package, harness=True),
    DEPOSIT_ITEM_DECIDED: EventMapping("dd:DepositItemDecision", _item),
    DEPOSIT_CHECKS_CONFIRMED: EventMapping("dd:DepositChecksConfirmation", _checks),
    DEPOSIT_APPROVED: EventMapping("dd:DepositApproval", _deposit_approved),
    DEPOSIT_RECORDED: EventMapping("dd:DepositRecording", _deposit_outcome, harness=True),
    DEPOSIT_FAILED: EventMapping("dd:DepositFailure", _deposit_outcome, harness=True),
    SUPPORT_TEAM_CHOSEN: EventMapping("dd:SupportTeamChoice", _team),
    ESCALATION_OPENED: EventMapping("dd:EscalationOpening", _opened),
    ESCALATION_TAKEN: EventMapping("dd:EscalationTaking", _move),
    ESCALATION_RELEASED: EventMapping("dd:EscalationRelease", _move),
    ESCALATION_WAITING: EventMapping("dd:EscalationWaiting", _move),
    ESCALATION_REPLIED: EventMapping("dd:EscalationReply", _move),
    ESCALATION_RESOLVED: EventMapping("dd:EscalationResolution", _move),
    ESCALATION_HANDED_BACK: EventMapping("dd:EscalationHandBack", _move),
    ESCALATION_WITHDRAWN: EventMapping("dd:EscalationWithdrawal", _move),
    ESCALATION_REOPENED: EventMapping("dd:EscalationReopening", _move),
    ESCALATION_REROUTED: EventMapping("dd:EscalationRerouting", _rerouted, harness=True),
    ESCALATION_REASSIGNED: EventMapping("dd:EscalationReassignment", _reassigned),
    ESCALATION_TRANSFERRED: EventMapping("dd:EscalationTransfer", _transferred),
    STEWARD_VIEWED: EventMapping("dd:StewardView", _viewed),
    STEWARD_MESSAGE: EventMapping("dd:StewardMessage", _steward_message),
    PROJECT_PAUSED: EventMapping("dd:ProjectPause", _pause),
    PROJECT_RESUMED: EventMapping("dd:ProjectResumption", _pause),
    GATE_CLEARED: EventMapping("dd:GateClearance", _gate),
    GATE_REFUSED: EventMapping("dd:GateRefusal", _gate),
}
