"""The conformance checks only a backend whose section holds across instances passes: two logs
opened over one record, as two harness processes over one database, contend for one project
(docs/specs/storage.md, invariants 10 and 11). The file backend's lock holds within one instance,
so these are not among `PROJECT_LOG_CHECKS` (`dd_harness.testing.storage`)."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from dd_harness.projects import (
    APPROVED,
    DOCUMENT_CHANGE_REFUSED,
    DOCUMENT_VERSION_DECIDED,
    ChangeRefusedError,
    Decision,
    Projects,
)
from dd_harness.storage import ProjectLog
from dd_harness.testing.fixtures import TEST_PRINCIPAL
from dd_harness.testing.storage import (
    MakeProjectLog,
    _enter,
    _log_event,
    _named,
    _new_project,
    drafted_readme,
)


def check_logs_over_one_record_share_each_section(make: MakeProjectLog) -> None:
    """Sections on one project through two logs over one record exclude one another and lose none
    of one another's events, and neither holds up another project (storage.md, invariant 10)."""
    logs = (make("log"), make("log"))
    busy, idle = _new_project(logs[0]), _new_project(logs[1])
    writers, rounds = 4, 5
    start = threading.Barrier(writers)

    def count(log: ProjectLog) -> None:
        start.wait()
        for _ in range(rounds):
            with log.section(busy) as section:
                seen = len(section.events())
                time.sleep(0.001)
                section.append([_log_event(busy, "check_event", seen=seen)])

    threads = [threading.Thread(target=count, args=(logs[n % 2],)) for n in range(writers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    seen = [e["seen"] for e in logs[1].events(busy)[1:]]
    assert seen == list(range(1, writers * rounds + 1)), "a section saw another log's partial work"

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
    deciders = 8
    start = threading.Barrier(deciders)
    outcomes: list[str] = []
    guard = threading.Lock()

    def decide(store: Projects) -> None:
        start.wait()
        try:
            store.decide(project_id, decision, acted_for=TEST_PRINCIPAL, caused_by="check")
            outcome = "decided"
        except ChangeRefusedError:
            outcome = "refused"
        with guard:
            outcomes.append(outcome)

    threads = [threading.Thread(target=decide, args=(stores[n % 2],)) for n in range(deciders)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert sorted(outcomes) == ["decided"] + ["refused"] * (deciders - 1), outcomes
    kinds = [e["event"] for e in Projects(make("projects")).events(project_id)]
    assert kinds.count(DOCUMENT_VERSION_DECIDED) == 1
    assert kinds.count(DOCUMENT_CHANGE_REFUSED) == deciders - 1


SHARED_RECORD_CHECKS: dict[str, Callable[[MakeProjectLog], None]] = {
    "logs over one record share each section": check_logs_over_one_record_share_each_section,
    "stores over one record admit one decision": (check_stores_over_one_record_admit_one_decision),
}


def check_shared_record(make: MakeProjectLog) -> None:
    """Every check of logs that several harness instances open over one record, each on a record
    of its own. Only a backend whose section holds across instances passes."""
    for n, check in enumerate(SHARED_RECORD_CHECKS.values()):
        check(_named(make, n))
