"""A data steward's actions in a project, as every way in reaches them
(docs/specs/stewardship.md, invariants 2, 3 and 6 to 8).

Each function checks the steward's access (`dd_harness.steward_access`) and the action against
the closed list of invariant 6 before anything happens, then records it in the project's log
(`dd_harness.projects.stewarding`) naming the steward:

- someone with no steward access to the project, or no such project, is answered as for a project
  that does not exist (`UnknownProjectError`), so that a refusal does not reveal whether it does;
- a member of the project, steward or not, is refused every steward action
  (`StewardRefusal.MEMBER_OF_PROJECT`): a member acts as a member (invariant 2), and a researcher
  cannot take a steward's action by any route;
- a steward whose access does not open the action is refused (`StewardRefusal.NOT_PERMITTED`).

Each read recorded, and each action taken, is also a security event (`steward.viewed`,
`steward.acted`, docs/specs/security.md) naming the steward, the project and the action, never a
note's text; a refusal records none. `read` records a steward's read, and is how the app's project
routes reach a steward.
`permitted_actions` says what the signed-in person may do in a project and why the rest is
refused, so that the shell renders what the harness decides (invariant 6, "Boundaries").
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Final

from dd_harness.escalation_api import check_origin
from dd_harness.policy import Profile
from dd_harness.project_access import Action, allowed, role_in, roles
from dd_harness.projects import (
    EscalationRefusedError,
    StewardRefusal,
    StewardRefusedError,
    UnknownProjectError,
)
from dd_harness.steward_access import ACTIONS, StewardAccess, StewardAction, access_in
from dd_harness.steward_storage import GateDecision, ProposedEdit
from dd_harness.storage import ProjectStorage
from dd_sdk.contract.models import DocumentVersionRef, Principal
from dd_sdk.security_log import SecurityEvent, emit

type EnvelopeOf = Callable[[str], Mapping[str, Any] | None]

# Why a researcher's action is not open to a steward: a steward is never a member.
NOT_A_MEMBER: Final = "not-a-member"

SERVICE: Final = "harness"


def _audit(steward: Principal, project_id: str, action: StewardAction | None = None) -> None:
    """The security event for a steward's read (`action` None) or action in another person's
    project, beside its event in the project's log."""
    event = SecurityEvent.STEWARD_VIEWED if action is None else SecurityEvent.STEWARD_ACTED
    extra = {} if action is None else {"action": action}
    emit(
        event,
        outcome="success",
        service=SERVICE,
        principal=steward.principal_id,
        project_id=project_id,
        **extra,
    )


def record_view(
    store: ProjectStorage, project_id: str, steward: Principal, *, caused_by: str
) -> None:
    """Record `steward`'s read of the project, at most once a day, in its log and the security
    log."""
    if store.record_view(project_id, acted_for=steward, caused_by=caused_by):
        _audit(steward, project_id)


def reach(
    store: ProjectStorage,
    profile: Profile,
    project_id: str,
    steward: Principal,
    action: StewardAction,
) -> StewardAccess:
    """`steward`'s access to the project, checked for `action`. Raises `UnknownProjectError` and
    `StewardRefusedError` as the module says."""
    if not store.exists(project_id):
        raise UnknownProjectError(f"no project {project_id!r}")
    events = store.events(project_id)
    if steward.principal_id in roles(events):
        raise StewardRefusedError(
            StewardRefusal.MEMBER_OF_PROJECT,
            "you are a member of this project, so you act in it as a member, not as its steward",
        )
    found = access_in(profile, events, steward)
    if found is None:
        raise UnknownProjectError(f"no project {project_id!r}")
    if (why := found.refusal(action)) is not None:
        raise StewardRefusedError(
            StewardRefusal.NOT_PERMITTED,
            f"a steward may not {action.replace('_', ' ')} in this project now ({why})",
        )
    return found


def read(
    store: ProjectStorage,
    profile: Profile,
    project_id: str,
    reader: Principal,
    *,
    caused_by: str,
) -> StewardAccess | None:
    """`reader`'s steward access to the project, recording their read (at most once a day), or
    None, recording nothing, for someone without it (a member included)."""
    if not store.exists(project_id):
        return None
    found = access_in(profile, store.events(project_id), reader)
    if found is not None:
        record_view(store, project_id, reader, caused_by=caused_by)
    return found


