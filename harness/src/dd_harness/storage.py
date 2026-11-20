"""What the harness asks of the stores it keeps runs and projects in (docs/specs/storage.md).

`RunStorage` and `ProjectStorage` are the interfaces callers use; `ProjectStorage` is composed of
one Protocol per area of the project rules (`ProjectLifecycle`, `ProjectConversations` and the
rest), so that a caller depends only on the areas it uses. `dd_harness.store.RunStore`
implements `RunStorage` over files. `ProjectStorage` is implemented once, by the project rules
(`dd_harness.projects.Projects`), over a `ProjectLog` that a backend provides, such as the file one
(`dd_harness.project_files.FileProjectLog`). Everything else reaches a store through these
protocols, so another backend, such as a database, can replace a file one unseen by callers.

Each protocol's docstring states the guarantees a backend must keep. `dd_harness.testing`'s
`check_run_storage`, `check_project_log` and `check_project_rules` check them against any
backend.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from datetime import timedelta
from typing import Any, Protocol

from dd_harness.conversation_storage import ProjectConversations as ProjectConversations
from dd_harness.fact_storage import ProjectFacts as ProjectFacts
from dd_harness.holding_storage import ProjectHoldings as ProjectHoldings
from dd_harness.listing import Page, Readable
from dd_harness.progress import ENTRY_BY_RESEARCHER, EntrySource
from dd_harness.project_decision import Decision
from dd_harness.project_effects import ProjectEffects
from dd_harness.project_errors import TitleSource
from dd_harness.project_log import ProjectLog as ProjectLog
from dd_harness.project_log import ProjectSection as ProjectSection
from dd_harness.requirements import Requirements
from dd_harness.sources import Sources
from dd_harness.storage_deposits import DepositApprovals
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
    DocumentKind,
    DocumentVersionRef,
    DraftAnswer,
    Envelope,
    Principal,
)

# The artifacts the conductor keeps with each run.
SPANS = "spans.jsonl"  # the OpenTelemetry trace the grounding linter checked
GROUNDING = "grounding.txt"  # the grounding linter's summary
SOURCES = "sources.txt"  # the source check's summary
VALIDATION = "validation-report.jsonld"  # the payload's SHACL Validation Report, if it has shapes
CRATE = "crate"  # the Process Run Crate, one artifact per file under this prefix


class RunStorage(Protocol):
    """Where the conductor keeps each run: its envelope, its request, the prompts it sent, the
    class schemas it was checked against, and named artifacts (the trace, the check reports and
    the Process Run Crate).

    A backend keeps these guarantees:

    1. A run is written once. `append` raises `FileExistsError` for an `invocation_id` already
       stored, and stores nothing of it. An artifact is written once too, and only for a stored
       run.
    2. `iter_envelopes` yields envelopes in the order they were stored. The conductor gives each
       run a UUIDv7 as it starts and stores it as it finishes, so this is the order runs finished
       in; conversations take their turn order from it.
    3. A class schema is kept once under its digest, and its bytes never change.
    4. Prompts are read only through `get_prompts`, by whoever may read the run. Nothing else the
       store returns (an envelope, an artifact) carries them.
    5. A name the caller supplies (an `invocation_id`, a digest, an artifact name) never reaches
       anything outside the store: one that is malformed names nothing.
    6. `list_runs` and `list_conversations` return the items `dd_harness.listing.scan_runs` and
       `scan_conversations` return over `iter_envelopes()`, in the same order, a page at a time.
       A cursor is the backend's own: the next page holds what was stored before the last item
       of the page that gave it, so pages neither repeat nor skip a run stored before the first
       was read. A malformed cursor names an empty page.
    """

    def has(self, invocation_id: str) -> bool:
        """Whether a run with this `invocation_id` is stored."""
        ...

    def append(
        self,
        envelope: dict[str, Any],
        request: dict[str, Any] | None = None,
        schemas: Iterable[ClassSchema] = (),
        prompts: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> None:
        """Store one run: its envelope, its request, each class schema it was checked against,
        and the prompts its model calls name, keyed by digest."""
        ...

    def iter_envelopes(self, *, conversation_id: str | None = None) -> Iterator[dict[str, Any]]:
        """Every stored envelope, in the order stored; with `conversation_id`, only that
        conversation's, turns and delegated children alike."""
        ...

    def list_runs(
        self, *, readable: Readable | None = None, limit: int, before: str | None = None
    ) -> Page:
        """A page of run summaries (`dd_harness.listing.run_summary`), newest first, delegated
        children included; with `readable`, only the runs it includes; with `before`, the runs
        stored before that cursor."""
        ...

    def list_conversations(
        self, *, readable: Readable | None = None, limit: int, before: str | None = None
    ) -> Page:
        """A page of conversation summaries (`dd_harness.listing.conversation_summary`, with its
        turns counted), the most recently active first, by the stored order of each one's latest
        turn. A delegated child is not a turn. With `readable`, only the conversations whose
        first turn it includes."""
        ...

    def get(self, invocation_id: str) -> dict[str, Any] | None:
        """The stored envelope, or None."""
        ...

    def get_request(self, invocation_id: str) -> dict[str, Any] | None:
        """The stored request, or None."""
        ...

    def get_prompts(self, invocation_id: str) -> dict[str, Any]:
        """The prompts a stored run sent, keyed by digest; empty if it sent none."""
        ...

    def get_schema(self, digest: str) -> dict[str, Any] | None:
        """The class schema kept under `digest`, or None."""
        ...

    def put_artifact(self, invocation_id: str, name: str, data: bytes) -> None:
        """Keep `data` as the run's artifact `name`, a relative path such as `spans.jsonl` or
        `crate/ro-crate-metadata.json`. Raises `KeyError` for a run not stored, `ValueError` for
        a malformed name and `FileExistsError` for an artifact already kept."""
        ...

    def get_artifact(self, invocation_id: str, name: str) -> bytes | None:
        """The run's artifact `name`, or None if there is none."""
        ...

    def where(self, invocation_id: str) -> str:
        """Where the run is kept, for a person to read: a path for files, a URI for a database."""
        ...


