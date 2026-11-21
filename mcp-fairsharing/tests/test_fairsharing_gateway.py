"""The server as the Data Director's tool gateway reaches it: over HTTP, listed, pinned, and with
each found record recorded and hashed by its `id`."""

from __future__ import annotations

import asyncio
import socket
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime

import httpx
import pytest
import uvicorn
from fs_support import RECORD_ID, registry

from dd_harness.gateway.config import ToolServer, tools_digest
from dd_harness.gateway.core import Gateway, recorded
from dd_harness.gateway.upstream import Upstream
from dd_mcp_fairsharing.app import create_app
from dd_sdk.evidence import DOCUMENT_CANONICALISATION, content_hash


def listed_servers(base_url: str) -> list[ToolServer]:
    reg = registry()
    return [
        ToolServer(
            name=reg.name,
            url=f"{base_url}/{reg.name}/mcp",
            id_field="id",
            canonicalisation=DOCUMENT_CANONICALISATION,
            tools_sha256=tools_digest(
                t.model_dump(mode="json", by_alias=True, exclude_none=True) for t in reg.tools
            ),
        )
    ]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def base_url() -> Iterator[str]:
    port = _free_port()
    config = uvicorn.Config(
        create_app([registry()]), host="127.0.0.1", port=port, log_level="warning"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "the server did not start"
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture(scope="module")
def gateway(base_url: str) -> Gateway:
    connected = Gateway(listed_servers(base_url), Upstream())
    connected.connect()
    return connected


def test_the_gateway_lists_and_pins_the_server_over_http(gateway: Gateway) -> None:
    assert gateway.unavailable == {}
    assert set(gateway.available) == {"fairsharing"}


def test_the_server_refuses_a_host_it_was_not_told_of(base_url: str) -> None:
    resp = httpx.post(
        f"{base_url}/fairsharing/mcp",
        headers={"Host": "attacker.example", "Content-Type": "application/json"},
        content=b"{}",
    )
    assert resp.status_code in {400, 421}


def test_a_found_record_is_recorded_and_hashed_by_the_gateway(gateway: Gateway) -> None:
    pinned = gateway.available["fairsharing"]
    result = asyncio.run(gateway.upstream.call_tool(pinned.server, "get_record", {"id": RECORD_ID}))
    assert not result.is_error
    [retrieval] = recorded(pinned, "get_record", result.structured_content, datetime.now(UTC))
    assert retrieval.source_id == f"tool:fairsharing/{RECORD_ID}"
    assert result.structured_content is not None
    [record] = result.structured_content["records"]
    assert retrieval.content_hash == content_hash(record, pinned.server.canonicalisation)


def test_a_miss_records_nothing(gateway: Gateway) -> None:
    pinned = gateway.available["fairsharing"]
    result = asyncio.run(
        gateway.upstream.call_tool(pinned.server, "get_record", {"id": "FAIRsharing.zzzzzz"})
    )
    assert not result.is_error and result.structured_content == {"records": []}
    assert recorded(pinned, "get_record", result.structured_content, datetime.now(UTC)) == []
