"""What a finished run does to its project (docs/specs/projects.md): the project rules the
conductor calls on, behind `ProjectEffects`, so that the conductor holds none of them.

A run in a project that succeeds with a `Document` is recorded in the project as a proposed
version, caused by the run; a draft the project refuses fails the run instead, and the conductor
writes that outcome. A `Reply` that names the project (`new_project_title`) renames it, caused by
the run, unless a person has given it a title; one that records an entry point
(`new_project_entry`) records it as the model's word, caused by the run, unless the researcher has
chosen one (docs/specs/orchestration.md, invariant 18). A project deleted while the run went takes
no new title or entry point (invariant 24), and its draft is still recorded.

A succeeded payload of any class that carries `proposed_facts` (`ProposesFacts`) has each
proposal recorded in the project for a person to decide, caused by the run
(`dd_harness.projects.facts`); the payload's class is never read. Proposals the project refuses
fail the run, as a refused draft does, and a project deleted while the run went takes none.

`Projects` implements `ProjectEffects` through `RunEffects`, from its own `record_draft`, `rename`,
`choose_entry` and `propose_facts`.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterable, Mapping
from typing import Any, Protocol

from dd_harness.progress import ENTRY_BY_MODEL, EntrySource
from dd_harness.project_errors import (
    TITLE_BY_MODEL,
    ProjectDeletedError,
    ProjectError,
    TitleSource,
)
from dd_sdk.contract.models import (
    DocumentVersionRef,
    Envelope,
    OutcomeStatus,
    Principal,
)

# The core payload class a run in a project records as a document version.
DOCUMENT = "Document"
# The core payload class whose `new_project_title` renames the run's project, and whose
# `new_project_entry` records its entry point.
REPLY = "Reply"
# The core slot of any payload whose facts are proposed to the run's project.
PROPOSED_FACTS = "proposed_facts"


class ProjectEffects(Protocol):
    """What the conductor asks of a project once a run in it is finished and its envelope keeps
    the contract."""

    def after_run(self, envelope: Envelope, *, acted_for: Principal) -> str | None:
        """Apply the run's effects on its project. Returns why the project refused the run's
        draft, in which case nothing was recorded and the run is to fail; None otherwise,
        including for a run outside a project or one that did not succeed."""
        ...


class _ProjectRules(Protocol):
    """The project rules `RunEffects` is written over."""

    def record_draft(self, project_id: str, envelope: Envelope) -> DocumentVersionRef: ...

    def rename(
        self,
        project_id: str,
        title: str,
        *,
        source: TitleSource,
        acted_for: Principal,
        caused_by: str,
    ) -> bool: ...

    def choose_entry(
        self,
        project_id: str,
        entry: int,
        *,
        acted_for: Principal,
        caused_by: str,
        source: EntrySource = ...,
    ) -> bool: ...

    def propose_facts(
        self,
        project_id: str,
        facts: Iterable[Mapping[str, Any]],
        *,
        agent_id: str,
        acted_for: Principal,
        caused_by: str,
    ) -> list[str]: ...


class RunEffects:
    """`ProjectEffects` over the project rules, for `Projects` to inherit."""

    def after_run(self: _ProjectRules, envelope: Envelope, *, acted_for: Principal) -> str | None:
        project_id = envelope.project_id
        if project_id is None or envelope.outcome.status != OutcomeStatus.SUCCEEDED:
            return None
        payload: dict[str, Any] = envelope.to_document().get("payload") or {}
        if proposed := payload.get(PROPOSED_FACTS):
            try:
                self.propose_facts(
                    project_id,
                    proposed,
                    agent_id=envelope.agent_id,
                    acted_for=acted_for,
                    caused_by=envelope.invocation_id,
                )
            except ProjectDeletedError:
                pass
            except ProjectError as exc:
                return f"its proposed facts were refused: {exc}"
        schema_class = payload.get("schema_class")
        if schema_class == DOCUMENT:
            try:
                self.record_draft(project_id, envelope)
            except ProjectError as exc:
                return str(exc)
        elif schema_class == REPLY:
            caused_by = envelope.invocation_id
            # The name and the entry point passed the contract already.
            if title := payload.get("new_project_title"):
                with contextlib.suppress(ProjectDeletedError):
                    self.rename(
                        project_id,
                        str(title),
                        source=TITLE_BY_MODEL,
                        acted_for=acted_for,
                        caused_by=caused_by,
                    )
            if (entry := payload.get("new_project_entry")) is not None:
                with contextlib.suppress(ProjectDeletedError):
                    self.choose_entry(
                        project_id,
                        int(entry),
                        source=ENTRY_BY_MODEL,
                        acted_for=acted_for,
                        caused_by=caused_by,
                    )
        return None