class ProjectRecord(Protocol):
    """Every area reads a project's events and asks whether it exists; each area Protocol
    below extends this one."""

    def exists(self, project_id: str) -> bool:
        """Whether the project exists."""
        ...

    def events(self, project_id: str) -> list[dict[str, Any]]:
        """Every event of the project, oldest first."""
        ...


class ProjectLifecycle(ProjectRecord, Protocol):
    """Creating, naming, deleting and restoring a project, the conversations started in it, and
    what a list of projects shows of each (`dd_harness.projects.lifecycle`)."""

    def create(self, *, acted_for: Principal, caused_by: str, title: str | None = None) -> str:
        """A new project and its `project_created` event; returns its `project_id`."""
        ...

    def rename(
        self,
        project_id: str,
        title: str,
        *,
        source: TitleSource,
        acted_for: Principal,
        caused_by: str,
    ) -> bool:
        """Give the project a new title; False, recording nothing, for a model's title once a
        person has given one."""
        ...

    restore_period: timedelta
    """How long after its deletion an owner may restore a project; zero makes deletion final."""

    def delete(self, project_id: str, *, acted_for: Principal, caused_by: str) -> dict[str, Any]:
        """Delete the project (a `project_deleted` event); `ProjectDeletedError` if it is
        already. Returns when it was deleted, by whom and until when it may be restored."""
        ...

    def restore(self, project_id: str, *, acted_for: Principal, caused_by: str) -> None:
        """Restore a deleted project (a `project_restored` event); `RestoreRefusedError` if it
        is not deleted or its restore period is over."""
        ...

    def is_deleted(self, project_id: str) -> bool:
        """Whether the project is deleted."""
        ...

    def start_conversation(self, project_id: str, *, acted_for: Principal, caused_by: str) -> str:
        """A new conversation in the project; returns its `conversation_id`."""
        ...

    def project_of(self, conversation_id: str) -> str | None:
        """The project the conversation was started in, or None."""
        ...

    def projects(self) -> list[dict[str, Any]]:
        """A summary of every project, in the order created."""
        ...

    def projects_naming(self, principal_id: str) -> list[str]:
        """The projects whose log may give the principal a role, in the order created
        (`ProjectLog.projects_naming`): a superset of the projects they have a role in, which
        `dd_harness.project_access.readable_projects` narrows by reading their logs."""
        ...

    def logs_naming(self, principal_id: str) -> dict[str, list[dict[str, Any]]]:
        """The log of each project `projects_naming` gives, by project in the order created,
        read at once (`ProjectLog.logs_naming`)."""
        ...

    def summary_of(self, project_id: str, events: list[dict[str, Any]]) -> dict[str, Any]:
        """`summary` of the project whose log, already read, is `events`."""
        ...

    def summary(self, project_id: str) -> dict[str, Any]:
        """What a list of projects shows of one."""
        ...


