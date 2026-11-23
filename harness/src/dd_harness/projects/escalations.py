"""A project's support team, and its escalations to a data steward (docs/specs/stewardship.md,
invariant 4; docs/ui/steward-escalation-flows.md, "Escalation states").

An escalation is a record in the project's log, not a store of its own. `escalation_opened` hands
a matter to a steward team: it names the team, its origin (the researcher, a policy-gate
referral, an agent's outcome or the orchestrator's offer, with the run), the researcher's note,
and the scope shared as the researcher saw it when they confirmed it. Every later event names the
escalation by `escalation_id`, the `event_id` of its `escalation_opened`, and moves it between
the states of `MOVES`. Any other move is refused and nothing is recorded. A re-opened escalation
keeps its history: no event is changed.

Two steward moves name a target: `reassign` gives a taken escalation to a colleague in its team,
and `transfer` sends it to another team, which must take it again. The rules check only that a
target is given and is not where the escalation already is; whether the colleague is in the team
and not a member of the project, and whether the team exists, needs the profile, so is the
caller's check (`dd_harness.escalation_targets`).

Each move belongs to a side, the researcher's or the steward's. The rules check that the side
asking is the move's; who is on which side is the caller's check
(`dd_harness.escalation_api.side_of`), as who may change membership is for `Membership`. A
steward's move also records `acting_as: steward`.

`support_team_chosen` records the steward team the project's owners chose to support it, which
an escalation is routed to. Which teams exist is the profile's, which these rules do not read:
`dd_harness.escalation_api` checks a team against it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Literal

from dd_harness.escalation_storage import MoveAsked as MoveAsked
from dd_harness.escalation_storage import NewEscalation as NewEscalation
from dd_harness.projects.rules import (
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
    SUPPORT_TEAM_CHOSEN,
    EscalationRefusal,
    EscalationRefusedError,
    ProjectRules,
)
from dd_sdk.contract.models import Principal

OPEN: Final = "open"
TAKEN: Final = "taken"
WAITING: Final = "waiting_for_researcher"
RESOLVED: Final = "resolved"
HANDED_BACK: Final = "handed_back"
WITHDRAWN: Final = "withdrawn"
type EscalationState = Literal[
    "open", "taken", "waiting_for_researcher", "resolved", "handed_back", "withdrawn"
]
# The states in which a steward team holds the matter, and may open the project (invariant 3).
LIVE_STATES: Final = frozenset({OPEN, TAKEN, WAITING})

RESEARCHER: Final = "researcher"
STEWARD: Final = "steward"
type Side = Literal["researcher", "steward"]
type Move = Literal[
    "take",
    "release",
    "wait",
    "reply",
    "resolve",
    "hand_back",
    "withdraw",
    "reopen",
    "reassign",
    "transfer",
]
# What a move that names a target names: a colleague's `principal_id`, or a steward team's id.
type Target = Literal["colleague", "team"]

# Where an escalation comes from (invariant 4). Each but the researcher's names the run.
ORIGINS: Final = ("researcher", "policy_gate", "agent", "orchestrator")
NOTE_MAX_LENGTH: Final = 4000
SCOPE_MAX_LINES: Final = 20
SCOPE_LINE_MAX_LENGTH: Final = 500


@dataclass(frozen=True)
class Step:
    """One move of an escalation: the event it appends, the states it may be made from, the state
    it leads to, whose it is, whether it needs a note, and what target it names, if any."""

    event: str
    starts: frozenset[str]
    to: str
    side: Side
    note: Literal["required", "optional", "none"]
    target: Target | None = None


# The table in docs/ui/steward-escalation-flows.md, "Escalation states". Routing an escalation
# again when no steward takes it (`open` to `open`) is no person's move, so it is not here: the
# deployment's sweep records it (`Escalations.reroute_escalation`, invariant 13).
MOVES: Final[Mapping[str, Step]] = {
    "take": Step(ESCALATION_TAKEN, frozenset({OPEN}), TAKEN, STEWARD, "none"),
    "release": Step(ESCALATION_RELEASED, frozenset({TAKEN}), OPEN, STEWARD, "optional"),
    "wait": Step(ESCALATION_WAITING, frozenset({TAKEN}), WAITING, STEWARD, "required"),
    "reply": Step(ESCALATION_REPLIED, frozenset({WAITING}), TAKEN, RESEARCHER, "required"),
    "resolve": Step(
        ESCALATION_RESOLVED, frozenset({TAKEN, WAITING}), RESOLVED, STEWARD, "required"
    ),
    "hand_back": Step(
        ESCALATION_HANDED_BACK, frozenset({TAKEN, WAITING}), HANDED_BACK, STEWARD, "required"
    ),
    "withdraw": Step(ESCALATION_WITHDRAWN, frozenset(LIVE_STATES), WITHDRAWN, RESEARCHER, "none"),
    "reopen": Step(
        ESCALATION_REOPENED, frozenset({RESOLVED, HANDED_BACK}), OPEN, RESEARCHER, "required"
    ),
    # Flow G: cover within a team, and moving a matter to the team it belongs with.
    "reassign": Step(
        ESCALATION_REASSIGNED, frozenset({TAKEN}), TAKEN, STEWARD, "optional", "colleague"
    ),
    "transfer": Step(
        ESCALATION_TRANSFERRED, frozenset(LIVE_STATES), OPEN, STEWARD, "required", "team"
    ),
}
_MOVE_OF: Final = {step.event: move for move, step in MOVES.items()}


def support_team(events: Iterable[Mapping[str, Any]]) -> str | None:
    """The steward team the project's owners last chose to support it, or None."""
    found = None
    for event in events:
        if event["event"] == SUPPORT_TEAM_CHOSEN:
            found = event["team_id"]
    return found


