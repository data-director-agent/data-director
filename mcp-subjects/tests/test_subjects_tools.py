"""The tools' answers (found, not found, error), every record valid against its tool's output
schema, and a scheme found by any name a repository gives it."""

from __future__ import annotations

from typing import Any

import pytest
from jsonschema import Draft202012Validator
from mcp_types import Tool

from dd_mcp_subjects.tools import GET_TERM, LIST_TERMS, Tools, scheme_id
from dd_subjects import SCHEMES, scheme


def records(tool: Tool, arguments: dict[str, Any]) -> list[dict[str, Any]]:
    result = Tools().call(tool.name, arguments)
    assert not result.is_error, result.content
    assert result.structured_content is not None and tool.output_schema is not None
    Draft202012Validator(tool.output_schema).validate(result.structured_content)
    found: list[dict[str, Any]] = result.structured_content["records"]
    return found


@pytest.mark.parametrize("tool", [LIST_TERMS, GET_TERM])
def test_each_tool_declares_input_and_output_schemas(tool: Tool) -> None:
    Draft202012Validator.check_schema(tool.input_schema)
    assert tool.output_schema is not None
    Draft202012Validator.check_schema(tool.output_schema)


@pytest.mark.parametrize(
    "named",
    ["anzsrc-for", "ANZSRC Fields of Research", "  anzsrc   fields of research ", "ANZSRC FoR"],
)
def test_a_scheme_is_found_by_its_id_or_a_name_a_repository_gives_it(named: str) -> None:
    assert scheme_id(named) == "anzsrc-for"


@pytest.mark.parametrize("scheme_name", SCHEMES)
def test_a_scheme_lists_every_field_once(scheme_name: str) -> None:
    [record] = records(LIST_TERMS, {"scheme": scheme_name})
    assert record["id"] == scheme_name
    codes = [t["code"] for t in record["terms"]]
    assert codes == [t.code for t in scheme(scheme_name).terms]
    assert record["licence"] and record["attribution"] and record["version"]


@pytest.mark.parametrize("scheme_name", SCHEMES)
def test_every_field_is_found_by_its_code_with_its_own_identifier(scheme_name: str) -> None:
    seen = set()
    for term in scheme(scheme_name).terms:
        [record] = records(GET_TERM, {"scheme": scheme_name, "code": term.code})
        assert (record["code"], record["label"], record["parent"]) == (
            term.code,
            term.label,
            term.parent,
        )
        seen.add(record["id"])
    assert len(seen) == len(scheme(scheme_name).terms)
    assert scheme_name not in seen  # a field never takes its scheme's identifier


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        (LIST_TERMS, {"scheme": "Dewey Decimal Classification"}),
        (GET_TERM, {"scheme": "anzsrc-for", "code": "9999"}),
        (GET_TERM, {"scheme": "no-such-scheme", "code": "4106"}),
    ],
)
def test_an_unknown_scheme_or_code_has_no_records(tool: Tool, arguments: dict[str, Any]) -> None:
    assert records(tool, arguments) == []


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("list_terms", {}),
        ("list_terms", {"scheme": "  "}),
        ("get_term", {"scheme": "anzsrc-for"}),
        ("get_term", {"scheme": "anzsrc-for", "code": 4106}),
        ("search_terms", {"scheme": "anzsrc-for"}),
    ],
)
def test_input_that_names_nothing_is_an_error(tool: str, arguments: dict[str, Any]) -> None:
    result = Tools().call(tool, arguments)
    assert result.is_error and result.structured_content is None
