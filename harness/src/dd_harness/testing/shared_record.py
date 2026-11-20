"""The conformance checks only a backend whose section holds across instances passes: two logs
opened over one record, as two harness processes over one database, contend for one project
(docs/specs/storage.md, invariants 10 and 11). The file backend's lock holds within one instance,
so these are not among `PROJECT_LOG_CHECKS` (`dd_harness.testing.storage`)."""

from __future__ import annotations

import threading
from collections.abc import Callable

from dd_harness.projects import (
    APPROVED,
    Decision,
    Projects,
)
from dd_harness.testing.fixtures import TEST_PRINCIPAL
from dd_harness.testing.storage import (
    MakeProjectLog,
    _enter,
    _named,
    _new_project,
    admit_one_decision,
    count_in_sections,
    drafted_readme,
)


def check_logs_over_one_record_share_each_section(make: MakeProjectLog) -> None:
    """Sections on one project through two logs over one record exclude one another and lose none
    of one another's events, and neither holds up another project (storage.md, invariant 10)."""
    logs = (make("log"), make("log"))
    busy, idle = _new_project(logs[0]), _new_project(logs[1])
    count_in_sections(logs, busy)

    waiting, entered = threading.Event(), threading.Event()
    with logs[0].section(busy):
        other = threading.Thread(target=lambda: _enter(logs[1], idle, entered))
        other.start()
        assert entered.wait(timeout=10), "a section on one project held up another"
        other.join(timeout=10)
        held = threading.Thread(target=lambda: _enter(logs[1], busy, waiting))
        held.start()
        assert not waiting.wait(timeout=0.5), "another log entered a section that was held"
    assert waiting.wait(timeout=10), "a section ended and another log still could not enter"
    held.join(timeout=10)


def check_stores_over_one_record_admit_one_decision(make: MakeProjectLog) -> None:
    """People deciding on one version through two stores over one record: one decision is
    recorded and every other refused and recorded (docs/specs/storage.md, invariants 10 and 11)."""
    stores = (Projects(make("projects")), Projects(make("projects")))
    project_id = stores[0].create(acted_for=TEST_PRINCIPAL, caused_by="check")
    ref = stores[1].record_draft(project_id, drafted_readme())
    (document,) = stores[0].documents(project_id)
    decision = Decision(ref.document_id, ref.version, document["versions"][-1]["digest"], APPROVED)
    admit_one_decision(stores, Projects(make("projects")), project_id, decision)


SHARED_RECORD_CHECKS: dict[str, Callable[[MakeProjectLog], None]] = {
    "logs over one record share each section": check_logs_over_one_record_share_each_section,
    "stores over one record admit one decision": (check_stores_over_one_record_admit_one_decision),
}


def check_shared_record(make: MakeProjectLog) -> None:
    """Every check of logs that several harness instances open over one record, each on a record
    of its own. Only a backend whose section holds across instances passes."""
    for n, check in enumerate(SHARED_RECORD_CHECKS.values()):
        check(_named(make, n))
