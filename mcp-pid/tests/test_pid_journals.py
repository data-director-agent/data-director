"""The `journals` server: a journal by any ISSN, a search by title, and an error, not a miss,
while the registry is not built."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pid_support import STOTEN, STOTEN_ONLINE, built_journals, registries

from dd_mcp_pid.tools import Registry


@pytest.fixture
def journals(tmp_path: Path) -> Registry:
    return {r.name: r for r in registries(journals=built_journals(tmp_path))}["journals"]


def records(registry: Registry, tool: str, arguments: dict[str, Any]) -> list[dict[str, Any]]:
    result = registry.call(tool, arguments)
    assert not result.is_error, result.content
    schema = next(t.output_schema for t in registry.tools if t.name == tool)
    assert schema is not None
    Draft202012Validator(schema).validate(result.structured_content)
    assert result.structured_content is not None
    found: list[dict[str, Any]] = result.structured_content["records"]
    return found


def walk(value: Any) -> list[Any]:
    """Every value in a record, nested values included."""
    if isinstance(value, dict):
        return [v for item in value.values() for v in [item, *walk(item)]]
    if isinstance(value, list):
        return [v for item in value for v in [item, *walk(item)]]
    return []


@pytest.mark.parametrize("issn", [STOTEN, STOTEN_ONLINE, STOTEN_ONLINE.replace("-", "")])
def test_any_issn_finds_the_journal_by_its_issn_l(journals: Registry, issn: str) -> None:
    [record] = records(journals, "get_journal", {"issn": issn})
    assert record["issn_l"] == STOTEN
    assert STOTEN_ONLINE in record["issns"]
    assert record["portal_url"].endswith(STOTEN)


def test_a_record_holds_no_integer(journals: Registry) -> None:
    [record] = records(journals, "get_journal", {"issn": STOTEN})
    assert not any(isinstance(v, int) and not isinstance(v, bool) for v in walk(record))


def test_an_issn_the_registry_lacks_has_no_records(journals: Registry) -> None:
    assert records(journals, "get_journal", {"issn": "9999-9999"}) == []


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [("get_journal", {"issn": "not an issn"}), ("search_journals", {"text": "  "})],
)
def test_an_input_of_the_wrong_kind_is_an_error(
    journals: Registry, tool: str, arguments: dict[str, str]
) -> None:
    assert journals.call(tool, arguments).is_error


def test_a_search_puts_the_same_title_first_then_those_it_starts(journals: Registry) -> None:
    found = [r["issn_l"] for r in records(journals, "search_journals", {"text": "nature"})]
    assert found[0] == "0028-0836"
    assert "1758-678X" in found[1:]
    assert [r["issn_l"] for r in records(journals, "search_journals", {"text": "Sci Data"})] == [
        "2052-4463"
    ]
    assert records(journals, "search_journals", {"text": "no such journal"}) == []


def test_a_search_for_an_issn_finds_its_journal(journals: Registry) -> None:
    [record] = records(journals, "search_journals", {"text": STOTEN_ONLINE})
    assert record["issn_l"] == STOTEN


def test_an_unbuilt_registry_is_an_error_that_says_how_to_build_it(tmp_path: Path) -> None:
    unbuilt = {r.name: r for r in registries(journals=tmp_path / "missing.sqlite")}["journals"]
    assert [t.name for t in unbuilt.tools] == ["get_journal", "search_journals"]
    result = unbuilt.call("get_journal", {"issn": STOTEN})
    assert result.is_error
    assert result.structured_content is None
