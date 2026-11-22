"""What a data steward does in a project they reach as its steward (docs/specs/stewardship.md,
invariants 3 and 6 to 8).

Each of these is an event in the project's log naming the steward as whom it acted for, with
`acting_as: steward`, kept beside the researchers' and the agents' events and never rewriting
them:

- `steward_viewed`: the steward opened the project or read its content, at most once a day for
  each steward (invariant 3);
- `steward_message`: a note to the researcher, shown as from a named person (invariant 6);
- a proposed version of a document (`document_version_added` with `acting_as: steward`), which
  the project's owners approve or reject as any other (invariant 6);
- `project_paused` and `project_resumed`: a pause the steward's team holds until one of its
  stewards lifts it, each with a reason (invariant 8);
- `gate_cleared` and `gate_refused`: the steward's decision on a run the policy gate referred,
  with a reason (invariant 7). It does not approve the content, and it does not run the agent:
  resuming a cleared run is TODO(#16).

Whether the person is a steward of this project, and may take the action, is the caller's check
(`dd_harness.steward_api`, from the profile), as who may change membership is for `Membership`.
These rules check what the log alone decides: a pause is not applied twice, is lifted only by the
team that holds it, and a referred run is decided once.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any, Final

from dd_harness.projects.documents import Documents
from dd_harness.projects.rules import (
    GATE_CLEARED,
    GATE_REFUSED,
    PROJECT_PAUSED,
    PROJECT_RESUMED,
    STEWARD_MESSAGE,
    STEWARD_VIEWED,
    StewardRefusal,
    StewardRefusedError,
)
from dd_harness.steward_storage import GateDecision, ProposedEdit
from dd_sdk.contract.models import DocumentVersionRef, Principal, now

STEWARD: Final = "steward"
NOTE_MAX_LENGTH: Final = 4000
_GATE_EVENTS: Final = {"cleared": GATE_CLEARED, "refused": GATE_REFUSED}


def pause_of(events: Iterable[Mapping[str, Any]]) -> dict[str, Any] | None:
    """The pause that stands on the project whose log is `events`: the team that holds it, its
    reason, who applied it and when; or None while the project is not paused."""
    found: dict[str, Any] | None = None
    for event in events:
        if event["event"] == PROJECT_PAUSED:
            found = {
                "team_id": event["team_id"],
                "reason": event["reason"],
                "by": event["acted_for"],
                "at": event["at"],
            }
        elif event["event"] == PROJECT_RESUMED:
            found = None
    return found


def gate_decisions(events: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """The steward's decision on each referred run of the project, by `invocation_id`."""
    verdicts = {kind: verdict for verdict, kind in _GATE_EVENTS.items()}
    return {
        event["invocation_id"]: {
            "verdict": verdicts[event["event"]],
            "reason": event["reason"],
            "by": event["acted_for"],
            "at": event["at"],
        }
        for event in events
        if event["event"] in verdicts
    }


def viewed_today(events: Iterable[Mapping[str, Any]], principal_id: str, today: str) -> bool:
    """Whether `principal_id` already has a `steward_viewed` on the UTC day `today`."""
    return any(
        event["event"] == STEWARD_VIEWED
        and event["acted_for"].get("principal_id") == principal_id
        and _day(event["at"]) == today
        for event in events
    )


def _day(at: str) -> str:
    return datetime.fromisoformat(at).date().isoformat()


def _note(note: str | None) -> str:
    checked = (note or "").strip()
    if not checked:
        raise StewardRefusedError(StewardRefusal.NOTE_REQUIRED, "a reason or note is required")
    if len(checked) > NOTE_MAX_LENGTH:
        raise StewardRefusedError(
            StewardRefusal.NOTE_TOO_LONG,
            f"a note is at most {NOTE_MAX_LENGTH} characters; this one has {len(checked)}",
        )
    return checked


