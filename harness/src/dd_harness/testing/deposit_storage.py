"""Conformance checks of what a project's storage keeps of its deposits: validation reports and
packages by digest, and a person's approval of a deposit through a repository's API with its
outcome (docs/specs/deposit.md, invariants 8, 9, 12 and 15). `dd_harness.testing.storage` runs them
among `PROJECT_STORAGE_CHECKS`."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from dd_harness.projects import (
    DEPOSIT_APPROVED,
    DEPOSIT_FAILED,
    DEPOSIT_RECORDED,
    PACKAGE_BUILT,
    PROJECT_VALIDATED,
    DepositInProgressError,
    UnknownProjectError,
)
from dd_harness.storage import ProjectStorage
from dd_harness.testing.fixtures import TEST_PRINCIPAL
from dd_sdk.evidence import input_hash

type MakeProjectStorage = Callable[[str], ProjectStorage]

# A project identifier that names no project.
NOWHERE = "0" * 8 + "-0000-7000-8000-" + "0" * 12


@contextmanager
def _raises(kind: type[Exception], what: str) -> Iterator[None]:
    """Fails unless the block raises `kind`; `what` says what should have been refused."""
    try:
        yield
    except kind:
        return
    raise AssertionError(f"{what}: expected {kind.__name__}")


def check_a_report_and_a_package_are_kept_by_digest(make: MakeProjectStorage) -> None:
    """A validation report and a deposit package are kept by digest and named in the log
    (docs/specs/deposit.md, invariants 8 and 9); a package the log does not name is not found."""
    store = make("projects")
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="check")
    report = {"@type": "sh:ValidationReport", "sh:conforms": True}
    report_digest = store.record_validation(
        project_id,
        report,
        conforms=True,
        requirements_digest=None,
        acted_for=TEST_PRINCIPAL,
        caused_by="check",
    )
    assert report_digest == input_hash(report)
    package = b"PK\x05\x06" + bytes(18)
    digest = store.record_package(
        project_id,
        package,
        about={"report_digest": report_digest, "event": "not this"},
        acted_for=TEST_PRINCIPAL,
        caused_by="check",
    )
    assert digest == hashlib.sha256(package).hexdigest()
    validated, built = make("projects").events(project_id)[-2:]
    assert (validated["event"], validated["digest"]) == (PROJECT_VALIDATED, report_digest)
    assert validated["conforms"] is True
    assert (built["event"], built["digest"]) == (PACKAGE_BUILT, digest)
    assert built["report_digest"] == report_digest
    assert make("projects").package(project_id, digest) == package
    assert store.package(project_id, "0" * 64) is None
    with _raises(UnknownProjectError, "a package of an unknown project"):
        store.record_package(
            NOWHERE, package, about={}, acted_for=TEST_PRINCIPAL, caused_by="check"
        )


def check_a_package_is_approved_for_deposit_once(make: MakeProjectStorage) -> None:
    """A package approved for a repository is not approved again while that deposit has no
    outcome, nor after it made a draft; after a failure it may be (docs/specs/deposit.md,
    invariants 12 and 15). Each outcome names its approval, and a second store reads both."""
    store = make("projects")
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="check")
    named = {"digest": "a" * 64, "repository_id": "r3d100010468", "transport": "zenodo"}
    first = store.approve_deposit(project_id, named, acted_for=TEST_PRINCIPAL, caused_by="check")
    with _raises(DepositInProgressError, "a second approval while the first has no outcome"):
        store.approve_deposit(project_id, named, acted_for=TEST_PRINCIPAL, caused_by="check")
    store.record_deposit_outcome(
        project_id,
        {"approval": first["event_id"], **named, "status": 503, "reason": "x"},
        recorded=False,
        acted_for=TEST_PRINCIPAL,
        caused_by="check",
    )
    second = store.approve_deposit(project_id, named, acted_for=TEST_PRINCIPAL, caused_by="check")
    store.record_deposit_outcome(
        project_id,
        {"approval": second["event_id"], **named, "draft_url": "https://example.org/d/1"},
        recorded=True,
        acted_for=TEST_PRINCIPAL,
        caused_by="check",
    )
    with _raises(DepositInProgressError, "an approval of a package already deposited"):
        store.approve_deposit(project_id, named, acted_for=TEST_PRINCIPAL, caused_by="check")
    other = {**named, "repository_id": "r3d100012124"}
    store.approve_deposit(project_id, other, acted_for=TEST_PRINCIPAL, caused_by="check")
    kinds = [e["event"] for e in make("projects").events(project_id)]
    assert kinds[1:] == [
        DEPOSIT_APPROVED,
        DEPOSIT_FAILED,
        DEPOSIT_APPROVED,
        DEPOSIT_RECORDED,
        DEPOSIT_APPROVED,
    ]


DEPOSIT_STORAGE_CHECKS: dict[str, Callable[[MakeProjectStorage], None]] = {
    "a report and a package are kept by digest": check_a_report_and_a_package_are_kept_by_digest,
    "a package is approved for deposit once": check_a_package_is_approved_for_deposit_once,
}
