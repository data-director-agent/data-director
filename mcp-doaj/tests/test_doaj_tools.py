"""The tools' answers (found, not found, error), every found record valid against the tool's own
output schema, and the server's health check and routing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from starlette.testclient import TestClient

from dd_mcp_doaj.app import create_app
from dd_mcp_doaj.journals import DoajUnavailableError, journal_record
from dd_mcp_doaj.tools import GET_JOURNAL, SEARCH_JOURNALS, Tools

DATA = Path(__file__).with_name("data")


def _record(name: str) -> dict[str, Any]:
    body = json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))
    record = journal_record(body["results"][0])
    assert record is not None
    return record


class FakeDoaj:
    def __init__(self, *records: dict[str, Any], down: bool = False) -> None:
        self.records = list(records)
        self.down = down

    def by_issn(self, issn: str) -> dict[str, Any] | None:
        if self.down:
            raise DoajUnavailableError("DOAJ: HTTP 503")
        return next((r for r in self.records if issn in (r["eissn"], r["pissn"])), None)

    def search(self, title: str, rows: int = 5) -> list[dict[str, Any]]:
        if self.down:
            raise DoajUnavailableError("DOAJ: HTTP 503")
        return [r for r in self.records if title.casefold() in r["title"].casefold()][:rows]


def records(tools: Tools, tool: str, arguments: dict[str, Any]) -> list[dict[str, Any]]:
    result = tools.call(tool, arguments)
    assert not result.is_error, result.content
    assert result.structured_content is not None
    schema = next(t.output_schema for t in tools.listed if t.name == tool)
    assert schema is not None
    Draft202012Validator(schema).validate(result.structured_content)
    found: list[dict[str, Any]] = result.structured_content["records"]
    return found


@pytest.mark.parametrize("tool", [GET_JOURNAL, SEARCH_JOURNALS])
def test_each_tool_declares_input_and_output_schemas(tool: Any) -> None:
    Draft202012Validator.check_schema(tool.input_schema)
    assert tool.output_schema is not None
    Draft202012Validator.check_schema(tool.output_schema)


def test_a_journal_is_found_by_its_issn() -> None:
    tools = Tools(FakeDoaj(_record("ncomms"), _record("plos")))
    [record] = records(tools, "get_journal", {"issn": "1932-6203"})
    assert record["eissn"] == "1932-6203"


def test_an_issn_doaj_does_not_list_has_no_records() -> None:
    assert records(Tools(FakeDoaj()), "get_journal", {"issn": "0000-0000"}) == []


def test_journals_are_searched_by_title() -> None:
    tools = Tools(FakeDoaj(_record("ncomms"), _record("plos")))
    found = records(tools, "search_journals", {"title": "nature"})
    assert [r["eissn"] for r in found] == ["2041-1723"]


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("get_journal", {}),
        ("get_journal", {"issn": "abc"}),
        ("get_journal", {"issn": 1932}),
        ("search_journals", {"title": " "}),
        ("search_journals", {}),
        ("search_licences", {"title": "x"}),
    ],
)
def test_input_that_cannot_be_used_is_an_error(tool: str, arguments: dict[str, Any]) -> None:
    result = Tools(FakeDoaj()).call(tool, arguments)
    assert result.is_error and result.structured_content is None


def test_doaj_not_answering_is_an_error_not_an_empty_result() -> None:
    tools = Tools(FakeDoaj(down=True))
    calls = (("get_journal", {"issn": "1932-6203"}), ("search_journals", {"title": "PLOS"}))
    for tool, arguments in calls:
        result = tools.call(tool, arguments)
        assert result.is_error and result.structured_content is None


def test_the_server_answers_its_health_check_and_nothing_else() -> None:
    with TestClient(create_app(Tools(FakeDoaj()))) as client:
        health = client.get("/healthz")
        assert health.status_code == 200 and health.json()["server"] == "doaj"
        assert client.get("/elsewhere").status_code == 404


def test_the_server_lists_its_tools_over_streamable_http() -> None:
    message = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    headers = {"Accept": "application/json, text/event-stream", "Host": "127.0.0.1"}
    with TestClient(create_app(Tools(FakeDoaj())), base_url="http://127.0.0.1") as client:
        answer = client.post("/doaj/mcp", json=message, headers=headers)
        assert answer.status_code == 200, answer.text
        names = {tool["name"] for tool in answer.json()["result"]["tools"]}
        assert names == {GET_JOURNAL.name, SEARCH_JOURNALS.name}
        refused = client.post("/doaj/mcp", json=message, headers={**headers, "Host": "evil.test"})
        assert refused.status_code >= 400