class Stewarding(Documents):
    """The record of what data stewards do in a project."""

    def record_view(self, project_id: str, *, acted_for: Principal, caused_by: str) -> bool:
        """Append a `steward_viewed` naming `acted_for`, unless they have one today. Returns
        whether one was appended. A deleted project is never read as a steward, so is refused."""
        today = now().date().isoformat()
        with self._section(project_id) as section:
            if viewed_today(section.events(), acted_for.principal_id, today):
                return False
            section.append([self._steward(project_id, STEWARD_VIEWED, acted_for, caused_by, {})])
        return True

    def steward_message(
        self, project_id: str, note: str, *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any]:
        """Record a steward's note to the researcher, and return its event."""
        event = self._steward(
            project_id, STEWARD_MESSAGE, acted_for, caused_by, {"note": _note(note)}
        )
        with self._section(project_id) as section:
            section.append([event])
        return event

    def pause(
        self, project_id: str, team_id: str, reason: str, *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any]:
        """Pause the project for `team_id`, and return the pause. Raises `StewardRefusedError`
        for a project already paused or a missing reason."""
        detail = {"team_id": team_id, "reason": _note(reason)}
        with self._section(project_id) as section:
            if pause_of(section.events()) is not None:
                raise StewardRefusedError(
                    StewardRefusal.ALREADY_PAUSED, "this project is already paused"
                )
            event = self._steward(project_id, PROJECT_PAUSED, acted_for, caused_by, detail)
            section.append([event])
        found = pause_of([event])
        assert found is not None
        return found

    def resume(
        self,
        project_id: str,
        teams: frozenset[str],
        reason: str,
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> None:
        """Lift the project's pause, which one of `teams`, the steward's, must hold. Raises
        `StewardRefusedError` for a project not paused, a pause another team holds, or a missing
        reason."""
        checked = _note(reason)
        with self._section(project_id) as section:
            held = pause_of(section.events())
            if held is None:
                raise StewardRefusedError(StewardRefusal.NOT_PAUSED, "this project is not paused")
            if held["team_id"] not in teams:
                raise StewardRefusedError(
                    StewardRefusal.PAUSE_HELD_ELSEWHERE,
                    "only a steward of the team that paused this project may lift its pause",
                )
            detail = {"team_id": held["team_id"], "reason": checked}
            section.append(
                [self._steward(project_id, PROJECT_RESUMED, acted_for, caused_by, detail)]
            )

    def decide_gate(
        self, project_id: str, decision: GateDecision, *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any]:
        """Record a steward's decision on a referred run, and return it. That the run is a
        referral of this project is the caller's check, against the run store. Raises
        `StewardRefusedError` for a run already decided or a missing reason."""
        invocation_id = decision.invocation_id
        detail = {"invocation_id": invocation_id, "reason": _note(decision.reason)}
        kind = _GATE_EVENTS[decision.verdict]
        with self._section(project_id) as section:
            if invocation_id in gate_decisions(section.events()):
                raise StewardRefusedError(
                    StewardRefusal.GATE_DECIDED,
                    f"a steward has already decided the referred run {invocation_id}",
                )
            event = self._steward(project_id, kind, acted_for, caused_by, detail)
            section.append([event])
        return gate_decisions([event])[invocation_id]

    def propose_edit(
        self, project_id: str, edit: ProposedEdit, *, acted_for: Principal, caused_by: str
    ) -> DocumentVersionRef:
        """Record a steward's edit of the latest version as a new proposed version, marked as the
        steward's, which the project's owners approve or reject (invariant 6). Refused as
        `Documents.edit` refuses an edit."""
        marked = {"acting_as": STEWARD}
        return self._edit(project_id, edit, acted_for=acted_for, caused_by=caused_by, marked=marked)

    def _steward(
        self,
        project_id: str,
        kind: str,
        acted_for: Principal,
        caused_by: str,
        detail: dict[str, Any],
    ) -> dict[str, Any]:
        return self._event(project_id, kind, acted_for, caused_by, {**detail, "acting_as": STEWARD})
