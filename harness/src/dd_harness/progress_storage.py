"""What the harness asks of a store for a project's place in the process flow and its intake
(`dd_harness.projects.flow`, docs/specs/projects.md). `dd_harness.storage` composes it into
`ProjectStorage` with the other areas of the project rules; each record is a change checked
against the log, in the project's exclusive section, as `ProjectStorage` guarantee 2 says."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol

from dd_harness.progress import ENTRY_BY_RESEARCHER, EntrySource
from dd_sdk.contract.models import Principal


class ProjectProgress(Protocol):
    """A project's place in the process flow, and its intake (`dd_harness.projects.flow`)."""

    # The manifest entries of the agents the deployment enables, read for the suggested step.
    serving: Callable[[], Sequence[Mapping[str, Any]]]

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
