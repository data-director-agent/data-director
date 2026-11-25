"""The harness card names each agent's schemas by digest and serves them beside it; a delegation
agent fetches them only when the digest changes (docs/specs/orchestration.md, #1590)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from dd_harness.testing import ScriptedAgent, make_conductor, request, review_of_input
from dd_harness.transport.a2a import a2a_routes
from dd_sdk import delegate
from dd_sdk.contract.models import GroundingMode
from dd_sdk.delegate import DelegationGrant, DelegationRefused, HarnessDelegate
from dd_sdk.manifest import schemas_digest
from dd_sdk.wire import MANIFEST_EXTENSION_URI

SCHEMA_KEYS = {"schemas", "json_schema", "shacl", "context"}


def keys(document: Any) -> Iterator[str]:
    """Every key anywhere in a JSON document."""
    if isinstance(document, dict):
        for key, value in document.items():
            yield key
            yield from keys(value)
    elif isinstance(document, list):
        for item in document:
            yield from keys(item)


def harness(tmp_path: Path) -> TestClient:
    conductor = make_conductor(tmp_path, ScriptedAgent(GroundingMode.NONE, review_of_input))
    return TestClient(Starlette(routes=a2a_routes(conductor, None, "http://harness.test")[1]))


def manifest_of(card: dict[str, Any]) -> list[dict[str, Any]]:
    [extension] = [
        e for e in card["capabilities"]["extensions"] if e["uri"] == MANIFEST_EXTENSION_URI
    ]
    agents: list[dict[str, Any]] = extension["params"]["agents"]
    return agents


def test_the_harness_card_carries_no_schemas_only_their_digests(tmp_path: Path) -> None:
    client = harness(tmp_path)
    manifest = manifest_of(client.get("/.well-known/agent-card.json").json())
    assert manifest
    assert not SCHEMA_KEYS & set(keys(manifest))
    for entry in manifest:
        schemas = client.get(f"/a2a/schemas/{entry['agent_id']}")
        assert schemas.status_code == 200
        # What the card names is what is served: the delegation agent can check one by the other.
        assert schemas_digest(schemas.json()) == entry["schemas_digest"]
        assert set(entry["accepts"]) <= set(schemas.json())
        assert all("json_schema" in s for s in schemas.json().values())


def test_an_agents_schemas_are_revalidated_with_a_304_and_an_unknown_agent_is_a_404(
    tmp_path: Path,
) -> None:
    client = harness(tmp_path)
    [entry] = manifest_of(client.get("/.well-known/agent-card.json").json())
    path = f"/a2a/schemas/{entry['agent_id']}"
    first = client.get(path)
    assert first.headers["etag"] == f'"{entry["schemas_digest"]}"'
    unchanged = client.get(path, headers={"If-None-Match": first.headers["etag"]})
    assert unchanged.status_code == 304
    assert unchanged.content == b""
    assert client.get("/a2a/schemas/no.such.agent").status_code == 404


class FakeHarness:
    """A harness card listing one agent, `a`, and that agent's schemas, with the requests made."""

    def __init__(self, schemas: dict[str, Any], digest: str | None = None) -> None:
        self.paths: list[str] = []
        self.serve(schemas, digest)

    def serve(self, schemas: dict[str, Any], digest: str | None = None) -> None:
        self.schemas = schemas
        entry = {"agent_id": "a", "schemas_digest": digest or schemas_digest(schemas)}
        self.card = {
            "name": "h",
            "capabilities": {
                "extensions": [{"uri": MANIFEST_EXTENSION_URI, "params": {"agents": [entry]}}]
            },
        }

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.paths.append(request.url.path)
        if request.url.path == "/a2a/schemas/a":
            return httpx.Response(200, json=self.schemas)
        return httpx.Response(200, json=self.card)

    def delegate(self) -> HarnessDelegate:
        def factory(base_url: str, timeout_s: float) -> httpx.AsyncClient:
            return httpx.AsyncClient(
                base_url=base_url, transport=httpx.MockTransport(self.handler), timeout=timeout_s
            )

        return HarnessDelegate(
            grant=DelegationGrant(url="http://harness.test", token="t"),
            parent=request("fake.delegation"),
            tracer=None,  # type: ignore[arg-type]
            client_factory=factory,
        )


@pytest.fixture(autouse=True)
def no_cached_copies() -> Iterator[None]:
    delegate._CARDS.clear()
    delegate._SCHEMAS.clear()
    yield
    delegate._CARDS.clear()
    delegate._SCHEMAS.clear()


def test_a_delegation_agent_fetches_an_agents_schemas_once_while_their_digest_holds() -> None:
    fake = FakeHarness({"X": {"json_schema": {"type": "object"}}})
    assert fake.delegate().schemas_of(["a"]) == {"a": fake.schemas}
    assert fake.delegate().schemas_of(["a"]) == {"a": fake.schemas}
    assert fake.paths.count("/a2a/schemas/a") == 1

    fake.serve({"X": {"json_schema": {"type": "object", "required": ["x"]}}})
    assert fake.delegate().schemas_of(["a"]) == {"a": fake.schemas}
    assert fake.paths.count("/a2a/schemas/a") == 2


def test_schemas_that_do_not_match_the_cards_digest_are_a_refusal() -> None:
    fake = FakeHarness({"X": {}}, digest="0" * 64)
    with pytest.raises(DelegationRefused, match="digest"):
        fake.delegate().schemas_of(["a"])


def test_schemas_of_an_agent_the_card_does_not_list_are_a_refusal() -> None:
    with pytest.raises(DelegationRefused, match="no schemas"):
        FakeHarness({}).delegate().schemas_of(["b"])
