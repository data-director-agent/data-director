"""The tools' answers (found, not found, error), every found record valid against the tool's own
output schema, the key settings, and the server's health check and routing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from jsonschema import Draft202012Validator
from opf_records import KEY, STOTEN_PAGE, opf, opf_handler
from starlette.testclient import TestClient

from dd_mcp_opf.app import create_app
from dd_mcp_opf.cli import SettingsError, api_key, check, hosts
from dd_mcp_opf.tools import GET_JOURNAL_BY_ISSN, GET_RECORD, SEARCH_RECORDS, Tools

TOOLS = {t.name: t for t in (SEARCH_RECORDS, GET_RECORD, GET_JOURNAL_BY_ISSN)}


def _valid(tool: str, result: Any) -> list[dict[str, Any]]:
    assert not result.is_error
    schema = TOOLS[tool].output_schema
    assert schema is not None
    Draft202012Validator(schema).validate(result.structured_content)
    records: list[dict[str, Any]] = result.structured_content["records"]
    return records


def test_a_search_answers_valid_records() -> None:
    tools = Tools(opf())
    result = tools.call("search_records", {"item_type": "funder", "text": "NERC"})
    [record] = _valid("search_records", result)
    assert record["acronyms"] == ["NERC"]


def test_a_record_is_read_by_identifier_and_a_journal_by_issn() -> None:
    tools = Tools(opf())
    [publisher] = _valid(
        "get_record", tools.call("get_record", {"item_type": "publisher", "identifier": "30"})
    )
    assert publisher["names"] == ["Elsevier"]
    [journal] = _valid(
        "get_journal_by_issn", tools.call("get_journal_by_issn", {"issn": "00489697"})
    )
    assert journal["page"] == STOTEN_PAGE
    assert [p["id"] for p in journal["publishers"]] == ["30"]


def test_nothing_found_is_an_empty_list_not_an_error() -> None:
    tools = Tools(opf())
    assert (
        _valid("get_record", tools.call("get_record", {"item_type": "funder", "identifier": "9"}))
        == []
    )
    assert (
        _valid("get_journal_by_issn", tools.call("get_journal_by_issn", {"issn": "1234-5679"}))
        == []
    )


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("search_records", {"item_type": "person", "text": "NERC"}),
        ("search_records", {"item_type": "funder", "text": "x"}),
        ("get_record", {"item_type": "funder", "identifier": " "}),
        ("get_journal_by_issn", {"issn": "nope"}),
        ("no_such_tool", {}),
    ],
)
def test_unusable_input_is_an_error(tool: str, arguments: dict[str, Any]) -> None:
    result = Tools(opf()).call(tool, arguments)
    assert result.is_error and result.structured_content is None


def test_an_unreachable_registry_is_an_error_that_names_no_key() -> None:
    result = Tools(opf(opf_handler(status=503))).call(
        "search_records", {"item_type": "funder", "text": "NERC"}
    )
    assert result.is_error and "HTTP 503" in result.content[0].text  # type: ignore[union-attr]
    assert KEY not in result.content[0].text  # type: ignore[union-attr]


def test_without_a_key_each_call_says_one_is_needed() -> None:
    result = Tools().call("get_journal_by_issn", {"issn": "0048-9697"})
    assert result.is_error and "OPEN_POLICY_FINDER_API_KEY" in result.content[0].text  # type: ignore[union-attr]


def test_the_key_comes_from_the_environment_or_a_file(tmp_path: Path) -> None:
    assert api_key({}) is None
    assert api_key({"OPEN_POLICY_FINDER_API_KEY": " k "}) == "k"
    (tmp_path / "key").write_text("secret\n", encoding="utf-8")
    assert api_key({"OPEN_POLICY_FINDER_API_KEY_FILE": str(tmp_path / "key")}) == "secret"
    relative = {"OPEN_POLICY_FINDER_API_KEY_FILE": "key", "CREDENTIALS_DIRECTORY": str(tmp_path)}
    assert api_key(relative) == "secret"
    (tmp_path / "two").write_text("a b", encoding="utf-8")
    for bad in (
        {"OPEN_POLICY_FINDER_API_KEY_FILE": "key"},
        {"OPEN_POLICY_FINDER_API_KEY_FILE": str(tmp_path / "missing")},
        {"OPEN_POLICY_FINDER_API_KEY_FILE": str(tmp_path / "two")},
        {"OPEN_POLICY_FINDER_API_KEY": "k", "OPEN_POLICY_FINDER_API_KEY_FILE": "key"},
    ):
        with pytest.raises(SettingsError):
            api_key(bad)


def test_hosts_are_loopback_and_any_the_deployment_adds() -> None:
    assert hosts({"DD_OPF_HOSTS": "mcp-opf, other"})[-2:] == ["mcp-opf", "other"]


def test_the_route_check_reports_each_known_record(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert check(opf(), tmp_path) == 0
    assert "fetch publication '0048-9697': 1 record(s)" in capsys.readouterr().out
    assert len(list(tmp_path.glob("opf-check-*.json"))) == 5
    json.loads(next(tmp_path.glob("opf-check-5-*.json")).read_text(encoding="utf-8"))
    assert check(opf(lambda _: httpx.Response(500))) == 1


def test_the_server_answers_its_health_check_and_nothing_else() -> None:
    with TestClient(create_app(Tools(opf()))) as client:
        health = client.get("/healthz")
        assert health.status_code == 200 and health.json()["server"] == "opf"
        assert client.get("/elsewhere").status_code == 404


def test_the_server_lists_its_tools_over_streamable_http() -> None:
    message = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    headers = {"Accept": "application/json, text/event-stream", "Host": "127.0.0.1"}
    with TestClient(create_app(Tools(opf())), base_url="http://127.0.0.1") as client:
        answer = client.post("/opf/mcp", json=message, headers=headers)
        assert answer.status_code == 200, answer.text
        assert {t["name"] for t in answer.json()["result"]["tools"]} == set(TOOLS)
        refused = client.post("/opf/mcp", json=message, headers={**headers, "Host": "evil.test"})
        assert refused.status_code >= 400
