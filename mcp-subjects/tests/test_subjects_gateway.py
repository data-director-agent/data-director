"""The server as the Data Director's tool gateway reaches it: listed, pinned, and with each
record recorded by `id` and hashed whole; and the HTTP application's health and host checks."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from starlette.testclient import TestClient

from dd_harness.gateway.config import ToolServer, tools_digest
from dd_harness.gateway.core import Gateway, recorded
from dd_harness.gateway.upstream import Upstream
from dd_mcp_subjects.app import create_app
from dd_mcp_subjects.server import server
from dd_mcp_subjects.tools import Tools
from dd_sdk.evidence import DOCUMENT_CANONICALISATION, content_hash


@pytest.fixture(scope="module")
def gateway() -> Gateway:
    listed = Tools().listed
    config = ToolServer(
        name="subjects",
        url="http://127.0.0.1:8314/subjects/mcp",
        id_field="id",
        canonicalisation=DOCUMENT_CANONICALISATION,
        tools_sha256=tools_digest(
            t.model_dump(mode="json", by_alias=True, exclude_none=True) for t in listed
        ),
    )
    connected = Gateway([config], Upstream(connect=lambda _config: server(Tools())))
    connected.connect()
    return connected


def test_the_gateway_lists_and_pins_the_server(gateway: Gateway) -> None:
    assert gateway.unavailable == {}
    assert set(gateway.available) == {"subjects"}


@pytest.mark.parametrize(
    ("tool", "arguments", "source_id"),
    [
        ("get_term", {"scheme": "ANZSRC Fields of Research", "code": "4106"}, "anzsrc-for:4106"),
        ("list_terms", {"scheme": "oecd-fos"}, "oecd-fos"),
    ],
)
def test_a_found_record_is_recorded_by_its_id_and_hashed_whole(
    gateway: Gateway, tool: str, arguments: dict[str, str], source_id: str
) -> None:
    pinned = gateway.available["subjects"]
    result = asyncio.run(gateway.upstream.call_tool(pinned.server, tool, arguments))
    assert not result.is_error and result.structured_content is not None
    [retrieval] = recorded(pinned, tool, result.structured_content, datetime.now(UTC))
    assert retrieval.source_id == f"tool:subjects/{source_id}"
    [record] = result.structured_content["records"]
    assert retrieval.content_hash == content_hash(record, DOCUMENT_CANONICALISATION)


def test_a_miss_records_nothing(gateway: Gateway) -> None:
    pinned = gateway.available["subjects"]
    arguments = {"scheme": "anzsrc-for", "code": "9999"}
    result = asyncio.run(gateway.upstream.call_tool(pinned.server, "get_term", arguments))
    assert not result.is_error and result.structured_content == {"records": []}
    assert recorded(pinned, "get_term", result.structured_content, datetime.now(UTC)) == []


def test_health_names_each_scheme_served() -> None:
    with TestClient(create_app()) as client:
        body = client.get("/healthz").json()
    assert body["status"] == "ok"
    assert set(body["schemes"]) == {"anzsrc-for", "oecd-fos"}


def test_the_server_refuses_a_host_it_was_not_told_of() -> None:
    with TestClient(create_app(), base_url="http://attacker.example") as client:
        resp = client.post(
            "/subjects/mcp", headers={"Content-Type": "application/json"}, content=b"{}"
        )
    assert resp.status_code in {400, 421}


def test_any_other_path_is_not_found() -> None:
    with TestClient(create_app()) as client:
        assert client.get("/spdx/mcp").status_code == 404
