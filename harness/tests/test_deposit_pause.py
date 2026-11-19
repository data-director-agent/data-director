"""The pause before deposit: what a person must decide, what was not checked, and the
confirmation of the checks C2 asks for (docs/specs/deposit.md, invariants 20 to 22)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from requirement_sets import ORDA, override, pinned, standard, write

from dd_harness.deposit import INFO, VIOLATION, WARNING, Validation, validate
from dd_harness.deposit_pause import CONFIRMATION_CHECK, DECISION_CHECK, PERSONAL_DATA_CHECK
from dd_harness.projects import (
    DEPOSIT_CHECKS_CONFIRMED,
    FACT_DECIDED,
    FactVerdict,
    ProjectError,
    ProjectStore,
)
from dd_harness.requirements import load_requirements
from dd_harness.testing import TEST_PRINCIPAL, file_inventory, file_inventory_of_parts

# The shape of dataset A (data-director-agent/sample-data): field notes with personal data, a
# table of sites with coordinates, a reference file from someone else and an access agreement.
NOTES = "notes/fieldnotes_2025.txt"
SITES = "calibration/sites.csv"
REFERENCE = "reference/WeatherNest_Stn442_hourly.csv"
AGREEMENT = "governance/access_agreement.pdf"
READINGS = "data/readings.csv"
DATASET_A = (NOTES, SITES, REFERENCE, AGREEMENT, READINGS)


def finding(path: str, kind: str, target: str, column: str | None = None) -> dict[str, Any]:
    found = {
        "finding_kind": kind,
        "finding_file": path,
        "finding_target": target,
        "finding_confidence": "medium",
        "finding_detector": "test detector 1.0",
    }
    return found | ({"finding_column": column} if column else {})


FINDINGS = [
    finding(NOTES, "phone number", "text"),
    finding(NOTES, "email address", "text"),
    finding(SITES, "location", "field name"),
]


def proposal(path: str, check: str, because: str) -> dict[str, Any]:
    return {
        "fact_kind": "file_inclusion",
        "fact_subject": path,
        "fact_file_path": path,
        "file_decision": "undecided",
        "fact_check_kind": check,
        "proposed_because": because,
    }


@pytest.fixture
def projects(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "projects")


def project(projects: ProjectStore, tmp_path: Path, inventory: dict[str, Any]) -> str:
    """A project holding `inventory`, with ORDA chosen."""
    project_id = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test", title="Moor")
    projects.add_inventory(project_id, inventory, acted_for=TEST_PRINCIPAL, caused_by="test")
    folder = tmp_path / "repositories"
    repositories = write(folder, ("standards", standard()), ("overrides", override()))
    projects.choose_repository(
        project_id,
        ORDA,
        registry=pinned(folder / "re3data"),
        requirements=load_requirements(repositories),
        acted_for=TEST_PRINCIPAL,
        caused_by="test",
    )
    return project_id


@pytest.fixture
def dataset_a(projects: ProjectStore, tmp_path: Path) -> str:
    """Dataset A's project: the inventory's findings name the field notes and the sites, and a
    check proposed that a person decide whether the reference file and the agreement go in."""
    inventory = {**file_inventory(*DATASET_A), "inventory_personal_data": FINDINGS}
    project_id = project(projects, tmp_path, inventory)
    projects.propose_facts(
        project_id,
        [
            proposal(REFERENCE, "third_party", "It is in a folder of someone else's material."),
            proposal(AGREEMENT, "governance", "Its name suggests terms or an agreement."),
        ],
        agent_id="advisor.check",
        acted_for=TEST_PRINCIPAL,
        caused_by="check",
    )
    return project_id


def of(validation: Validation, component: str, severity: str) -> list[str]:
    return [
        r.focus.rsplit("#file/", 1)[-1]
        for r in validation.results
        if r.component == component and r.severity == severity
    ]


def decide(projects: ProjectStore, project_id: str, fact: dict[str, Any]) -> None:
    projects.decide_fact(
        project_id, FactVerdict.CHANGED, fact=fact, acted_for=TEST_PRINCIPAL, caused_by="test"
    )


@pytest.mark.requirement("C2")
def test_each_file_a_person_must_decide_pauses_the_deposit_until_one_does(
    projects: ProjectStore, dataset_a: str
) -> None:
    projects.confirm_checks(dataset_a, acted_for=TEST_PRINCIPAL, caused_by="test")
    paused = validate(projects, dataset_a)
    assert not paused.conforms
    waiting = of(paused, DECISION_CHECK, VIOLATION)
    assert sorted(waiting) == sorted((NOTES, SITES, REFERENCE, AGREEMENT))
    # A finding is named by its kind and place, never a value.
    notes = next(
        r for r in paused.violations if r.component == DECISION_CHECK and "notes" in r.message
    )
    assert "phone number" in notes.message and "email address" in notes.message

    decide(
        projects,
        dataset_a,
        {
            "fact_kind": "sensitivity",
            "fact_subject": NOTES,
            "sensitive_subject": NOTES,
            "sensitivity_decision": "withhold",
        },
    )
    decide(
        projects,
        dataset_a,
        {
            "fact_kind": "sensitivity",
            "fact_subject": SITES,
            "sensitive_subject": SITES,
            "sensitivity_decision": "generalise",
            "location_precision": "region",
        },
    )
    for path in (REFERENCE, AGREEMENT):
        decide(
            projects,
            dataset_a,
            {
                "fact_kind": "file_inclusion",
                "fact_subject": path,
                "fact_file_path": path,
                "file_decision": "exclude",
            },
        )
    cleared = validate(projects, dataset_a)
    assert of(cleared, DECISION_CHECK, VIOLATION) == []
    # Each decision is in the project log, with who made it and when.
    decided = [e for e in projects.events(dataset_a) if e["event"] == FACT_DECIDED]
    assert len(decided) == 4
    assert all(e["acted_for"]["principal_id"] == TEST_PRINCIPAL.principal_id for e in decided)
    assert all(e["at"] for e in decided)


@pytest.mark.requirement("C2")
def test_a_fact_that_stands_undecided_still_pauses_the_deposit(
    projects: ProjectStore, tmp_path: Path
) -> None:
    inventory = {**file_inventory(READINGS), "inventory_personal_data": []}
    project_id = project(projects, tmp_path, inventory)
    decide(
        projects,
        project_id,
        {
            "fact_kind": "file_inclusion",
            "fact_subject": READINGS,
            "fact_file_path": READINGS,
            "file_decision": "undecided",
        },
    )
    assert of(validate(projects, project_id), DECISION_CHECK, VIOLATION) != []


@pytest.mark.requirement("C2")
def test_a_project_with_no_marks_still_says_what_was_not_checked(
    projects: ProjectStore, tmp_path: Path
) -> None:
    inventory = {**file_inventory(READINGS), "inventory_personal_data": []}
    project_id = project(projects, tmp_path, inventory)
    validation = validate(projects, project_id)
    assert of(validation, DECISION_CHECK, VIOLATION) == []
    assert of(validation, PERSONAL_DATA_CHECK, WARNING) == []
    # A note says what was not checked, so that no flag is never read as clearance.
    assert of(validation, PERSONAL_DATA_CHECK, INFO) != []


@pytest.mark.requirement("C2")
def test_an_inventory_made_before_findings_existed_is_a_warning_not_clearance(
    projects: ProjectStore, tmp_path: Path
) -> None:
    project_id = project(projects, tmp_path, file_inventory(READINGS))
    validation = validate(projects, project_id)
    assert of(validation, PERSONAL_DATA_CHECK, WARNING) != []
    assert [r for r in validation.notes if r.component == PERSONAL_DATA_CHECK] == []


def test_each_part_made_without_the_check_is_named(projects: ProjectStore, tmp_path: Path) -> None:
    inventory = file_inventory_of_parts({"field": ["a.csv"], "lab": ["b.csv"]})
    inventory["inventory_parts"][0]["part_personal_data"] = []
    project_id = project(projects, tmp_path, inventory)
    (warning,) = [
        r for r in validate(projects, project_id).warnings if r.component == PERSONAL_DATA_CHECK
    ]
    assert "lab" in warning.message


@pytest.mark.requirement("C2")
def test_the_checks_before_deposit_are_confirmed_for_the_inventory_held_now(
    projects: ProjectStore, dataset_a: str
) -> None:
    assert of(validate(projects, dataset_a), CONFIRMATION_CHECK, VIOLATION) != []
    digest = projects.confirm_checks(dataset_a, acted_for=TEST_PRINCIPAL, caused_by="test")
    confirmed = projects.events(dataset_a)[-1]
    assert confirmed["event"] == DEPOSIT_CHECKS_CONFIRMED
    assert confirmed["inventory_digest"] == digest
    assert confirmed["statements"]
    assert confirmed["acted_for"]["principal_id"] == TEST_PRINCIPAL.principal_id
    validation = validate(projects, dataset_a)
    assert of(validation, CONFIRMATION_CHECK, VIOLATION) == []
    assert of(validation, CONFIRMATION_CHECK, INFO) != []

    # A new inventory needs a new confirmation.
    projects.add_inventory(
        dataset_a, file_inventory(READINGS), acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    assert projects.checks_confirmation(dataset_a) is None
    assert of(validate(projects, dataset_a), CONFIRMATION_CHECK, VIOLATION) != []


def test_the_checks_cannot_be_confirmed_before_there_is_an_inventory(
    projects: ProjectStore,
) -> None:
    project_id = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test", title="Empty")
    with pytest.raises(ProjectError):
        projects.confirm_checks(project_id, acted_for=TEST_PRINCIPAL, caused_by="test")
    assert [e["event"] for e in projects.events(project_id)][-1] != DEPOSIT_CHECKS_CONFIRMED
