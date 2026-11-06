"""What the harness asks of the stores it keeps runs and projects in (docs/specs/storage.md).

`RunStorage` and `ProjectStorage` are the interfaces; `dd_harness.store.RunStore` and
`dd_harness.projects.ProjectStore` are the file backends that implement them. Everything else in
the harness, the app and the workbench reaches a store through these protocols, so another
backend, such as a database, can replace a file one without changing its callers.

Each protocol's docstring states the guarantees a backend must keep. `dd_harness.testing`'s
`check_run_storage` and `check_project_storage` check them against any backend.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from typing import Any, Protocol

from dd_harness.projects import Decision
from dd_harness.requirements import Resolved
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import DocumentVersionRef, Envelope, Principal

# The artifacts the conductor keeps with each run.
SPANS = "spans.jsonl"  # the OpenTelemetry trace the grounding linter checked
GROUNDING = "grounding.txt"  # the grounding linter's summary
SOURCES = "sources.txt"  # the source check's summary
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


class ProjectStorage(Protocol):
    """Where the harness keeps each project's log of events, and the content they added
    (docs/specs/projects.md).

    A backend keeps these guarantees:

    1. A project's log is append-only: an event is never changed or removed, and events come
       back in the order they were appended.
    2. A change checked against the log (`edit`, `decide`, `record_draft`) reads the log and
       appends its events as one atomic step for that project: no other change to the project
       comes between. The file backend holds a per-project lock; a database would use a
       transaction or a conditional insert. Events a change writes together (an edit and its
       approval) are kept together or not at all.
    3. Projects do not wait on one another.
    4. Content an event adds is kept once by digest, and read back byte for byte.
    5. `project_of` finds a conversation's project from what is stored, so it holds after a
       restart.
    6. A malformed `project_id` names no project.
    """

    def create(self, *, acted_for: Principal, caused_by: str, title: str | None = None) -> str:
        """A new project and its `project_created` event; returns its `project_id`."""
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

    def summary(self, project_id: str) -> dict[str, Any]:
        """What a list of projects shows of one."""
        ...

    def exists(self, project_id: str) -> bool:
        """Whether the project exists."""
        ...

    def add_inventory(
        self,
        project_id: str,
        inventory: Mapping[str, Any],
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> str:
        """Add a `FileInventory`; returns its digest."""
        ...

    def choose_repository(
        self, project_id: str, resolved: Resolved, *, acted_for: Principal, caused_by: str
    ) -> str:
        """Record the repository chosen; returns the merged requirement set's digest."""
        ...

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

    def documents(self, project_id: str) -> list[dict[str, Any]]:
        """Each document of the project, with every version and its text."""
        ...

    def events(self, project_id: str) -> list[dict[str, Any]]:
        """Every event of the project, oldest first."""
        ...

    def inventory(self, project_id: str) -> dict[str, Any] | None:
        """The inventory added last, or None."""
        ...

    def requirements(self, project_id: str) -> dict[str, Any] | None:
        """The merged requirements of the repository chosen last, or None."""
        ...
