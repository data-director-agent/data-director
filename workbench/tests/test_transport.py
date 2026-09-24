"""A2A and AG-UI bindings, the agent manifest and the samples listing, driven in-process with an
httpx ASGI transport (ADR-0001). Nothing here names a payload class."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from a2a.client import ClientConfig, create_client
from a2a.helpers import get_data_parts, new_data_part, new_message
from a2a.types import Role, SendMessageRequest, TaskState

from dd_agent_factcheck.agent import FactChecker
from dd_agent_hello.agent import HelloWorld
from dd_agent_quality.agent import QualityReviewer
from dd_agent_stub.agent import AbstainingStub
from dd_sdk.contract.models import to_document
from workbench.testing import claim, make_conductor, record, request
from workbench.transport.app import build_app

BASE = "http://testserver"


def _app(runs_dir: Path):
    conductor = make_conductor(
        runs_dir, QualityReviewer(), FactChecker(), HelloWorld(), AbstainingStub()
    )
    return conductor, build_app(conductor, base_url=BASE)


def _get(app: Any, path: str) -> tuple[int, Any]:
    async def go() -> tuple[int, Any]:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as hc:
            r = await hc.get(path)
            return r.status_code, (
                r.json() if "json" in r.headers.get("content-type", "") else r.text
            )

    return asyncio.run(go())


async def _send_a2a(app: Any, payload: dict[str, Any]) -> Any:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as hc:
        card_resp = await hc.get("/.well-known/agent-card.json")
        assert card_resp.status_code == 200
        client = await create_client(
            agent=BASE, client_config=ClientConfig(streaming=False, httpx_client=hc)
        )
        msg = new_message([new_data_part(payload)], role=Role.ROLE_USER)
        last = None
        async for resp in client.send_message(SendMessageRequest(message=msg)):
            last = resp
        return last


@pytest.mark.requirement("C5", "DD-REGISTRY")
def test_agent_card_lists_one_skill_per_agent_from_the_manifest(runs_dir: Path) -> None:
    _, app = _app(runs_dir)
    _, card = _get(app, "/.well-known/agent-card.json")
    skills = {s["id"]: s for s in card["skills"]}
    assert set(skills) == {"quality.reviewer", "fact.checker", "hello.world", "stub.abstain"}
    assert {"grounding:input_only", "accepts:MetadataRecord", "R4.1"} <= set(
        skills["quality.reviewer"]["tags"]
    )
    assert card["supportedInterfaces"][0]["protocolBinding"] == "JSONRPC"


@pytest.mark.requirement("C5")
def test_a2a_message_send_returns_envelope_artifact(runs_dir: Path) -> None:
    conductor, app = _app(runs_dir)
    resp = asyncio.run(_send_a2a(app, to_document(request("fact.checker", claim()))))
    task = resp.task
    assert task.status.state == TaskState.TASK_STATE_COMPLETED
    (envelope,) = get_data_parts(task.artifacts[0].parts)
    assert envelope["outcome"]["status"] == "succeeded"
    assert envelope["grounding_mode"] == "retrieval"
    assert envelope["requires_human_review"] is True
    assert conductor.store.get(envelope["invocation_id"]) is not None


@pytest.mark.requirement("DD-INPUT-ACCEPTS")
def test_a2a_input_mismatch_is_an_envelope_not_a_transport_failure(runs_dir: Path) -> None:
    _, app = _app(runs_dir)
    resp = asyncio.run(_send_a2a(app, to_document(request("fact.checker", record()))))
    assert resp.task.status.state == TaskState.TASK_STATE_COMPLETED
    (envelope,) = get_data_parts(resp.task.artifacts[0].parts)
    assert envelope["outcome"]["status"] == "failed"
    assert envelope["problem"]["type"].endswith("/input-not-accepted")


def test_a2a_rejects_malformed_request(runs_dir: Path) -> None:
    _, app = _app(runs_dir)
    resp = asyncio.run(_send_a2a(app, {"agent_id": "stub.abstain"}))  # missing required fields
    assert resp.task.status.state == TaskState.TASK_STATE_FAILED


def _sse_events(text: str) -> list[dict[str, Any]]:
    return [
        json.loads(line[len("data: ") :]) for line in text.splitlines() if line.startswith("data: ")
    ]


@pytest.mark.requirement("C5")
def test_agui_run_and_replay_emit_started_and_finished(runs_dir: Path) -> None:
    _, app = _app(runs_dir)

    async def go() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as hc:
            body = {
                "threadId": "t1",
                "runId": "r1",
                "messages": [],
                "state": {},
                "tools": [],
                "context": [],
                "forwardedProps": {"request": to_document(request("quality.reviewer", record()))},
            }
            r = await hc.post("/agui", json=body)
            live = _sse_events(r.text)
            inv = live[-1]["result"]["invocation_id"]
            r2 = await hc.get(f"/agui/runs/{inv}")
            r3 = await hc.get("/runs")
            return live, _sse_events(r2.text), r3.json()

    live, replay, index = asyncio.run(go())
    assert [e["type"] for e in live] == ["RUN_STARTED", "RUN_FINISHED"]
    assert live[1]["result"]["outcome"]["status"] == "succeeded"
    assert live[1]["result"]["payload"]["schema_class"] == "QualityReview"
    assert replay[1]["result"] == live[1]["result"]
    assert index[0]["status"] == "succeeded"


@pytest.mark.requirement("DD-REGISTRY")
def test_manifest_samples_and_schema_are_served(runs_dir: Path) -> None:
    _, app = _app(runs_dir)
    status, manifest = _get(app, "/agents")
    assert status == 200
    by_id = {m["agent_id"]: m for m in manifest["agents"]}
    assert by_id["quality.reviewer"]["uischema"]  # the shell composes this under `payload`
    status, samples = _get(app, "/samples")
    assert status == 200
    classes = {s["name"]: s["schema_class"] for s in samples}
    assert (
        classes["claim.json"] == "Claim"
        and classes["orda-record.metadata.json"] == "MetadataRecord"
    )
    status, doc = _get(app, "/samples/claim.json")
    assert status == 200 and doc["schema_class"] == "Claim"
    status, _ = _get(app, "/samples/..%2Fpyproject.toml")
    assert status == 404
    status, _ = _get(app, "/samples/nope.json")
    assert status == 404
    status, ui = _get(app, "/schema/uischema.json")
    assert status == 200 and "payload" not in ui and "grounding_mode" in ui
    status, _ = _get(app, "/schema/envelope.schema.json")
    assert status == 200


def test_favicon_is_served(runs_dir: Path) -> None:
    _, app = _app(runs_dir)
    status, _ = _get(app, "/favicon.ico")
    assert status == 200
