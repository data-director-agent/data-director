"""The project record: an append-only log of what changed in a project (docs/specs/projects.md).

A project is a record of its own that outlives any conversation. These are the project rules,
written once over a `ProjectLog` (`dd_harness.storage`, docs/specs/storage.md) that a backend
provides and that only stores. There is one log and one fold (`fold`); the rules are split by
area, each a `ProjectRules` (`rules`) over that log:

- `lifecycle`: creating, naming, deleting and restoring a project, its conversations, and its
  summary;
- `holdings`: its file inventory and supporting documentation;
- `researchers`: facts from researchers' own ORCID records;
- `repository`: the repository chosen and the requirements it resolved to;
- `flow`: its place in the process flow, and its intake;
- `documents`: drafts, edits, decisions and answers (checked in themselves by `decisions`), and
  what is read from them;
- `facts`: the facts check agents propose and people decide;
- `deposits`: validation reports and deposit packages.

`Projects` is every area together: the `ProjectStorage` every backend gives its callers, while a
caller names only the area Protocols it uses (`dd_harness.storage`). `ProjectStore` is the rules
over the file log, `dd_harness.project_files`, under `DD_PROJECTS_DIR`.

Who may do what in a project is read from the log by `dd_harness.project_access`; membership
events are TODO(#389).
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from dd_harness.project_effects import RunEffects
from dd_harness.project_files import FileProjectLog
from dd_harness.projects.decisions import (
    ANSWER_MAX_LENGTH,
    QUESTION_ID,
    REASON_MAX_LENGTH,
    Decision,
    Verdict,
    check_answers,
    reason_required,
    review_rules,
)
from dd_harness.projects.deposits import DepositRecords
from dd_harness.projects.documents import Documents
from dd_harness.projects.extract import SOURCE_MAX_BYTES, SOURCE_MEDIA_TYPES
from dd_harness.projects.facts import FACT_REASON_MAX_LENGTH, Facts, FactVerdict
from dd_harness.projects.flow import Flow
from dd_harness.projects.fold import APPROVED, PROPOSED, REJECTED, text_digest
from dd_harness.projects.holdings import (
    DOCUMENTATION_MAX_BYTES,
    DOCUMENTATION_MEDIA_TYPES,
    DOCUMENTATION_NAME_MAX_LENGTH,
    Holdings,
    check_documentation,
    read_document_file,
)
from dd_harness.projects.lifecycle import (
    TITLE_BY_MODEL,
    TITLE_BY_RESEARCHER,
    TITLE_MAX_LENGTH,
    Lifecycle,
    TitleSource,
)
from dd_harness.projects.repository import RepositoryChoice
from dd_harness.projects.researchers import Researchers
from dd_harness.projects.rules import (
    CONVERSATION_STARTED,
    DEFAULT_RESTORE_PERIOD,
    DIGEST,
    DOCUMENT_CHANGE_REFUSED,
    DOCUMENT_QUESTION_ANSWERED,
    DOCUMENT_VERSION_ADDED,
    DOCUMENT_VERSION_DECIDED,
    DOCUMENTATION_ADDED,
    FACT_DECIDED,
    FACT_PROPOSED,
    INVENTORY_ADDED,
    PACKAGE_BUILT,
    PROJECT_CREATED,
    PROJECT_DELETED,
    PROJECT_ID,
    PROJECT_RENAMED,
    PROJECT_RESTORED,
    PROJECT_VALIDATED,
    REPOSITORY_CHOSEN,
    RESEARCHER_ADDED,
    RESEARCHER_WITHDRAWN,
    ChangeRefusedError,
    ProjectDeletedError,
    ProjectError,
    ProjectRules,
    Refusal,
    Refused,
    RestoreRefusedError,
    UnknownProjectError,
    deletion,
)
from dd_harness.projects.snapshot import SnapshotLog

__all__ = [
    "ANSWER_MAX_LENGTH",
    "APPROVED",
    "CONVERSATION_STARTED",
    "DEFAULT_RESTORE_PERIOD",
    "DIGEST",
    "DOCUMENTATION_ADDED",
    "DOCUMENTATION_MAX_BYTES",
    "DOCUMENTATION_MEDIA_TYPES",
    "DOCUMENTATION_NAME_MAX_LENGTH",
    "DOCUMENT_CHANGE_REFUSED",
    "DOCUMENT_QUESTION_ANSWERED",
    "DOCUMENT_VERSION_ADDED",
    "DOCUMENT_VERSION_DECIDED",
    "FACT_DECIDED",
    "FACT_PROPOSED",
    "FACT_REASON_MAX_LENGTH",
    "INVENTORY_ADDED",
    "PACKAGE_BUILT",
    "PROJECT_CREATED",
    "PROJECT_DELETED",
    "PROJECT_ID",
    "PROJECT_RENAMED",
    "PROJECT_RESTORED",
    "PROJECT_VALIDATED",
    "PROPOSED",
    "QUESTION_ID",
    "REASON_MAX_LENGTH",
    "REJECTED",
    "REPOSITORY_CHOSEN",
    "RESEARCHER_ADDED",
    "RESEARCHER_WITHDRAWN",
    "SOURCE_MAX_BYTES",
    "SOURCE_MEDIA_TYPES",
    "TITLE_BY_MODEL",
    "TITLE_BY_RESEARCHER",
    "TITLE_MAX_LENGTH",
    "ChangeRefusedError",
    "Decision",
    "DepositRecords",
    "Documents",
    "FactVerdict",
    "Facts",
    "Flow",
    "Holdings",
    "Lifecycle",
    "ProjectDeletedError",
    "ProjectError",
    "ProjectRules",
    "ProjectStore",
    "Projects",
    "Refusal",
    "Refused",
    "RepositoryChoice",
    "Researchers",
    "RestoreRefusedError",
    "SnapshotLog",
    "TitleSource",
    "UnknownProjectError",
    "Verdict",
    "check_answers",
    "check_documentation",
    "deletion",
    "read_document_file",
    "reason_required",
    "review_rules",
    "text_digest",
]


class Projects(
    Lifecycle,
    Holdings,
    Researchers,
    RepositoryChoice,
    Flow,
    Documents,
    Facts,
    DepositRecords,
    RunEffects,
):
    """The project rules, every area together over one `ProjectLog` (`dd_harness.storage`,
    docs/specs/storage.md): the `ProjectStorage` every backend gives its callers. The log stores
    and reads; everything that decides whether a change is allowed, and what the log means, is in
    the areas this is made of, and what a finished run does to its project is
    `RunEffects.after_run` (`dd_harness.project_effects`). It adds only `snapshot`."""

    def snapshot(self, project_id: str) -> Projects:
        """The rules over the project `project_id` as its log reads now, read once however much
        is asked of it, for the reads of one invocation (`SnapshotLog`). It takes no change."""
        return Projects(SnapshotLog(self.log, project_id), restore_period=self.restore_period)


class ProjectStore(Projects):
    """The file backend of `ProjectStorage`: the project rules over a `FileProjectLog` under
    `root` (`dd_harness.project_files`, docs/specs/storage.md). `root` belongs to this backend,
    for tests of its layout; every other caller reaches a project through `ProjectStorage`."""

    def __init__(self, root: Path, *, restore_period: timedelta = DEFAULT_RESTORE_PERIOD) -> None:
        super().__init__(FileProjectLog(root), restore_period=restore_period)
        self.root = root
