"""Each tool's answers (found, not found, error), and that every found record is valid against
the tool's own output schema with its identifier at the top level."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fs_support import RECORD_ID, client, registry, seen
from jsonschema import Draft202012Validator

from dd_mcp_fairsharing.client import record_id
from dd_mcp_fairsharing.tools import Tools


def records(reg: Tools, tool: str, arguments: dict[str, Any]) -> list[dict[str, Any]]:
    result = reg.call(tool, arguments)
    assert not result.is_error, result.content
    assert result.structured_content is not None
    schema = next(t.output_schema for t in reg.listed if t.name == tool)
    assert schema is not None
    Draft202012Validator(schema).validate(result.structured_content)
    found: list[dict[str, Any]] = result.structured_content["records"]
    return found


def test_every_tool_declares_input_and_output_schemas() -> None:
    for tool in registry().listed:
        Draft202012Validator.check_schema(tool.input_schema)
        assert tool.output_schema is not None
        Draft202012Validator.check_schema(tool.output_schema)


@pytest.mark.parametrize(
    "value",
    [
        RECORD_ID,
        "10.25504/FAIRsharing.abc123",
        "https://fairsharing.org/FAIRsharing.abc123/",
        "1234",
    ],
)
def test_a_record_is_found_by_any_form_of_its_identifier(value: str) -> None:
    [record] = records(registry(), "get_record", {"id": value})
    assert record["id"] == RECORD_ID
    assert record["doi"] == "10.25504/FAIRsharing.abc123"
    assert record["record_type"] == "model_and_format"
    assert record["subjects"] == ["Metadata"]
    assert record["url"] == "https://fairsharing.org/FAIRsharing.abc123"
    assert "CC BY-SA" in record["licence"]


def test_a_record_needs_no_account() -> None:
    assert records(registry(account=False), "get_record", {"id": RECORD_ID})


def test_an_unknown_identifier_has_no_records() -> None:
    assert records(registry(), "get_record", {"id": "FAIRsharing.zzzzzz"}) == []
    gone = Tools(client(lambda _r: httpx.Response(404)))
    assert records(gone, "get_record", {"id": RECORD_ID}) == []


def test_a_search_lists_records_and_signs_in_once() -> None:
    seen.clear()
    reg = registry()
    for _ in range(2):
        [record] = records(
            reg, "search_records", {"query": "metadata", "record_type": "model_and_format"}
        )
        assert record["id"] == RECORD_ID and record["domains"] == ["Data management"]
    assert [r.url.path for r in seen].count("/users/sign_in") == 1
    assert seen[-1].url.params["record_type"] == "model_and_format"


def test_search_without_an_account_is_an_error_that_points_to_get_record() -> None:
    result = registry(account=False).call("search_records", {"query": "metadata"})
    assert result.is_error
    assert "get_record" in result.content[0].text  # type: ignore[union-attr]


def test_the_credentials_never_appear_in_an_answer() -> None:
    result = registry().call("search_records", {"query": "metadata"})
    assert "not-a-real-password" not in result.model_dump_json()


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("get_record", {"id": "not an id"}),
        ("get_record", {}),
        ("search_records", {"query": "  "}),
        ("search_records", {"query": "x", "limit": 0}),
        ("search_records", {"query": "x", "limit": "ten"}),
        ("no_such_tool", {}),
    ],
)
def test_an_input_of_the_wrong_kind_is_an_error(tool: str, arguments: dict[str, Any]) -> None:
    assert registry().call(tool, arguments).is_error


def test_a_failing_service_is_an_error_not_a_miss() -> None:
    down = Tools(client(lambda _r: httpx.Response(503)))
    assert down.call("get_record", {"id": RECORD_ID}).is_error


def test_record_id_normalises() -> None:
    assert record_id("fairsharing.ABC123") == "FAIRsharing.ABC123"
    assert record_id("10.1234/x") is None
