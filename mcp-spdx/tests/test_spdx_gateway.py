"""The server as the Data Director's tool gateway reaches it: over HTTP, listed, pinned, and with
each found licence recorded by `licenseId` and hashed under `dd-spdx-licence-v1`."""

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

from dd_harness.gateway.config import ToolServer, tools_digest
from dd_harness.gateway.core import Gateway, recorded
from dd_harness.gateway.upstream import Upstream
from dd_mcp_spdx.app import create_app
from dd_mcp_spdx.licences import release
from dd_mcp_spdx.tools import Tools
from dd_sdk.evidence import SPDX_LICENCE_CANONICALISATION, content_hash


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def base_url() -> Iterator[str]:
    port = _free_port()
    config = uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning")
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
    listed = Tools().listed
    server = ToolServer(
        name="spdx",
        url=f"{base_url}/spdx/mcp",
        id_field="licenseId",
        canonicalisation=SPDX_LICENCE_CANONICALISATION,
        tools_sha256=tools_digest(
            t.model_dump(mode="json", by_alias=True, exclude_none=True) for t in listed
        ),
        snapshot_ref=release().snapshot_ref,
    )
    connected = Gateway([server], Upstream())
    connected.connect()
    return connected


def test_the_gateway_lists_and_pins_the_server_over_http(gateway: Gateway) -> None:
    assert gateway.unavailable == {}
    assert set(gateway.available) == {"spdx"}


def test_health_names_the_release_served(base_url: str) -> None:
    body = httpx.get(f"{base_url}/healthz").json()
    assert body["status"] == "ok"
    assert body["snapshot_ref"] == release().snapshot_ref


def test_the_server_refuses_a_host_it_was_not_told_of(base_url: str) -> None:
    resp = httpx.post(
        f"{base_url}/spdx/mcp",
        headers={"Host": "attacker.example", "Content-Type": "application/json"},
        content=b"{}",
    )
    assert resp.status_code in {400, 421}


def test_a_found_licence_is_recorded_and_hashed_by_the_gateway(gateway: Gateway) -> None:
    pinned = gateway.available["spdx"]
    result = asyncio.run(
        gateway.upstream.call_tool(pinned.server, "get_licence", {"id": "cc-by-4.0"})
    )
    assert not result.is_error and result.structured_content is not None
    [retrieval] = recorded(pinned, "get_licence", result.structured_content, datetime.now(UTC))
    assert retrieval.source_id == "tool:spdx/CC-BY-4.0"
    [record] = result.structured_content["records"]
    assert retrieval.content_hash == content_hash(record, SPDX_LICENCE_CANONICALISATION)


def test_a_miss_records_nothing(gateway: Gateway) -> None:
    pinned = gateway.available["spdx"]
    result = asyncio.run(
        gateway.upstream.call_tool(pinned.server, "get_licence", {"id": "Not-A-Licence-1.0"})
    )
    assert not result.is_error and result.structured_content == {"records": []}
    assert recorded(pinned, "get_licence", result.structured_content, datetime.now(UTC)) == []


def test_any_other_path_is_not_found(base_url: str) -> None:
    assert httpx.get(f"{base_url}/fairsharing/mcp").status_code == 404