def escalations(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Each escalation of the project whose log is `events`, the first opened first: its state,
    team, origin, note, the scope shared, who opened it and when, who has taken it, and each
    move made, with who made it, when and their note."""
    found: dict[str, dict[str, Any]] = {}
    for event in events:
        kind = event["event"]
        if kind == ESCALATION_OPENED:
            found[event["event_id"]] = {
                "escalation_id": event["event_id"],
                "state": OPEN,
                "team_id": event["team_id"],
                "origin": event["origin"],
                "note": event["note"],
                "scope_shared": event["scope_shared"],
                "opened_by": event["acted_for"],
                "opened_at": event["at"],
                "updated_at": event["at"],
                # When the team was last asked to take it: opened, released, re-opened or rerouted.
                "routed_at": event["at"],
                "taken_by": None,
                "history": [_history("open", event)],
            }
        elif (move := _MOVE_OF.get(kind)) is not None and (
            escalation := found.get(event["escalation_id"])
        ) is not None:
            escalation["state"] = MOVES[move].to
            escalation["updated_at"] = event["at"]
            _fold(escalation, move, event)
            escalation["history"].append(_history(move, event))
        elif (
            kind == ESCALATION_REROUTED
            and (escalation := found.get(event["escalation_id"])) is not None
        ):
            escalation["updated_at"] = escalation["routed_at"] = event["at"]
            escalation["history"].append(_history("reroute", event))
    return list(found.values())


def _fold(escalation: dict[str, Any], move: str, event: Mapping[str, Any]) -> None:
    """Who holds `escalation`, and when its team was last asked to take it, after `move`."""
    if move == "take":
        escalation["taken_by"] = event["acted_for"]
    elif move == "reassign":
        escalation["taken_by"] = event["to_steward"]
    elif move in ("release", "reopen", "transfer"):
        escalation["taken_by"] = None
        escalation["routed_at"] = event["at"]
    if move == "transfer":
        escalation["team_id"] = event["team_id"]


# What a move's history entry says about its target, by the event's own names.
_TARGET_KEYS: Final = ("from_steward", "to_steward", "from_team", "team_id")


def _history(move: str, event: Mapping[str, Any]) -> dict[str, Any]:
    entry = {
        "move": move,
        "event_id": event["event_id"],
        "by": event["acted_for"],
        "at": event["at"],
    }
    if event.get("note"):
        entry["note"] = event["note"]
    if event.get("acting_as"):
        entry["acting_as"] = event["acting_as"]
    if (step := MOVES.get(move)) is not None and step.target is not None:
        entry.update({key: event[key] for key in _TARGET_KEYS if event.get(key) is not None})
    return entry


def _target_detail(
    step: Step, escalation: Mapping[str, Any], to: str | Principal | None
) -> dict[str, Any]:
    """What a move that names a target records about it: where the escalation was, and where it
    goes. Raises `EscalationRefusedError` for a target missing, or where it already is."""
    if step.target is None:
        return {}
    if not to or isinstance(to, Principal) != (step.target == "colleague"):
        raise EscalationRefusedError(
            EscalationRefusal.TARGET_REQUIRED,
            f"name the {step.target} to {'reassign' if step.target == 'colleague' else 'transfer'}"
            " it to",
        )
    if isinstance(to, Principal):
        if to.principal_id == (escalation["taken_by"] or {}).get("principal_id"):
            raise EscalationRefusedError(
                EscalationRefusal.SAME_TARGET, "that steward has already taken it"
            )
        return {
            "from_steward": escalation["taken_by"],
            "to_steward": to.model_dump(mode="json", exclude_none=True),
        }
    if to == escalation["team_id"]:
        raise EscalationRefusedError(
            EscalationRefusal.SAME_TARGET, "the escalation is already with that team"
        )
    return {"from_team": escalation["team_id"], "team_id": to}


def _check_note(note: str | None, *, required: bool) -> str | None:
    note = (note or "").strip() or None
    if required and note is None:
        raise EscalationRefusedError(EscalationRefusal.NOTE_REQUIRED, "a note is required here")
    if note is not None and len(note) > NOTE_MAX_LENGTH:
        raise EscalationRefusedError(
            EscalationRefusal.NOTE_TOO_LONG,
            f"a note is at most {NOTE_MAX_LENGTH} characters; this one has {len(note)}",
        )
    return note


def _check_scope(scope_shared: Sequence[str]) -> list[str]:
    lines = [str(line).strip() for line in scope_shared if str(line).strip()]
    if len(lines) > SCOPE_MAX_LINES or any(len(line) > SCOPE_LINE_MAX_LENGTH for line in lines):
        raise EscalationRefusedError(
            EscalationRefusal.NOTE_TOO_LONG,
            f"the scope shared is at most {SCOPE_MAX_LINES} lines of at most "
            f"{SCOPE_LINE_MAX_LENGTH} characters",
        )
    return lines


class Escalations(ProjectRules):
    """The rules of a project's support team and its escalations to a data steward."""

    def choose_support_team(
        self, project_id: str, team_id: str, *, acted_for: Principal, caused_by: str
    ) -> None:
        """Record `team_id` as the project's support team, unless it already is. Whether the
        team exists, and whether `acted_for` may choose it, are the caller's checks."""
        with self._section(project_id) as section:
            if support_team(section.events()) != team_id:
                section.append(
                    [
                        self._event(
                            project_id,
                            SUPPORT_TEAM_CHOSEN,
                            acted_for,
                            caused_by,
                            {"team_id": team_id},
                        )
                    ]
                )

    def open_escalation(
        self, project_id: str, new: NewEscalation, *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any]:
        """Open the escalation `new` and return it. With `new.support`, also record its team as
        the project's support team, in the same section. Raises `EscalationRefusedError` for a
        missing or overlong note, too much scope, or a run that already has a live escalation."""
        checked_note = _check_note(new.note, required=True)
        lines = _check_scope(new.scope_shared)
        with self._section(project_id) as section:
            events = section.events()
            invocation = new.origin.get("invocation_id")
            if invocation is not None and any(
                e["origin"].get("invocation_id") == invocation and e["state"] in LIVE_STATES
                for e in escalations(events)
            ):
                raise EscalationRefusedError(
                    EscalationRefusal.ALREADY_ESCALATED,
                    f"the run {invocation} has already been sent to a data steward",
                )
            appended = []
            if new.support and support_team(events) != new.team_id:
                appended.append(
                    self._event(
                        project_id,
                        SUPPORT_TEAM_CHOSEN,
                        acted_for,
                        caused_by,
                        {"team_id": new.team_id},
                    )
                )
            opened = self._event(
                project_id,
                ESCALATION_OPENED,
                acted_for,
                caused_by,
                {
                    "team_id": new.team_id,
                    "origin": dict(new.origin),
                    "note": checked_note,
                    "scope_shared": lines,
                },
            )
            section.append([*appended, opened])
        (escalation,) = escalations([opened])
        return escalation

    def move_escalation(
        self,
        project_id: str,
        escalation_id: str,
        move: str | MoveAsked,
        *,
        side: Side,
        acted_for: Principal,
        caused_by: str,
    ) -> dict[str, Any]:
        """Make `move` on the escalation for `side`, and return the escalation as it then
        stands. `move` is a move's name alone, or a `MoveAsked` with its note and its target:
        the colleague for `reassign`, a team's id for `transfer`; other moves ignore a target.
        Raises
        `EscalationRefusedError` for an unknown escalation or move, a move its state does not
        allow, one that is not `side`'s, a note missing or too long, or a target missing or
        where the escalation already is."""
        asked = move if isinstance(move, MoveAsked) else MoveAsked(move)
        move, note, to = asked.move, asked.note, asked.to
        step = MOVES.get(move)
        if step is None:
            raise EscalationRefusedError(
                EscalationRefusal.MOVE_NOT_ALLOWED,
                f"{move!r} is not a move; the moves are {', '.join(MOVES)}",
            )
        checked_note = _check_note(note, required=step.note == "required")
        if step.note == "none":
            checked_note = None
        with self._section(project_id) as section:
            events = section.events()
            found = {e["escalation_id"]: e for e in escalations(events)}.get(escalation_id)
            if found is None:
                raise EscalationRefusedError(
                    EscalationRefusal.UNKNOWN_ESCALATION, f"no escalation {escalation_id!r}"
                )
            if step.side != side:
                raise EscalationRefusedError(
                    EscalationRefusal.NOT_YOUR_MOVE,
                    f"only the {step.side} may {move.replace('_', ' ')} an escalation",
                )
            if found["state"] not in step.starts:
                raise EscalationRefusedError(
                    EscalationRefusal.MOVE_NOT_ALLOWED,
                    f"an escalation that is {found['state'].replace('_', ' ')} cannot be "
                    f"moved by {move.replace('_', ' ')}",
                )
            detail: dict[str, Any] = {
                "escalation_id": escalation_id,
                **_target_detail(step, found, to),
            }
            if checked_note is not None:
                detail["note"] = checked_note
            if side == STEWARD:
                detail["acting_as"] = STEWARD
            moved = self._event(project_id, step.event, acted_for, caused_by, detail)
            section.append([moved])
        return {e["escalation_id"]: e for e in escalations([*events, moved])}[escalation_id]

    def reroute_escalation(
        self,
        project_id: str,
        escalation_id: str,
        *,
        routed_before: datetime,
        acted_for: Principal,
        caused_by: str,
    ) -> dict[str, Any] | None:
        """Send the escalation to its team again, if it is still `open` and was last routed
        before `routed_before`, and return it; otherwise record nothing and
        return None. Checked inside the section, so that a steward taking it meanwhile wins."""
        with self._section(project_id) as section:
            events = section.events()
            found = {e["escalation_id"]: e for e in escalations(events)}.get(escalation_id)
            if (
                found is None
                or found["state"] != OPEN
                or datetime.fromisoformat(found["routed_at"]) >= routed_before
            ):
                return None
            detail = {"escalation_id": escalation_id, "team_id": found["team_id"]}
            rerouted = self._event(project_id, ESCALATION_REROUTED, acted_for, caused_by, detail)
            section.append([rerouted])
        return {e["escalation_id"]: e for e in escalations([*events, rerouted])}[escalation_id]
