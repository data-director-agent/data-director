"""Depositing a draft through a repository's API after a person approves it (docs/specs/deposit.md,
Depositing through an API; invariants 11 to 15 and 17 to 19)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from requirement_sets import ORDA, override, pinned, standard, write
from test_deposit import FILES, RECORD, approve

from dd_harness.deposit import build_package
from dd_harness.deposit_api import (
    DepositRefusedError,
    DepositSetup,
    Refusal,
    approve_and_deposit,
    connection,
    deposits,
    summary,
)
from dd_harness.metadata_standards import registered
from dd_harness.projects import (
    DEPOSIT_APPROVED,
    DEPOSIT_FAILED,
    DEPOSIT_RECORDED,
    PACKAGE_BUILT,
    DepositInProgressError,
    ProjectStore,
)
from dd_harness.requirements import Requirements, load_requirements
from dd_harness.store import RunStore
from dd_harness.testing import (
    TEST_PRINCIPAL,
    FakeDepositBroker,
    clear_review,
    file_inventory,
)
from dd_harness.transports.zenodo import TRANSPORT as ZENODO
from dd_sdk.contract.models import DepositConnector, DocumentKind
from dd_sdk.deposit_grant import DepositReason
from dd_sdk.transports import discover

SANDBOX = {
    "transport": "zenodo",
    "format": "zenodo-deposit",
    "base_url": "https://sandbox.zenodo.org/api",
    "sandbox": True,
}
OFFERED = frozenset({"zenodo"})
TRANSPORTS = {"zenodo": ZENODO}


@pytest.fixture
def projects(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "projects")


@pytest.fixture
def runs(tmp_path: Path) -> RunStore:
    return RunStore(tmp_path / "runs")


@pytest.fixture
def requirements(tmp_path: Path) -> Requirements:
    folder = tmp_path / "repositories"
    return load_requirements(
        write(folder, ("standards", standard()), ("overrides", override(deposit=SANDBOX)))
    )


@pytest.fixture
def broker() -> FakeDepositBroker:
    return FakeDepositBroker()


@pytest.fixture
def packaged(
    projects: ProjectStore, runs: RunStore, requirements: Requirements, tmp_path: Path
) -> tuple[str, str]:
    """A project ready for ORDA, whose override deposits to the Zenodo sandbox, and its package's
    digest."""
    project_id = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test", title="Soil")
    projects.add_inventory(
        project_id, file_inventory(*FILES), acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    projects.choose_repository(
        project_id,
        ORDA,
        registry=pinned(tmp_path / "re3data"),
        requirements=requirements,
        acted_for=TEST_PRINCIPAL,
        caused_by="test",
    )
    approve(projects, runs, project_id, DocumentKind.METADATA_RECORD, json.dumps(RECORD))
    approve(projects, runs, project_id, DocumentKind.README)
    clear_review(projects, project_id, acted_for=TEST_PRINCIPAL)
    package = build_package(projects, runs, project_id, acted_for=TEST_PRINCIPAL, caused_by="test")
    return project_id, package.digest


def deposit(
    projects: ProjectStore,
    packaged: tuple[str, str],
    requirements: Requirements,
    broker: FakeDepositBroker | None,
    **changes: Any,
) -> dict[str, Any]:
    project_id, digest = packaged
    return approve_and_deposit(
        projects,
        project_id,
        changes.pop("digest", digest),
        requirements=requirements,
        setup=DepositSetup(
            offered=changes.pop("offered", OFFERED),
            transports=changes.pop("transports", TRANSPORTS),
            broker=None if broker is None else broker.deposit_broker(),
        ),
        acted_for=TEST_PRINCIPAL,
        caused_by="test",
    )


def test_an_approved_deposit_makes_a_draft_and_records_it(
    projects: ProjectStore,
    packaged: tuple[str, str],
    requirements: Requirements,
    broker: FakeDepositBroker,
) -> None:
    project_id, digest = packaged
    outcome = deposit(projects, packaged, requirements, broker)
    assert outcome["event"] == DEPOSIT_RECORDED
    assert outcome["draft_url"] == "https://sandbox.zenodo.org/deposit/1001"
    assert outcome["digest"] == digest
    assert outcome["transport"] == "zenodo"
    events = projects.events(project_id)
    approval = next(e for e in events if e["event"] == DEPOSIT_APPROVED)
    # The approval names the person, the package, the repository and the connector as configured.
    assert approval["acted_for"]["principal_id"] == TEST_PRINCIPAL.principal_id
    assert (approval["digest"], approval["repository_id"]) == (digest, ORDA)
    assert approval["base_url"] == "https://sandbox.zenodo.org/api"
    assert approval["sandbox"] is True
    assert outcome["approval"] == approval["event_id"]
    # The rendered item is kept as a package derived from the RO-Crate package (invariant 19).
    (item,) = [e for e in events if e["event"] == PACKAGE_BUILT and e["format"] == ZENODO.format]
    assert item["derived_from"] == digest
    assert item["digest"] == approval["item_digest"]
    # The broker was sent exactly the approved bytes, as the person who approved.
    (received,) = broker.received
    assert received.claims.package_digest == digest
    assert received.claims.approval == approval["event_id"]
    assert received.claims.base_url == "https://sandbox.zenodo.org/api"
    assert received.request.package == projects.package(project_id, digest)
    assert received.pseudonym == broker.keys.minter().pseudonym(TEST_PRINCIPAL)
    assert broker.item()["metadata"]["title"] == "Soil cores from Hope Valley"
    (shown,) = [summary(d) for d in deposits(projects, project_id)]
    assert shown["state"] == "recorded"
    assert shown["draft_url"] == outcome["draft_url"]


def test_a_second_approval_of_a_deposited_package_is_refused_and_names_the_draft(
    projects: ProjectStore,
    packaged: tuple[str, str],
    requirements: Requirements,
    broker: FakeDepositBroker,
) -> None:
    first = deposit(projects, packaged, requirements, broker)
    with pytest.raises(DepositInProgressError, match="already deposited") as refused:
        deposit(projects, packaged, requirements, broker)
    assert refused.value.earlier["draft_url"] == first["draft_url"]
    assert len(broker.received) == 1


@pytest.mark.parametrize(
    ("failing", "reason"),
    [
        ((403, DepositReason.ACCOUNT_MISSING), "account-missing"),
        ((401, DepositReason.ACCOUNT_REJECTED), "account-rejected"),
        ((400, DepositReason.ITEM_REJECTED), "item-rejected"),
        ((503, DepositReason.REPOSITORY_UNAVAILABLE), "repository-unavailable"),
    ],
)
def test_a_failed_deposit_is_an_outcome_and_may_be_approved_again(
    projects: ProjectStore,
    packaged: tuple[str, str],
    requirements: Requirements,
    broker: FakeDepositBroker,
    failing: tuple[int, DepositReason],
    reason: str,
) -> None:
    """Invariant 15: a failure is a `deposit_failed` event with a status and a reason code, not an
    exception; trying again needs a new approval."""
    broker.failing = failing
    outcome = deposit(projects, packaged, requirements, broker)
    assert outcome["event"] == DEPOSIT_FAILED
    assert (outcome["status"], outcome["reason"]) == (failing[0], reason)
    broker.failing = None
    again = deposit(projects, packaged, requirements, broker)
    assert again["event"] == DEPOSIT_RECORDED
    assert again["approval"] != outcome["approval"]


def test_an_unreachable_broker_is_a_failed_deposit(
    projects: ProjectStore, packaged: tuple[str, str], requirements: Requirements
) -> None:
    project_id, digest = packaged
    dead = FakeDepositBroker()
    unreachable = dead.deposit_broker()
    object.__setattr__(unreachable, "transport", None)
    object.__setattr__(unreachable, "url", "http://127.0.0.1:9")
    outcome = approve_and_deposit(
        projects,
        project_id,
        digest,
        requirements=requirements,
        setup=DepositSetup(OFFERED, TRANSPORTS, unreachable),
        acted_for=TEST_PRINCIPAL,
        caused_by="test",
    )
    assert outcome["event"] == DEPOSIT_FAILED
    assert outcome["reason"] == "broker-unavailable"


@pytest.mark.parametrize(
    ("changes", "refusal"),
    [
        ({"offered": frozenset()}, Refusal.NOT_OFFERED),
        ({"transports": {}}, Refusal.NOT_INSTALLED),
        ({"digest": "0" * 64}, Refusal.UNKNOWN_PACKAGE),
    ],
)
def test_nothing_is_approved_or_sent_when_the_deposit_cannot_be_made(
    projects: ProjectStore,
    packaged: tuple[str, str],
    requirements: Requirements,
    broker: FakeDepositBroker,
    changes: dict[str, Any],
    refusal: Refusal,
) -> None:
    """Invariants 12 and 17: an unoffered or unknown transport, or a package the log does not
    record, is refused before anything is approved, rendered or sent."""
    project_id, _ = packaged
    before = projects.events(project_id)
    with pytest.raises(DepositRefusedError) as refused:
        deposit(projects, packaged, requirements, broker, **changes)
    assert refused.value.refusal is refusal
    assert projects.events(project_id) == before
    assert broker.received == []


def test_without_a_deposit_broker_the_repository_is_deposited_to_by_hand(
    projects: ProjectStore, packaged: tuple[str, str], requirements: Requirements
) -> None:
    with pytest.raises(DepositRefusedError) as refused:
        deposit(projects, packaged, requirements, None)
    assert refused.value.refusal is Refusal.NO_BROKER


def test_a_repository_without_a_connector_is_deposited_to_by_hand(
    projects: ProjectStore, packaged: tuple[str, str], tmp_path: Path, broker: FakeDepositBroker
) -> None:
    by_hand = load_requirements(
        write(tmp_path / "by-hand", ("standards", standard()), ("overrides", override()))
    )
    project_id, _ = packaged
    found = connection(
        projects,
        project_id,
        requirements=by_hand,
        offered=OFFERED,
        transports=TRANSPORTS,
        broker=broker.deposit_broker(),
    )
    assert found is not None
    assert (found.connector, found.unavailable) == (None, Refusal.BY_HAND)
    with pytest.raises(DepositRefusedError, match="by hand"):
        deposit(projects, packaged, by_hand, broker)


def test_a_package_older_than_the_project_is_refused(
    projects: ProjectStore,
    runs: RunStore,
    packaged: tuple[str, str],
    requirements: Requirements,
    broker: FakeDepositBroker,
) -> None:
    project_id, _ = packaged
    approve(projects, runs, project_id, DocumentKind.README)
    with pytest.raises(DepositRefusedError) as refused:
        deposit(projects, packaged, requirements, broker)
    assert refused.value.refusal is Refusal.STALE


def test_the_grant_names_only_what_was_approved_and_carries_no_credential(
    projects: ProjectStore,
    packaged: tuple[str, str],
    requirements: Requirements,
    broker: FakeDepositBroker,
) -> None:
    """Invariant 13: the person is named only by their sealed pseudonym, and nothing the harness
    records or sends holds a token."""
    project_id, _ = packaged
    deposit(projects, packaged, requirements, broker)
    (received,) = broker.received
    assert TEST_PRINCIPAL.principal_id not in json.dumps(received.headers)
    logged = json.dumps(projects.events(project_id))
    assert "token" not in logged.lower()
    assert "authorization" not in {k.lower() for k in received.headers}


def test_zenodo_is_a_registered_transport() -> None:
    assert discover()["zenodo"] == ZENODO


def test_the_zenodo_item_maps_the_record_and_names_what_it_could_not_place() -> None:
    attributes = {
        **RECORD,
        "creators": [
            {
                "name": "Carberry, Josiah",
                "nameIdentifiers": [
                    {
                        "nameIdentifier": "https://orcid.org/0000-0002-1825-0097",
                        "nameIdentifierScheme": "ORCID",
                    }
                ],
                "affiliation": [{"name": "University of Sheffield"}],
            }
        ],
        "relatedIdentifiers": [
            {
                "relatedIdentifier": "10.1234/paper",
                "relatedIdentifierType": "DOI",
                "relationType": "IsSupplementTo",
            }
        ],
        "fundingReferences": [{"funderName": "NERC"}],
        "geoLocations": [{"geoLocationPlace": "Hope Valley"}],
        "publisher": {"name": "Zenodo"},
    }
    datacite = registered().get("datacite-4")
    assert datacite is not None
    pivot = datacite.read(json.dumps(attributes), "application/json").pivot()
    item = ZENODO.render(pivot, "data-director-practice")
    metadata = json.loads(item.content)["metadata"]
    assert metadata == {
        "access_right": "open",
        "communities": [{"identifier": "data-director-practice"}],
        "creators": [
            {
                "name": "Carberry, Josiah",
                "orcid": "0000-0002-1825-0097",
                "affiliation": "University of Sheffield",
            }
        ],
        "description": "Cores taken in 2026.",
        "keywords": ["soil science"],
        "license": "cc-by-4.0",
        "related_identifiers": [{"identifier": "10.1234/paper", "relation": "isSupplementTo"}],
        "title": "Soil cores from Hope Valley",
        "upload_type": "dataset",
    }
    assert item.unplaced == ("fundingReferences", "geoLocations")
    # The same record always renders to the same bytes, so an approval names exactly what is sent.
    assert ZENODO.render(pivot, "data-director-practice") == item
    assert "publish" not in item.content.decode()


def test_a_connector_holds_no_credential() -> None:
    with pytest.raises(ValueError, match="token"):
        DepositConnector.model_validate({**SANDBOX, "token": "secret"})
