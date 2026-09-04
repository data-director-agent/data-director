"""A2A and AG-UI bindings, driven in-process with an httpx ASGI transport (ADR-0001)."""

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

from tests import fakes
from tests.test_harness import make_conductor, request, soil_profile
from workbench.agents.r3.agent import R3Agent
from workbench.contract.models import to_document
from workbench.transport.app import build_app

BASE = "http://testserver"


def _app(runs_dir: Path):
    conductor = make_conductor(runs_dir, r3=R3Agent(retrieval=fakes.FakeRetrieval()), crate=False)
    return conductor, build_app(conductor, base_url=BASE)


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


@pytest.mark.requirement("C5")
def test_agent_card_lists_one_skill_per_agent_with_requirement_tags(runs_dir: Path) -> None:
    _, app = _app(runs_dir)

    async def go() -> dict[str, Any]:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as hc:
            r = await hc.get("/.well-known/agent-card.json")
            body: dict[str, Any] = r.json()
            return body

    card = asyncio.run(go())
    skills = {s["id"]: s for s in card["skills"]}
    assert set(skills) == {"r3.standards-advisor", "stub.abstain"}
    assert "R3" in skills["r3.standards-advisor"]["tags"]
    assert card["supportedInterfaces"][0]["protocolBinding"] == "JSONRPC"


@pytest.mark.requirement("C5")
def test_a2a_message_send_returns_envelope_artifact(runs_dir: Path) -> None:
    conductor, app = _app(runs_dir)
    resp = asyncio.run(_send_a2a(app, to_document(request("r3.standards-advisor"))))
    task = resp.task
    assert task.status.state == TaskState.TASK_STATE_COMPLETED
    (envelope,) = get_data_parts(task.artifacts[0].parts)
    assert envelope["outcome"]["status"] == "succeeded"
    assert envelope["requires_human_review"] is True
    assert conductor.store.get(envelope["invocation_id"]) is not None


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
                "forwardedProps": {"request": to_document(request("stub.abstain", soil_profile()))},
            }
            r = await hc.post("/agui", json=body)
            live = _sse_events(r.text)
            inv = live[-1]["result"]["invocation_id"]
            r2 = await hc.get(f"/agui/runs/{inv}")
            r3 = await hc.get("/runs")
            return live, _sse_events(r2.text), r3.json()

    live, replay, index = asyncio.run(go())
    assert [e["type"] for e in live] == ["RUN_STARTED", "RUN_FINISHED"]
    assert live[1]["result"]["outcome"]["status"] == "abstained"
    assert replay[1]["result"] == live[1]["result"]
    assert index[0]["status"] == "abstained"


def test_schema_and_uischema_are_served(runs_dir: Path) -> None:
    _, app = _app(runs_dir)

    async def go() -> tuple[int, dict[str, Any]]:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as hc:
            a = await hc.get("/schema/envelope.schema.json")
            b = await hc.get("/schema/uischema.json")
            ui: dict[str, Any] = b.json()
            return a.status_code, ui

    status, ui = asyncio.run(go())
    assert status == 200
    assert "payload" in ui
