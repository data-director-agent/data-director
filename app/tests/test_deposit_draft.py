"""Depositing a draft through a repository's API from the app (docs/specs/deposit.md, Depositing
through an API): the server records the signed-in person's approval and asks the deposit broker for
a draft with their own account, and says how it went."""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from pathlib import Path

import pytest
from starlette.testclient import TestClient
from support import JSON_HEADERS, check_fixture, configure_env, dist_dir, new_governance, pin_export
from test_deposit_package import RECORD, chosen, normalised, ready, store, valid

from dd_app.app import Links, build_app
from dd_app.governance import Governance
from dd_app.routes.deposit import DepositRefusedProblem, Deposits, DepositShown
from dd_app.routes.session import RepositoryTicket
from dd_harness.projects import DEPOSIT_APPROVED, DEPOSIT_RECORDED
from dd_harness.storage import ProjectStorage
from dd_harness.testing import TEST_PRINCIPAL, FakeDepositBroker, GrantKeys
from dd_sdk.deposit_grant import TICKET_TYPE, DepositReason

__all__ = ["RECORD", "chosen", "ready", "store", "valid"]


@pytest.fixture
def broker() -> FakeDepositBroker:
    return FakeDepositBroker()


@pytest.fixture
def governance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, broker: FakeDepositBroker
) -> Iterator[Governance]:
    """The app's reference set, whose Zenodo override deposits to the sandbox, with a deposit
    broker in memory."""
    configure_env(monkeypatch, tmp_path)
    monkeypatch.setenv("DD_SOURCES_CONFIG", str(pin_export(tmp_path / "re3data")))
    for governance in new_governance():
        governance.deposit_broker = broker.deposit_broker()
        yield governance


@pytest.fixture
def client(governance: Governance, tmp_path: Path) -> TestClient:
    return TestClient(
        build_app(
            governance, dist_dir(tmp_path), links=Links(deposit_broker_path="/deposit-broker")
        )
    )


def built(client: TestClient, project_id: str) -> str:
    answer = client.post(f"/api/projects/{project_id}/package", headers=JSON_HEADERS)
    assert answer.status_code == 201, answer.text
    digest: str = answer.json()["package"]["digest"]
    return digest


def test_the_project_says_it_can_be_deposited_to_the_zenodo_sandbox(
    client: TestClient, chosen: str
) -> None:
    answer = client.get(f"/api/projects/{chosen}/deposits")
    assert answer.status_code == 200
    body = answer.json()
    assert body == {
        "connection": {
            "repository_name": "Zenodo",
            "transport": "zenodo",
            "base_url": "https://sandbox.zenodo.org/api",
            "sandbox": True,
            "available": True,
            "unavailable": None,
        },
        "deposits": [],
    }
    check_fixture("project-deposits-none.json", body, model=Deposits)


def test_approving_a_deposit_makes_a_draft_with_the_persons_account(
    client: TestClient, ready: str, store: ProjectStorage, broker: FakeDepositBroker
) -> None:
    digest = built(client, ready)
    answer = client.post(f"/api/projects/{ready}/deposits", json={"digest": digest})
    assert answer.status_code == 201, answer.text
    shown = answer.json()
    assert shown["state"] == "recorded"
    assert shown["draft_url"] == "https://sandbox.zenodo.org/deposit/1001"
    assert shown["sandbox"] is True
    assert shown["approved_by"] == TEST_PRINCIPAL.name
    (received,) = broker.received
    assert received.pseudonym == broker.keys.minter().pseudonym(TEST_PRINCIPAL)
    assert broker.item()["metadata"]["title"] == RECORD["titles"][0]["title"]
    kinds = [e["event"] for e in store.events(ready)]
    assert kinds[-2:] == [DEPOSIT_APPROVED, DEPOSIT_RECORDED]
    listed = client.get(f"/api/projects/{ready}/deposits").json()
    assert listed["deposits"] == [shown]
    check_fixture("project-deposit-recorded.json", normalised(shown), model=DepositShown)
    check_fixture("project-deposits.json", normalised(listed), model=Deposits)

    again = client.post(f"/api/projects/{ready}/deposits", json={"digest": digest})
    assert again.status_code == 409
    assert again.json()["refusal"] == "already-deposited"
    assert again.json()["draft_url"] == shown["draft_url"]


def test_a_failed_deposit_is_shown_with_its_reason(
    client: TestClient, ready: str, broker: FakeDepositBroker
) -> None:
    broker.failing = (403, DepositReason.ACCOUNT_MISSING)
    digest = built(client, ready)
    answer = client.post(f"/api/projects/{ready}/deposits", json={"digest": digest})
    assert answer.status_code == 201
    shown = answer.json()
    assert (shown["state"], shown["reason"]) == ("failed", "account-missing")
    assert "draft_url" not in shown
    check_fixture("project-deposit-failed.json", normalised(shown), model=DepositShown)


def test_a_deposit_that_cannot_be_approved_records_nothing(
    client: TestClient, ready: str, store: ProjectStorage, governance: Governance
) -> None:
    digest = built(client, ready)
    governance.conductor.profile = dataclasses.replace(
        governance.conductor.profile, deposit_transports=frozenset()
    )
    before = store.events(ready)
    answer = client.post(f"/api/projects/{ready}/deposits", json={"digest": digest})
    assert answer.status_code == 409
    assert answer.json()["refusal"] == "transport-not-offered"
    assert DepositRefusedProblem.model_validate(answer.json())
    assert store.events(ready) == before
    shown = client.get(f"/api/projects/{ready}/deposits").json()["connection"]
    assert (shown["available"], shown["unavailable"]) == (False, "transport-not-offered")


def test_a_malformed_digest_is_refused(client: TestClient, ready: str) -> None:
    answer = client.post(f"/api/projects/{ready}/deposits", json={"digest": "nope"})
    assert answer.status_code == 400


def test_a_repository_account_ticket_is_for_the_deposit_broker(
    client: TestClient, broker: FakeDepositBroker
) -> None:
    session = client.get("/api/session", headers=JSON_HEADERS).json()
    assert session["repository_accounts"] is True
    answer = client.post("/api/repository-account/ticket", headers=JSON_HEADERS)
    assert answer.status_code == 200
    body = RepositoryTicket.model_validate(answer.json())
    assert body.deposit_broker_url == "/deposit-broker"
    assert answer.headers["cache-control"] == "no-store"
    sealed_to_broker = GrantKeys(broker.keys.signing_key, broker.subject_key, broker.keys.secret)
    opened = sealed_to_broker.open(body.ticket)
    assert opened.header["typ"] == TICKET_TYPE
    assert opened.pseudonym == broker.keys.minter().pseudonym(TEST_PRINCIPAL)


def test_without_a_deposit_broker_no_account_is_offered(
    governance: Governance, tmp_path: Path
) -> None:
    governance.deposit_broker = None
    client = TestClient(
        build_app(
            governance, dist_dir(tmp_path), links=Links(deposit_broker_path="/deposit-broker")
        )
    )
    assert client.get("/api/session", headers=JSON_HEADERS).json()["repository_accounts"] is False
    refused = client.post("/api/repository-account/ticket", headers=JSON_HEADERS)
    assert refused.status_code == 404
