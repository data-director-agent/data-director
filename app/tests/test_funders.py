"""Looking up the organisation behind a funder in the pinned ROR dump, through the app's server, so
that the funder page can show what a name and identifier stand for (docs/specs/app.md)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from starlette.testclient import TestClient
from support import (
    ROR_DUMP,
    UKRI,
    check_fixture,
    configure_env,
    dist_dir,
    new_governance,
    pin_export,
    pin_ror,
)

from dd_app.app import build_app
from dd_app.governance import Governance
from dd_app.routes.funders import RorOrganisation
from dd_harness.sources import Sources

BARE = UKRI.removeprefix("https://ror.org/")


@pytest.fixture
def governance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Governance]:
    configure_env(monkeypatch, tmp_path)
    monkeypatch.setenv("DD_SOURCES_CONFIG", str(pin_ror(tmp_path / "ror")))
    yield from new_governance()


@pytest.fixture
def client(governance: Governance, tmp_path: Path) -> TestClient:
    return TestClient(build_app(governance, dist_dir(tmp_path)))


@pytest.mark.parametrize("given", [BARE, UKRI, BARE.upper(), f"{UKRI}/"])
def test_an_organisation_is_found_by_its_ror_identifier_in_any_form(
    client: TestClient, given: str
) -> None:
    found = client.get(f"/api/funders/ror/{given}")
    assert found.status_code == 200
    body = found.json()
    assert body["ror_id"] == UKRI
    assert body["snapshot_ref"] == ROR_DUMP
    assert body["links"]["ror"] == UKRI


def test_the_answer_says_what_the_dump_records_and_where_to_open_it(client: TestClient) -> None:
    body = client.get(f"/api/funders/ror/{BARE}").json()
    assert body["crossref_funder_ids"] == ["100014013"]
    assert body["links"]["crossref_funders"] == ["https://doi.org/10.13039/100014013"]
    assert {n["value"] for n in body["names"]} == {"UK Research and Innovation", "UKRI"}
    check_fixture("funder-ror-organisation.json", body, model=RorOrganisation)


@pytest.mark.parametrize("given", ["0zzzzzz99", "not-a-ror-id", "../etc/passwd"])
def test_an_identifier_the_dump_does_not_hold_is_not_found(client: TestClient, given: str) -> None:
    assert client.get(f"/api/funders/ror/{given}").status_code == 404


def test_a_server_with_no_built_dump_says_so(governance: Governance, tmp_path: Path) -> None:
    governance.conductor.sources = Sources()
    client = TestClient(build_app(governance, dist_dir(tmp_path)))
    found = client.get(f"/api/funders/ror/{BARE}")
    assert found.status_code == 503
    assert found.json()["type"].endswith("ror-unavailable")


def test_a_server_that_pins_only_other_registries_has_no_dump(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    configure_env(monkeypatch, tmp_path)
    monkeypatch.setenv("DD_SOURCES_CONFIG", str(pin_export(tmp_path / "re3data")))
    for governance in new_governance():
        client = TestClient(build_app(governance, dist_dir(tmp_path)))
        assert client.get(f"/api/funders/ror/{BARE}").status_code == 503
