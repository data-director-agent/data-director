"""The part of a project's storage that keeps what data stewards do in it
(`dd_harness.projects.stewarding`, docs/specs/stewardship.md, invariants 3 and 6 to 8).
`dd_harness.storage.ProjectStorage` includes it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

from dd_sdk.contract.models import DocumentVersionRef, Principal


@dataclass(frozen=True)
class ProposedEdit:
    """A person's edit of a document's latest version: the document, the version edited, the
    digest of the text they edited, and the new text (docs/specs/projects.md, invariant 12)."""

    document_id: str
    version: int
    digest: str
    text: str


@dataclass(frozen=True)
class GateDecision:
    """A steward's decision on a run the policy gate referred, and its reason
    (docs/specs/stewardship.md, invariant 7)."""

    invocation_id: str
    verdict: Literal["cleared", "refused"]
    reason: str


class ProjectStewarding(Protocol):
    def record_view(self, project_id: str, *, acted_for: Principal, caused_by: str) -> bool:
        """Record that a steward read the project, at most once a day for each steward."""
        ...

    def steward_message(
        self, project_id: str, note: str, *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any]:
        """Record a steward's note to the researcher."""
        ...

    def pause(
        self, project_id: str, team_id: str, reason: str, *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any]:
        """Pause the project for a steward team."""
        ...

    def resume(
        self,
        project_id: str,
        teams: frozenset[str],
        reason: str,
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> None:
        """Lift the project's pause, which one of `teams` holds."""
        ...

    def decide_gate(
        self, project_id: str, decision: GateDecision, *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any]:
        """Record a steward's decision on a run the policy gate referred."""
        ...

    def propose_edit(
        self, project_id: str, edit: ProposedEdit, *, acted_for: Principal, caused_by: str
    ) -> DocumentVersionRef:
        """Record a steward's edit as a new proposed version, marked as the steward's."""
        ...
