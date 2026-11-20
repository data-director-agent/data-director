"""The server as the Data Director's tool gateway reaches it: over HTTP at its URL, listed,
pinned, and with each found record recorded and hashed. That the committed tool configurations
pin these tools is checked at the repository's level (scripts/tests/test_pid_resolver_switch.py).

This is the gateway's URL transport in use (the gateway's own tests serve in process), so a
change in either the server or the MCP SDK that breaks the wire fails here.
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
import uvicorn
from pid_support import CROSSREF_DOI, DATACITE_DOI, NERC, ORCID_ID, built_registry, registries

from dd_harness.gateway.config import ToolServer, tools_digest
from dd_harness.gateway.core import Gateway, recorded
from dd_harness.gateway.upstream import Upstream
from dd_mcp_pid.app import create_app
from dd_sdk.evidence import DOCUMENT_CANONICALISATION, content_hash

ID_FIELD = {"datacite": "doi", "crossref": "doi", "orcid": "orcid", "ror": "id"}


def listed_servers(base_url: str) -> list[ToolServer]:
    """Each registry as a deployment lists it, pinned to the tools it serves."""
    return [
        ToolServer(
            name=r.name,
            url=f"{base_url}/{r.name}/mcp",
            id_field=ID_FIELD[r.name],
            canonicalisation=DOCUMENT_CANONICALISATION,
            tools_sha256=tools_digest(
                t.model_dump(mode="json", by_alias=True, exclude_none=True) for t in r.tools
            ),
        )
        for r in registries()
    ]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def base_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """The server on a free loopback port, answering from recorded files."""
    app = create_app(registries(built_registry(tmp_path_factory.mktemp("ror"))))
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
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


def test_the_gateway_lists_and_pins_every_server_over_http(gateway: Gateway) -> None:
    assert gateway.unavailable == {}
    assert set(gateway.available) == {"datacite", "crossref", "orcid", "ror"}


def test_the_server_refuses_a_host_it_was_not_told_of(base_url: str) -> None:
    import httpx

    resp = httpx.post(
        f"{base_url}/datacite/mcp",
        headers={"Host": "attacker.example", "Content-Type": "application/json"},
        content=b"{}",
    )
    assert resp.status_code in {400, 421}


@pytest.mark.parametrize(
    ("server", "tool", "arguments", "record_id"),
    [
        ("datacite", "get_doi", {"doi": DATACITE_DOI}, DATACITE_DOI),
        ("crossref", "get_doi", {"doi": CROSSREF_DOI}, CROSSREF_DOI),
        ("orcid", "get_orcid", {"orcid": ORCID_ID}, f"https://orcid.org/{ORCID_ID}"),
        ("ror", "get_organisation", {"id": NERC}, NERC),
    ],
)
def test_a_found_record_is_recorded_and_hashed_by_the_gateway(
    gateway: Gateway, server: str, tool: str, arguments: dict[str, str], record_id: str
) -> None:
    pinned = gateway.available[server]
    result = asyncio.run(gateway.upstream.call_tool(pinned.server, tool, arguments))
    assert not result.is_error
    [retrieval] = recorded(pinned, tool, result.structured_content, datetime.now(UTC))
    assert retrieval.source_id == f"tool:{server}/{record_id}"
    assert result.structured_content is not None
    [record] = result.structured_content["records"]
    assert retrieval.content_hash == content_hash(record, pinned.server.canonicalisation)


def test_a_miss_records_nothing(gateway: Gateway) -> None:
    pinned = gateway.available["datacite"]
    result = asyncio.run(
        gateway.upstream.call_tool(pinned.server, "get_doi", {"doi": CROSSREF_DOI})
    )
    assert not result.is_error and result.structured_content == {"records": []}
    assert recorded(pinned, "get_doi", result.structured_content, datetime.now(UTC)) == []


def test_every_server_is_local_on_loopback(base_url: str) -> None:
    assert {s.locality for s in listed_servers(base_url)} == {"local"}
