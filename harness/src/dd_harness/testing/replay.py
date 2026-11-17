"""A conformance check that a backend's project log replays as its events fold
(docs/specs/storage.md, docs/specs/projects.md).

The project rules hold no state but the log: each read folds the events the log returns
(`dd_harness.projects.fold`). So a log appended in one section and the same log appended an event
at a time must fold to the same documents, after every event as well as at the end, and after the
store is opened again. `check_a_log_replays_as_it_folds` holds a backend to that for any sequence
of changes; the harness's tests give it sequences that Hypothesis generates, against each backend.

A change is an event's kind and detail, as the project rules write them, without the fields every
event carries (`event_id`, `project_id`, `at`, `acted_for`, `caused_by`); a
`document_version_added` change carries its `text` in place of the digest, and the check keeps
the text by its digest.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from dd_harness.project_log import ProjectLog
from dd_harness.projects import PROJECT_CREATED, Projects, text_digest
from dd_harness.projects.fold import fold
from dd_harness.testing.fixtures import TEST_PRINCIPAL
from dd_sdk.contract.models import new_invocation_id

type MakeProjectLog = Callable[[str], ProjectLog]

# One document drafted, answered, rejected, revised and approved, among events the fold ignores.
SAMPLE_CHANGES: tuple[dict[str, Any], ...] = (
    {
        "event": "document_version_added",
        "document_id": "readme",
        "document_kind": "readme",
        "version": 1,
        "text": "# Moorland sensors\n",
        "media_type": "text/markdown",
        "document_title": "README",
        "questions": [
            {
                "question_id": "q-0123456789abcdef",
                "question_prompt": "Which licence?",
                "gap_section": "licence",
            }
        ],
    },
    {"event": "conversation_started", "conversation_id": "c1"},
    {
        "event": "document_question_answered",
        "document_id": "readme",
        "version": 1,
        "question_id": "q-0123456789abcdef",
        "answer_text": "CC BY 4.0",
    },
    {
        "event": "document_version_decided",
        "document_id": "readme",
        "version": 1,
        "decision": "rejected",
        "reason": "Name the licence.",
    },
    {
        "event": "document_version_added",
        "document_id": "readme",
        "document_kind": "readme",
        "version": 2,
        "text": "# Moorland sensors\n\nLicence: CC BY 4.0 ✓\n",
        "media_type": "text/markdown",
        "revises": 1,
    },
    {
        "event": "document_version_decided",
        "document_id": "readme",
        "version": 2,
        "decision": "approved",
    },
)


def stamped(project_id: str, changes: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """`changes` as the project's log holds them, after its `project_created` event: each with
    the fields every event carries, a time a second after the last, and a version's text replaced
    by its digest."""
    start = datetime(2026, 1, 1, tzinfo=UTC)
    events = []
    for n, change in enumerate([{"event": PROJECT_CREATED}, *changes]):
        detail = {key: value for key, value in change.items() if key != "text"}
        if "text" in change:
            detail["digest"] = text_digest(change["text"])
        events.append(
            {
                "event_id": new_invocation_id(),
                "project_id": project_id,
                "at": (start + timedelta(seconds=n)).isoformat(),
                "acted_for": TEST_PRINCIPAL.model_dump(mode="json", exclude_none=True),
                "caused_by": "check",
                **detail,
            }
        )
    return events


def _opened(log: ProjectLog, created: dict[str, Any], changes: Sequence[dict[str, Any]]) -> None:
    """The project `created` creates, in `log`, holding the text of every version `changes` add."""
    project_id: str = created["project_id"]
    log.create(project_id, created)
    for change in changes:
        if "text" in change:
            text: str = change["text"]
            log.keep_blob(project_id, text_digest(text), text.encode("utf-8"))


def check_a_log_replays_as_it_folds(
    make: MakeProjectLog, changes: Sequence[dict[str, Any]] = SAMPLE_CHANGES
) -> None:
    """A log appended whole and one appended an event at a time fold as the events themselves
    do: after each event, at the end, and once opened again; and the project rules read the same
    documents from both. `make` opens a store by name, as in `dd_harness.testing.storage`; give
    each call names of its own."""
    whole, stepwise = make("whole"), make("stepwise")
    project_id = new_invocation_id()
    events = stamped(project_id, changes)
    for log in (whole, stepwise):
        _opened(log, events[0], changes)
    with whole.section(project_id) as section:
        section.append(events[1:])
    for n in range(1, len(events)):
        with stepwise.section(project_id) as section:
            section.append([events[n]])
        assert fold(stepwise.events(project_id)) == fold(events[: n + 1]), (
            f"the log folds otherwise after event {n}, {events[n]['event']!r}"
        )
    for name in ("whole", "stepwise"):
        assert make(name).events(project_id) == events, f"the {name} log reads back otherwise"
    assert fold(whole.events(project_id)) == fold(stepwise.events(project_id)) == fold(events)
    assert Projects(make("whole")).documents(project_id) == Projects(make("stepwise")).documents(
        project_id
    )
