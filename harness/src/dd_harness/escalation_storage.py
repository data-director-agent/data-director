"""The part of a project's storage that keeps its support team and its escalations to a data
steward (`dd_harness.projects.escalations`, docs/specs/stewardship.md, invariant 4).
`dd_harness.storage.ProjectStorage` includes it."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol

from dd_sdk.contract.models import Principal


@dataclass(frozen=True)
class NewEscalation:
    """An escalation a person confirmed: the team it is routed to, its origin as checked, the
    researcher's note and the scope shared as they saw it. With `support`, the team also becomes
    the project's support team."""

    team_id: str
    origin: Mapping[str, Any]
    note: str
    scope_shared: Sequence[str] = ()
    support: bool = False


@dataclass(frozen=True)
class MoveAsked:
    """A move asked for on an escalation: its name, the note it carries, and the target a move
    that names one names: the colleague for `reassign`, a team's id for `transfer`."""

    move: str
    note: str | None = None
    to: str | Principal | None = None


class ProjectEscalations(Protocol):
    def events(self, project_id: str) -> list[dict[str, Any]]:
        """Every event of the project, oldest first."""
        ...

    def choose_support_team(
        self, project_id: str, team_id: str, *, acted_for: Principal, caused_by: str
    ) -> None:
        """Record the project's support team, unless it already is."""
        ...

    def open_escalation(
        self, project_id: str, new: NewEscalation, *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any]:
        """Open an escalation to a steward team; with `new.support`, also choose it as the
        project's support team."""
        ...

    def move_escalation(
        self,
        project_id: str,
        escalation_id: str,
        move: str | MoveAsked,
        *,
        side: Literal["researcher", "steward"],
        acted_for: Principal,
        caused_by: str,
    ) -> dict[str, Any]:
        """Make a move on an escalation, for the researcher's or the steward's side: a move's
        name alone, or with its note and target."""
        ...

    def reroute_escalation(
        self,
        project_id: str,
        escalation_id: str,
        *,
        routed_before: datetime,
        acted_for: Principal,
        caused_by: str,
    ) -> dict[str, Any] | None:
        """Send an `open` escalation last routed before `routed_before` to its team again."""
        ...
