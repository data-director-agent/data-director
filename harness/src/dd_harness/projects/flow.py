"""Where a project is in the Blueprint's process flow, and its intake (docs/specs/projects.md).

Where the project is in the process flow is derived from the log by `progress`, never stored
(`dd_harness.progress`, docs/specs/orchestration.md). The researcher's own word on it is two
events: `entry_chosen` (`choose_entry`, the last counts) and `step_marked` (`mark_step`: done,
skipped, or open again). An orchestrator's model may also record an `entry_chosen` it worked out
from what the researcher said, saying so in `entry_source`, until the researcher chooses one.
The intake's answers are events too (`answer_intake`, `dismiss_intake`, rule 20): an answer to the
entry question is an `entry_chosen`, any other an `intake_answered`, and a dismissal an
`intake_dismissed`. Where the intake stands is derived, like progress (`dd_harness.intake`).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from dd_harness import intake as intake_rules
from dd_harness import progress as flow
from dd_harness.projects.rules import ProjectError, ProjectRules
from dd_sdk.contract.models import Principal
from dd_sdk.intake import ENTRY as ENTRY_QUESTION


class Flow(ProjectRules):
    """The rules of a project's place in the process flow and of its intake."""

    def choose_entry(
        self,
        project_id: str,
        entry: int,
        *,
        acted_for: Principal,
        caused_by: str,
        source: flow.EntrySource = flow.ENTRY_BY_RESEARCHER,
    ) -> bool:
        """Record the Blueprint entry point (1, 2 or 3) the researcher chose, or an
        orchestrator's model worked out from what they said; the last counts. Returns False, and
        records nothing, for a model's entry point once the researcher has chosen one. Raises
        `ProjectError` for an unknown project, entry point or source."""
        if source not in (flow.ENTRY_BY_RESEARCHER, flow.ENTRY_BY_MODEL):
            raise ProjectError(
                f"an entry point is chosen by a researcher or a model, not {source!r}"
            )
        if entry not in (1, 2, 3):
            raise ProjectError(f"the Blueprint has no entry point {entry!r}")
        with self._section(project_id) as section:
            _, held = flow.entry_and_source(section.events())
            if source == flow.ENTRY_BY_MODEL and held == flow.ENTRY_BY_RESEARCHER:
                return False
            detail = {"entry": entry, "entry_source": source}
            section.append(
                [self._event(project_id, flow.ENTRY_CHOSEN, acted_for, caused_by, detail)]
            )
        return True

    def mark_step(
        self, project_id: str, step_id: str, mark: str, *, acted_for: Principal, caused_by: str
    ) -> None:
        """Record the researcher marking a process-flow step done, skipped, or open again.
        Raises `ProjectError` for an unknown project, a step that is not in scope, or a mark
        that is none of those."""
        self._require(project_id)
        if not flow.markable(step_id):
            raise ProjectError(f"{step_id!r} is not a process-flow step that may be marked")
        if mark not in flow.MARKS:
            raise ProjectError(f"a step is marked one of {', '.join(flow.MARKS)}, not {mark!r}")
        self._append(
            project_id,
            flow.STEP_MARKED,
            acted_for,
            caused_by,
            {"step_id": step_id, "mark": mark},
        )

    def answer_intake(
        self,
        project_id: str,
        question_id: str,
        answer_values: Sequence[str],
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> None:
        """Record the researcher's answer to an intake question (docs/specs/projects.md, rule 20):
        for the entry question, an `entry_chosen` of the entry point chosen; for any other, an
        `intake_answered`. The answer is checked against its question as a turn's answer is,
        and must be to a question asked from the project's entry point. Raises
        `UnknownProjectError` for an unknown project and `ProjectError` for an answer that fails
        the check, recording nothing."""
        with self._section(project_id) as section:
            entry = flow.entry_chosen(section.events())
            if problem := intake_rules.answer_problem(question_id, answer_values, entry):
                raise ProjectError(problem)
            if question_id == ENTRY_QUESTION:
                kind = flow.ENTRY_CHOSEN
                detail: dict[str, Any] = {
                    "entry": int(answer_values[0]),
                    "entry_source": flow.ENTRY_BY_RESEARCHER,
                }
            else:
                kind = flow.INTAKE_ANSWERED
                detail = {"question_id": question_id, "answer_values": list(answer_values)}
            section.append([self._event(project_id, kind, acted_for, caused_by, detail)])

    def dismiss_intake(self, project_id: str, *, acted_for: Principal, caused_by: str) -> None:
        """Record the researcher dismissing the intake, an `intake_dismissed`; an answer recorded
        later opens it again. Raises `UnknownProjectError` for an unknown project."""
        self._append(project_id, flow.INTAKE_DISMISSED, acted_for, caused_by, {})

    def progress(self, project_id: str) -> dict[str, Any]:
        """The entry point chosen and each step the log shows started, done or skipped. Raises
        `UnknownProjectError`."""
        return flow.describe(self.events(project_id))

    def intake(self, project_id: str) -> dict[str, Any]:
        """Where the project's intake stands, its questions with their current answers and the
        project's progress (`dd_harness.intake.describe`). Raises `UnknownProjectError`."""
        return intake_rules.describe(self.events(project_id))