class ProjectResearchers(ProjectRecord, Protocol):
    """The researcher records a project keeps (`dd_harness.projects.researchers`)."""

    def add_researcher(
        self,
        project_id: str,
        record: Mapping[str, Any],
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> str:
        """Keep a person's own `ResearcherRecord`; returns its digest."""
        ...

    def withdraw_researcher(
        self, project_id: str, orcid_id: str, *, acted_for: Principal, caused_by: str
    ) -> None:
        """Stop giving agents the record a person kept."""
        ...

    def researchers(self, project_id: str) -> list[dict[str, Any]] | None:
        """The `ResearcherRecord`s that stand, the one kept first first; None while none."""
        ...


class ProjectRepository(ProjectRecord, Protocol):
    """The repository chosen and the requirements it resolved to
    (`dd_harness.projects.repository`)."""

    def choose_repository(
        self,
        project_id: str,
        re3data_id: str,
        *,
        registry: Sources,
        requirements: Requirements,
        acted_for: Principal,
        caused_by: str,
    ) -> str:
        """Record the repository chosen by its re3data identifier; returns the merged
        requirement set's digest."""
        ...

    def requirements(self, project_id: str) -> dict[str, Any] | None:
        """The merged requirements of the repository chosen last, or None."""
        ...


class ProjectProgress(ProjectRecord, Protocol):
    """A project's place in the process flow, and its intake (`dd_harness.projects.flow`)."""

    def choose_entry(
        self,
        project_id: str,
        entry: int,
        *,
        acted_for: Principal,
        caused_by: str,
        source: EntrySource = ENTRY_BY_RESEARCHER,
    ) -> bool:
        """Record the entry point chosen; False, recording nothing, for a model's once the
        researcher has chosen one."""
        ...

    def mark_step(
        self, project_id: str, step_id: str, mark: str, *, acted_for: Principal, caused_by: str
    ) -> None:
        """Record a step marked done, skipped or open."""
        ...

    def answer_intake(
        self,
        project_id: str,
        question_id: str,
        answer_values: Sequence[str],
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> None:
        """Record an answer to an intake question, checked against the question."""
        ...

    def dismiss_intake(self, project_id: str, *, acted_for: Principal, caused_by: str) -> None:
        """Record the intake dismissed."""
        ...

    def progress(self, project_id: str) -> dict[str, Any]:
        """The entry point chosen and the step states, derived from the log."""
        ...

    def intake(self, project_id: str) -> dict[str, Any]:
        """Where the intake stands and its questions with their current answers."""
        ...


class ProjectDocuments(ProjectRecord, Protocol):
    """A project's documents: drafts, edits, decisions and answers, and what is read from them
    (`dd_harness.projects.documents`)."""

    def record_draft(self, project_id: str, envelope: Envelope) -> DocumentVersionRef:
        """Record a run's `Document` payload as a proposed version."""
        ...

    def edit(
        self,
        project_id: str,
        document_id: str,
        version: int,
        digest: str,
        text: str,
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> DocumentVersionRef:
        """Record a person's edit of the latest version as a new proposed version."""
        ...

    def decide(
        self, project_id: str, decision: Decision, *, acted_for: Principal, caused_by: str
    ) -> DocumentVersionRef:
        """Record a person's decision on the latest version."""
        ...

    def answer(
        self,
        project_id: str,
        document_id: str,
        version: int,
        answers: list[DraftAnswer],
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> DocumentVersionRef:
        """Record a person's answers to questions the latest version asks."""
        ...

    def answers(self, project_id: str, document_kind: DocumentKind) -> list[dict[str, Any]] | None:
        """The latest answer to each question of the documents of `document_kind`, as
        `DraftAnswer`s, or None."""
        ...

    def current_version(
        self, project_id: str, document_kind: DocumentKind, document_id: str | None = None
    ) -> dict[str, Any] | None:
        """The latest version of `document_id`, or of the document of `document_kind` drafted or
        revised last, as a `CurrentVersion`, or None. Raises `ProjectError` for a `document_id`
        that is not the project's or is of another kind."""
        ...

    def documents(self, project_id: str) -> list[dict[str, Any]]:
        """Each document of the project, with every version and its text, and the answers
        given to its questions."""
        ...

    def metadata_record(self, project_id: str) -> dict[str, Any] | None:
        """The `metadata_record` version a person approved last, as an `ApprovedMetadataRecord`, or
        None."""
        ...


class ProjectDeposits(ProjectRecord, DepositApprovals, Protocol):
    """The validation reports, the decisions and confirmation made before packaging, and the
    deposit packages a project keeps (`dd_harness.projects.deposits`)."""

    def record_validation(
        self,
        project_id: str,
        report: Mapping[str, Any],
        *,
        conforms: bool,
        requirements_digest: str | None,
        acted_for: Principal,
        caused_by: str,
    ) -> str:
        """Keep a SHACL Validation Report of the project; returns its digest."""
        ...

    def record_item_decision(
        self,
        project_id: str,
        decision: Mapping[str, Any],
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> None:
        """Keep a person's decision on an item the deposit check asked them to decide."""
        ...

    def record_confirmation(
        self,
        project_id: str,
        confirmation: Mapping[str, Any],
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> None:
        """Keep a person's confirmation that the checks before deposit were made."""
        ...

    def record_package(
        self,
        project_id: str,
        package: bytes,
        *,
        about: Mapping[str, Any],
        acted_for: Principal,
        caused_by: str,
    ) -> str:
        """Keep a deposit package by the SHA-256 of its bytes; returns the digest."""
        ...

    def package(self, project_id: str, digest: str) -> bytes | None:
        """The bytes of a package the log records as built, or None."""
        ...


class ProjectStorage(
    ProjectLifecycle,
    ProjectConversations,
    ProjectHoldings,
    ProjectResearchers,
    ProjectRepository,
    ProjectProgress,
    ProjectDocuments,
    ProjectFacts,
    ProjectDeposits,
    ProjectEffects,
    Protocol,
):
    """Where the harness keeps each project's log of events, and the content they added
    (docs/specs/projects.md): every area of the project rules together, as
    `dd_harness.projects.Projects` gives them. Whoever builds a store or hands it on names this;
    a caller that uses a store names only the area Protocols it calls.

    A backend keeps these guarantees:

    1. A project's log is append-only: an event is never changed or removed, and events come
       back in the order they were appended.
    2. A change checked against the log (`edit`, `decide`, `answer`, `record_draft`, `rename`,
       `restore`, `decide_fact`, and every change to a deleted project, which is refused)
       reads the log, applies the project rules and appends its events in an exclusive section
       for that project: no other change to the project enters it. The file backend holds a
       lock per project; a database holds a lock on the project's row for one transaction.
       Events a change writes together (an edit and its approval) are kept together or not at
       all.
    3. A refusal is recorded, then raised: the `document_change_refused` event is kept with the
       section, and `ChangeRefusedError` is raised after the section ends.
    4. Projects do not wait on one another.
    5. Content an event adds is kept once by digest, and read back byte for byte.
    6. `project_of`, `projects` and every other read answer from what is stored when asked, so
       several stores over one record agree, and each holds after a restart. Only what can
       never change, such as a conversation's project once recorded, may be cached.
    7. A malformed `project_id` names no project.
    """

    def snapshot(self, project_id: str) -> ProjectStorage:
        """The project as its log reads now, read once for one invocation's reads; it takes no
        change (invariant 12)."""
        ...


class DepositSource(
    ProjectHoldings, ProjectRepository, ProjectDocuments, ProjectDeposits, Protocol
):
    """The areas of a project that validating and packaging it read and record
    (`dd_harness.deposit`)."""
