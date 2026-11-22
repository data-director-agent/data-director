"""The project rules' errors and title sources, apart from the rules themselves
(`dd_harness.projects`) so that what acts on a project for a run (`dd_harness.project_effects`)
can name them without importing the rules. `dd_harness.projects` re-exports every name here."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final, Literal

# Who gave a project its title: a person (when creating or renaming it) or an orchestrator's
# model. A person's title is never replaced by a model's.
TITLE_BY_RESEARCHER: Final = "researcher"
TITLE_BY_MODEL: Final = "model"
type TitleSource = Literal["researcher", "model"]


class ProjectError(ValueError):
    """The project does not exist, or what was to be added to it was refused."""


class UnknownProjectError(ProjectError):
    """No project has this identifier."""


class ProjectDeletedError(ProjectError):
    """The project is deleted, so it takes no new work until it is restored
    (docs/specs/projects.md, invariant 24)."""


class RestoreRefusedError(ProjectError):
    """The project is not deleted, or the period in which it could be restored is over
    (docs/specs/projects.md, invariant 25)."""


class UnknownConversationError(ProjectError):
    """The project records no conversation with this identifier."""


class ConversationDeletedError(ProjectError):
    """The conversation is deleted, so it is not deleted again until it is restored
    (docs/specs/projects.md, invariant 29)."""


class MembershipRefusal(StrEnum):
    """Why a change to a project's members was refused (docs/specs/projects.md, invariant 16).
    Each value is a Problem Details slug."""

    LAST_OWNER = "last-owner"
    ALREADY_MEMBER = "already-member"
    NOT_A_MEMBER = "not-a-member"
    SAME_ROLE = "same-role"


class MembershipRefusedError(ProjectError):
    """A change to a project's members that would leave it with no owner, add someone already a
    member, or change or remove someone who is not one. Nothing is recorded."""

    def __init__(self, refusal: MembershipRefusal, detail: str) -> None:
        super().__init__(detail)
        self.refusal = refusal
        self.detail = detail


class EscalationRefusal(StrEnum):
    """Why an escalation to a data steward, or a move of one, was refused
    (docs/specs/stewardship.md, invariant 4). Each value is a Problem Details slug."""

    NO_STEWARD_TEAM = "no-steward-team"
    UNKNOWN_TEAM = "unknown-team"
    TEAM_REQUIRED = "team-required"
    UNKNOWN_ESCALATION = "unknown-escalation"
    MOVE_NOT_ALLOWED = "move-not-allowed"
    NOT_YOUR_MOVE = "not-your-move"
    NOTE_REQUIRED = "note-required"
    NOTE_TOO_LONG = "note-too-long"
    ORIGIN_MISMATCH = "origin-mismatch"
    ALREADY_ESCALATED = "already-escalated"
    MEMBER_OF_PROJECT = "member-of-project"


class EscalationRefusedError(ProjectError):
    """An escalation that cannot be routed or does not match the run it names, or a move its
    state, or the side of whoever asked, does not allow. Nothing is recorded."""

    def __init__(self, refusal: EscalationRefusal, detail: str) -> None:
        super().__init__(detail)
        self.refusal = refusal
        self.detail = detail


class StewardRefusal(StrEnum):
    """Why a steward's action in a project was refused (docs/specs/stewardship.md, invariants 6
    to 8). Each value is a Problem Details slug."""

    MEMBER_OF_PROJECT = "member-of-project"
    NOT_PERMITTED = "steward-action-not-permitted"
    NOTE_REQUIRED = "note-required"
    NOTE_TOO_LONG = "note-too-long"
    ALREADY_PAUSED = "already-paused"
    NOT_PAUSED = "not-paused"
    PAUSE_HELD_ELSEWHERE = "pause-held-by-another-team"
    NOT_REFERRED = "run-not-referred"
    GATE_DECIDED = "gate-decided"


class StewardRefusedError(ProjectError):
    """A steward's action that their access, or the project's state, does not allow. Nothing is
    recorded."""

    def __init__(self, refusal: StewardRefusal, detail: str) -> None:
        super().__init__(detail)
        self.refusal = refusal
        self.detail = detail


class Refusal(StrEnum):
    """Why a decision, an edit or an answer was refused as not naming what it must
    (docs/specs/projects.md, invariant 12). Each value is a Problem Details slug."""

    NO_DOCUMENT = "document-not-found"
    NOT_LATEST = "version-not-latest"
    DECIDED = "version-decided"
    DIGEST = "digest-mismatch"
    NOT_A_DRAFT = "version-not-a-draft"  # a `questions` version (docs/specs/drafting.md)
    NOT_ASKED = "question-not-asked"
    NO_PROPOSAL = "proposal-not-found"
    NOT_PROPOSED = "fact-not-proposed"
    SUPERSEDED = "proposal-superseded"
    NOT_ATTACHED = "documentation-not-found"  # a plan that is no document the project holds


class ChangeRefusedError(ProjectError):
    """A decision or edit that does not name the document's latest text, a decision on a
    version already decided, an answer to a question the latest version does not ask, or a
    decision on a fact the project was not proposed or on a proposal since superseded. The
    refusal is recorded, and nothing else is."""

    def __init__(self, refusal: Refusal, detail: str) -> None:
        super().__init__(detail)
        self.refusal = refusal
        self.detail = detail


@dataclass(frozen=True)
class Refused:
    """A change the project rules refuse: why, what a person is told, and what the
    `document_change_refused` event names. Returned, not raised, so that the refusal is written
    in the change's exclusive section before `ChangeRefusedError` is raised."""

    refusal: Refusal
    detail: str
    named: dict[str, Any]
