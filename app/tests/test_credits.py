"""The credit each external source asks for (`app/config/credits.yaml`, `dd_app.credits`).

The file is the one place the app's "Sources and licences" page and its evidence panel read the
credit from, so these tests hold it to the register of external sources in
docs/specs/dependencies.md and to the licence files kept beside each copy of a source's data.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from starlette.testclient import TestClient
from support import configure_env, dist_dir, new_governance

from dd_app import credits
from dd_app.app import build_app
from dd_app.governance import Governance


@pytest.fixture(scope="module")
def found() -> list[credits.Credit]:
    return credits.load()


def test_a_source_that_requires_credit_says_how_and_where_its_licence_is(
    found: list[credits.Credit],
) -> None:
    for credit in found:
        if credit.credit_required:
            assert credit.attribution.strip(), credit.id
            assert credit.licence_url.startswith("https://"), credit.id


def test_every_entry_links_over_https(found: list[credits.Credit]) -> None:
    for credit in found:
        links = [credit.url, credit.licence_url, credit.terms_url, credit.badge_url]
        assert all(link is None or link.startswith("https://") for link in links), credit.id


def test_no_two_sources_claim_the_same_prefix(found: list[credits.Credit]) -> None:
    claimed: dict[tuple[str, str], str] = {}
    for credit in found:
        for field in ("source_id_prefixes", "snapshot_ref_prefixes"):
            for prefix in getattr(credit.match, field):
                assert (field, prefix) not in claimed, (prefix, credit.id, claimed[field, prefix])
                claimed[field, prefix] = credit.id


def test_a_duplicated_source_id_is_a_configuration_error(tmp_path: Path) -> None:
    entry = "".join(
        f"    {line}\n" if i else f"  - {line}\n"
        for i, line in enumerate(
            [
                "id: a",
                "name: A",
                "url: https://a.example",
                "kind: data",
                "licence: CC0-1.0",
                "licence_url: https://a.example/licence",
                "attribution: A",
                "credit_required: false",
                "non_commercial: false",
                "use: pinned",
            ]
        )
    )
    path = tmp_path / "credits.yaml"
    path.write_text("sources:\n" + entry + entry, encoding="utf-8")
    with pytest.raises(ValueError, match="used twice"):
        credits.load(path)


@pytest.fixture
def governance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Governance]:
    configure_env(monkeypatch, tmp_path)
    yield from new_governance()


def test_the_sources_route_is_open_and_serves_every_entry(
    governance: Governance, tmp_path: Path, found: list[credits.Credit]
) -> None:
    client = TestClient(build_app(governance, dist_dir(tmp_path)))
    response = client.get("/api/sources")
    assert response.status_code == 200
    body = response.json()
    assert [entry["id"] for entry in body["sources"]] == [credit.id for credit in found]
    fairsharing = next(entry for entry in body["sources"] if entry["id"] == "fairsharing")
    assert fairsharing["badge_url"] and fairsharing["credit_required"] is True


def test_the_sources_page_serves_the_built_shell(governance: Governance, tmp_path: Path) -> None:
    response = TestClient(build_app(governance, dist_dir(tmp_path))).get("/sources")
    assert response.status_code == 200
    assert "<title>shell</title>" in response.text