def message(
    store: ProjectStorage,
    profile: Profile,
    project_id: str,
    note: str,
    *,
    acted_for: Principal,
    caused_by: str,
) -> dict[str, Any]:
    """Write to the researcher as the project's steward."""
    reach(store, profile, project_id, acted_for, "message")
    event = store.steward_message(project_id, note, acted_for=acted_for, caused_by=caused_by)
    _audit(acted_for, project_id, "message")
    return event


def pause(
    store: ProjectStorage,
    profile: Profile,
    project_id: str,
    reason: str,
    *,
    acted_for: Principal,
    caused_by: str,
) -> dict[str, Any]:
    """Pause the project for the steward's team with the matter escalated to it (invariant 8)."""
    found = reach(store, profile, project_id, acted_for, "pause")
    team_id = min(found.escalated_teams)
    paused = store.pause(project_id, team_id, reason, acted_for=acted_for, caused_by=caused_by)
    _audit(acted_for, project_id, "pause")
    return paused


def resume(
    store: ProjectStorage,
    profile: Profile,
    project_id: str,
    reason: str,
    *,
    acted_for: Principal,
    caused_by: str,
) -> None:
    """Lift the project's pause, which the steward's team holds (invariant 8)."""
    found = reach(store, profile, project_id, acted_for, "resume")
    store.resume(project_id, found.teams, reason, acted_for=acted_for, caused_by=caused_by)
    _audit(acted_for, project_id, "resume")


def decide_gate(
    store: ProjectStorage,
    profile: Profile,
    project_id: str,
    decision: GateDecision,
    envelope_of: EnvelopeOf,
    *,
    acted_for: Principal,
    caused_by: str,
) -> dict[str, Any]:
    """Clear or refuse a run of this project that the policy gate referred (invariant 7). Raises
    `StewardRefusedError` for a run that is not such a referral."""
    action: StewardAction = "clear_gate" if decision.verdict == "cleared" else "refuse_gate"
    reach(store, profile, project_id, acted_for, action)
    named = {"kind": "policy_gate", "invocation_id": decision.invocation_id}
    try:
        check_origin(named, project_id, envelope_of)
    except EscalationRefusedError as exc:
        raise StewardRefusedError(StewardRefusal.NOT_REFERRED, exc.detail) from exc
    decided = store.decide_gate(project_id, decision, acted_for=acted_for, caused_by=caused_by)
    _audit(acted_for, project_id, action)
    return decided


def propose_edit(
    store: ProjectStorage,
    profile: Profile,
    project_id: str,
    edit: ProposedEdit,
    *,
    acted_for: Principal,
    caused_by: str,
) -> DocumentVersionRef:
    """Propose a new version of a document as the project's steward, which its owners approve or
    reject."""
    reach(store, profile, project_id, acted_for, "propose_edit")
    proposed = store.propose_edit(project_id, edit, acted_for=acted_for, caused_by=caused_by)
    _audit(acted_for, project_id, "propose_edit")
    return proposed


def permitted_actions(
    store: ProjectStorage, profile: Profile, project_id: str, principal: Principal
) -> dict[str, Any]:
    """What `principal` may do in the project, as whom (`member` or `steward`), and why each of
    the rest is refused. Raises `UnknownProjectError` for someone who reaches it neither way."""
    found = store.events(project_id) if store.exists(project_id) else None
    permitted = None if found is None else permitted_actions_in(profile, found, principal)
    if permitted is None:
        raise UnknownProjectError(f"no project {project_id!r}")
    return permitted


def permitted_actions_in(
    profile: Profile, events: list[dict[str, Any]], principal: Principal
) -> dict[str, Any] | None:
    """`permitted_actions` in the project whose log, already read, is `events`, so that a listing
    that has read its projects' logs does not read each again; None for someone who reaches the
    project neither as a member nor as its steward."""
    role = role_in(events, principal)
    if role is not None:
        member = [
            _row(a.value, None if allowed(role, a) else f"not-{role.value}-action") for a in Action
        ]
        refused = StewardRefusal.MEMBER_OF_PROJECT.value
        return {"acting_as": "member", "actions": member + [_row(a, refused) for a in ACTIONS]}
    found = access_in(profile, events, principal)
    if found is None:
        return None
    researcher = [_row(a.value, NOT_A_MEMBER) for a in Action]
    steward = [_row(a, found.refusal(a)) for a in ACTIONS]
    return {"acting_as": "steward", "actions": researcher + steward}


def _row(action: str, refusal: str | None) -> dict[str, Any]:
    row: dict[str, Any] = {"action": action, "permitted": refusal is None}
    if refusal is not None:
        row["refusal"] = refusal
    return row
