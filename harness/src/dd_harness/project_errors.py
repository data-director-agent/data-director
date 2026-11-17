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


class Refusal(StrEnum):
    """Why a decision, an edit or an answer was refused as not naming what it must
    (docs/specs/projects.md, invariant 12). Each value is a Problem Details slug."""

    NO_DOCUMENT = "document-not-found"
    NOT_LATEST = "version-not-latest"
    DECIDED = "version-decided"
    DIGEST = "digest-mismatch"
    NOT_ASKED = "question-not-asked"
    NO_PROPOSAL = "proposal-not-found"
    NOT_PROPOSED = "fact-not-proposed"


class ChangeRefusedError(ProjectError):
    """A decision or edit that does not name the document's latest text, a decision on a
    version already decided, an answer to a question the latest version does not ask, or a
    decision on a fact the project was not proposed. The refusal is recorded, and nothing else
    is."""

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
