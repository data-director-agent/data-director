"""The tool's answers (found, not found, error), every found record valid against the tool's own
output schema, and the packaged release checked against its manifest."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from importlib import resources
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from dd_mcp_spdx.licences import PinError, index, release
from dd_mcp_spdx.tools import GET_LICENCE, Tools


def records(tools: Tools, arguments: dict[str, Any]) -> list[dict[str, Any]]:
    result = tools.call("get_licence", arguments)
    assert not result.is_error, result.content
    assert result.structured_content is not None
    assert GET_LICENCE.output_schema is not None
    Draft202012Validator(GET_LICENCE.output_schema).validate(result.structured_content)
    found: list[dict[str, Any]] = result.structured_content["records"]
    return found


def test_the_tool_declares_input_and_output_schemas() -> None:
    Draft202012Validator.check_schema(GET_LICENCE.input_schema)
    assert GET_LICENCE.output_schema is not None
    Draft202012Validator.check_schema(GET_LICENCE.output_schema)


@pytest.mark.parametrize("given", ["CC-BY-4.0", "cc-by-4.0", "  CC-BY-4.0 "])
def test_a_licence_is_found_by_its_identifier_in_any_case(given: str) -> None:
    [record] = records(Tools(), {"id": given})
    assert record["licenseId"] == "CC-BY-4.0"
    assert record["reference"] == "https://spdx.org/licenses/CC-BY-4.0.html"
    assert record["isDeprecatedLicenseId"] is False
    assert record["seeAlso"]


def test_a_deprecated_identifier_is_found_and_marked() -> None:
    [record] = records(Tools(), {"id": "GPL-2.0"})
    assert record["isDeprecatedLicenseId"] is True


def test_an_unknown_identifier_has_no_records() -> None:
    assert records(Tools(), {"id": "Not-A-Licence-1.0"}) == []


@pytest.mark.parametrize("arguments", [{}, {"id": ""}, {"id": 4}])
def test_input_that_is_not_an_identifier_is_an_error(arguments: dict[str, Any]) -> None:
    result = Tools().call("get_licence", arguments)
    assert result.is_error and result.structured_content is None


def test_an_unknown_tool_is_an_error() -> None:
    assert Tools().call("search_licences", {"text": "MIT"}).is_error


def _integers(value: object) -> bool:
    if isinstance(value, dict):
        return any(_integers(v) for v in value.values())
    if isinstance(value, list):
        return any(_integers(v) for v in value)
    return isinstance(value, int) and not isinstance(value, bool)


def test_every_packaged_record_is_valid_and_holds_no_integers() -> None:
    pinned = release()
    raw = resources.files("dd_mcp_spdx").joinpath("data", pinned.file).read_bytes()
    every = index(pinned, raw)
    assert len(every) == pinned.count
    validate = Draft202012Validator(GET_LICENCE.output_schema or {}).validate
    for record in every.values():
        validate({"records": [record]})
        assert not _integers(record)


def test_a_records_file_that_does_not_match_its_manifest_is_refused() -> None:
    pinned = release()
    line = json.dumps({"licenseId": "X", "name": "X"}) + "\n"
    with pytest.raises(PinError):
        index(pinned, line.encode())
    raw = line.encode()
    short = replace(pinned, sha256=hashlib.sha256(raw).hexdigest())
    with pytest.raises(PinError):
        index(short, raw)


def test_the_release_names_the_snapshot_it_serves() -> None:
    pinned = release()
    assert pinned.snapshot_ref == f"spdx:{pinned.version}"
    assert pinned.file == f"licenses-{pinned.version}.jsonl"
