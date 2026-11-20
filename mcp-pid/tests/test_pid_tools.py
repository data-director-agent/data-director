"""Each tool's three answers (found, not found, error), and that every found record is valid
against the tool's own output schema with its identifying field at the top level."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from jsonschema import Draft202012Validator
from pid_support import CROSSREF_DOI, DATACITE_DOI, NERC, ORCID_ID, built_registry, registries

from dd_mcp_pid.tools import Registry

ID_FIELD = {"datacite": "doi", "crossref": "doi", "orcid": "orcid", "ror": "id"}


@pytest.fixture
def by_name(tmp_path: Path) -> dict[str, Registry]:
    return {r.name: r for r in registries(built_registry(tmp_path))}


def records(registry: Registry, tool: str, arguments: dict[str, Any]) -> list[dict[str, Any]]:
    """The records a call found, checked against the tool's output schema."""
    result = registry.call(tool, arguments)
    assert not result.is_error, result.content
    assert result.structured_content is not None
    schema = next(t.output_schema for t in registry.tools if t.name == tool)
    assert schema is not None
    Draft202012Validator(schema).validate(result.structured_content)
    found: list[dict[str, Any]] = result.structured_content["records"]
    for record in found:
        assert isinstance(record[ID_FIELD[registry.name]], str)
    return found


def one(registry: Registry, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    [record] = records(registry, tool, arguments)
    return record


def test_every_tool_declares_input_and_output_schemas(by_name: dict[str, Registry]) -> None:
    for registry in by_name.values():
        for tool in registry.tools:
            Draft202012Validator.check_schema(tool.input_schema)
            assert tool.output_schema is not None
            Draft202012Validator.check_schema(tool.output_schema)


def test_a_doi_is_found_by_the_agency_that_registered_it(by_name: dict[str, Registry]) -> None:
    record = one(by_name["datacite"], "get_doi", {"doi": "https://doi.org/10.15497/RDA00157"})
    assert record["doi"] == DATACITE_DOI
    assert record["title"] == "Data Director Agentic AI Tool Blueprint"
    record = one(by_name["crossref"], "get_doi", {"doi": CROSSREF_DOI})
    assert record["agency"] == "Crossref"


def test_a_doi_the_agency_did_not_register_has_no_records(by_name: dict[str, Registry]) -> None:
    assert records(by_name["datacite"], "get_doi", {"doi": CROSSREF_DOI}) == []
    result = by_name["datacite"].call("get_doi", {"doi": CROSSREF_DOI})
    assert "another registration agency may" in result.content[0].text  # type: ignore[union-attr]
    assert records(by_name["orcid"], "get_orcid", {"orcid": "0000-0001-5109-3700"}) == []
    assert records(by_name["ror"], "get_organisation", {"id": "05krs5044"}) == []


@pytest.mark.parametrize(
    ("server", "tool", "arguments"),
    [
        ("datacite", "get_doi", {"doi": "not a doi"}),
        ("orcid", "get_orcid", {"orcid": "0000-0002-1825-0098"}),
        ("ror", "get_organisation", {"id": "nerc"}),
        ("ror", "search_organisations", {"name": "  "}),
        ("datacite", "get_doi", {}),
        ("datacite", "no_such_tool", {"doi": DATACITE_DOI}),
    ],
)
def test_an_input_of_the_wrong_kind_is_an_error(
    by_name: dict[str, Registry], server: str, tool: str, arguments: dict[str, Any]
) -> None:
    result = by_name[server].call(tool, arguments)
    assert result.is_error and result.structured_content is None


def test_a_failing_registry_is_an_error_not_a_miss() -> None:
    down = {r.name: r for r in registries(handler=lambda _r: httpx.Response(502))}
    result = down["crossref"].call("get_doi", {"doi": CROSSREF_DOI})
    assert result.is_error
    assert "Crossref: HTTP 502" in result.content[0].text  # type: ignore[union-attr]


def test_an_orcid_id_resolves_to_the_public_name(by_name: dict[str, Registry]) -> None:
    record = one(by_name["orcid"], "get_orcid", {"orcid": ORCID_ID})
    assert record["orcid"] == f"https://orcid.org/{ORCID_ID}"
    assert (record["given_names"], record["family_name"]) == ("Josiah", "Carberry")


def test_a_ror_id_is_read_from_the_dump_and_says_so(by_name: dict[str, Registry]) -> None:
    result = by_name["ror"].call("get_organisation", {"id": "02b5d8509"})
    record = one(by_name["ror"], "get_organisation", {"id": "02b5d8509"})
    assert record["id"] == NERC
    assert "from the ROR dump test" in result.content[0].text  # type: ignore[union-attr]


def test_ror_falls_back_to_the_api_when_the_dump_is_not_built(tmp_path: Path) -> None:
    ror = {r.name: r for r in registries(tmp_path / "missing.jsonl")}["ror"]
    result = ror.call("get_organisation", {"id": NERC})
    assert result.structured_content is not None
    assert result.structured_content["records"][0]["id"] == NERC
    assert "from ROR's API (the dump could not be read)" in result.content[0].text  # type: ignore[union-attr]


def test_a_name_search_lists_every_match_and_an_empty_list_for_none(
    by_name: dict[str, Registry],
) -> None:
    found = records(by_name["ror"], "search_organisations", {"name": "NERC"})
    assert [r["id"] for r in found] == [NERC]
    assert records(by_name["ror"], "search_organisations", {"name": "No Such Council"}) == []
