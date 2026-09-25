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
from dd_agent_quality.classes import MetadataRecord
from dd_agent_stub.agent import AbstainingStub
from dd_sdk.contract.models import Claim, new_invocation_id, to_document
from workbench.identity import OperatorAssertion
from workbench.testing import TEST_PRINCIPAL, make_conductor, request
from workbench.transport.app import build_app

BASE = "http://testserver"


def record() -> MetadataRecord:
    """An input for the real quality.reviewer, in its own class."""
    return MetadataRecord(
        identifier="https://doi.org/10.15131/shef.data.00000000",
        title="Soil chemistry survey",
        licence="https://creativecommons.org/licenses/by/4.0/",
        creators=["Example Researcher"],
    )


def claim() -> Claim:
    """An input for the real fact.checker, in its own class."""
    return Claim(text="A DOI does not change when the object moves.")


def _app(runs_dir: Path):
    conductor = make_conductor(
        runs_dir, QualityReviewer(), FactChecker(), HelloWorld(), AbstainingStub()
    )
    return conductor, build_app(conductor, OperatorAssertion(TEST_PRINCIPAL), base_url=BASE)


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


@pytest.mark.requirement("C5.1", "DD-REGISTRY")
def test_agent_card_lists_one_skill_per_agent_from_the_manifest(runs_dir: Path) -> None:
    _, app = _app(runs_dir)
    _, card = _get(app, "/.well-known/agent-card.json")
    skills = {s["id"]: s for s in card["skills"]}
    assert set(skills) == {"quality.reviewer", "fact.checker", "hello.world", "stub.abstain"}
    assert {"grounding:input_only", "accepts:MetadataRecord", "R4.1"} <= set(
        skills["quality.reviewer"]["tags"]
    )
    assert card["supportedInterfaces"][0]["protocolBinding"] == "JSONRPC"


@pytest.mark.requirement("C5.1")
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


@pytest.mark.requirement("C5.1")
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


def _agui_body(request_doc: dict[str, Any], thread_id: str) -> dict[str, Any]:
    return {
        "threadId": thread_id,
        "runId": "r1",
        "messages": [],
        "state": {},
        "tools": [],
        "context": [],
        "forwardedProps": {"request": request_doc},
    }


def test_agui_runs_an_input_written_in_the_shell_form_not_only_a_sample(runs_dir: Path) -> None:
    # What the viewer's input form sends: the class's required slots, optional ones left out.
    _, app = _app(runs_dir)
    doc = {
        **to_document(request("hello.world")),
        "input": {"schema_class": "Salutation", "greeted_name": "Ada"},
    }

    async def go() -> list[dict[str, Any]]:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as hc:
            return _sse_events((await hc.post("/agui", json=_agui_body(doc, "t1"))).text)

    live = asyncio.run(go())
    assert [e["type"] for e in live] == ["RUN_STARTED", "RUN_FINISHED"]
    envelope = live[1]["result"]
    assert envelope["outcome"]["status"] == "succeeded", envelope["outcome"]["statement"]
    assert envelope["payload"]["greeting_text"] == "Hello, Ada!"


@pytest.mark.requirement("DD-CONVERSATION")
def test_agui_thread_is_the_conversation_and_conversations_are_served(runs_dir: Path) -> None:
    _, app = _app(runs_dir)
    conv = new_invocation_id()
    doc = to_document(
        request("quality.reviewer", record()).model_copy(update={"conversation_id": conv})
    )

    async def go() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as hc:
            ok = _sse_events((await hc.post("/agui", json=_agui_body(doc, conv))).text)
            other = {**doc, "invocation_id": new_invocation_id()}
            bad = _sse_events((await hc.post("/agui", json=_agui_body(other, "t9"))).text)
            return ok, bad

    ok, bad = asyncio.run(go())
    assert ok[0]["threadId"] == conv
    assert [e["type"] for e in bad] == ["RUN_ERROR"]
    assert "conversation_id" in bad[0]["message"]

    status, index = _get(app, "/conversations")
    assert status == 200 and index[0]["conversation_id"] == conv
    status, found = _get(app, f"/conversations/{conv}")
    assert status == 200
    assert found["turns"][0]["agent_id"] == "quality.reviewer"
    assert found["turns"][0]["input"]["schema_class"] == "MetadataRecord"
    status, _ = _get(app, f"/conversations/{new_invocation_id()}")
    assert status == 404


def _naming_a_profile() -> dict[str, Any]:
    """A request that tries to choose its own policy, as one could before ADR-0017."""
    doc = to_document(request("quality.reviewer", record()))
    doc["policy_bundle_ref"] = "profile:test-permissive"
    return doc


@pytest.mark.requirement("DD-POLICY-OWNER")
def test_agui_reports_an_unknown_agent_or_a_request_naming_a_profile_as_run_error(
    runs_dir: Path,
) -> None:
    _, app = _app(runs_dir)
    unknown_agent = to_document(request("no.such.agent", record()))

    async def go() -> list[tuple[int, list[dict[str, Any]]]]:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as hc:
            out = []
            for doc in (unknown_agent, _naming_a_profile()):
                r = await hc.post("/agui", json=_agui_body(doc, "t1"))
                out.append((r.status_code, _sse_events(r.text)))
            return out

    (s1, agent_events), (s2, policy_events) = asyncio.run(go())
    assert s1 == s2 == 200
    assert [e["type"] for e in agent_events] == ["RUN_ERROR"]
    assert "no.such.agent" in agent_events[0]["message"]
    assert [e["type"] for e in policy_events] == ["RUN_ERROR"]
    assert "policy_bundle_ref" in policy_events[0]["message"]


@pytest.mark.requirement("DD-POLICY-OWNER")
def test_a2a_fails_a_request_naming_a_profile_and_runs_nothing(runs_dir: Path) -> None:
    conductor, app = _app(runs_dir)
    resp = asyncio.run(_send_a2a(app, _naming_a_profile()))
    assert resp.task.status.state == TaskState.TASK_STATE_FAILED
    assert list(conductor.store.iter_envelopes()) == []


def _saying_whom_it_acts_for() -> dict[str, Any]:
    """A request that tries to choose its own principal."""
    doc = to_document(request("quality.reviewer", record()))
    doc["acting_for"] = {"principal_id": "https://orcid.org/0000-0000-0000-0000", "name": "Else"}
    return doc


@pytest.mark.requirement("DD-ACTS-FOR")
def test_a_request_saying_whom_it_acts_for_is_refused_by_both_transports(runs_dir: Path) -> None:
    conductor, app = _app(runs_dir)
    resp = asyncio.run(_send_a2a(app, _saying_whom_it_acts_for()))
    assert resp.task.status.state == TaskState.TASK_STATE_FAILED

    async def agui() -> list[dict[str, Any]]:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as hc:
            r = await hc.post("/agui", json=_agui_body(_saying_whom_it_acts_for(), "t1"))
            return _sse_events(r.text)

    events = asyncio.run(agui())
    assert [e["type"] for e in events] == ["RUN_ERROR"] and "acting_for" in events[0]["message"]
    assert list(conductor.store.iter_envelopes()) == []


@pytest.mark.requirement("DD-ACTS-FOR")
def test_each_transport_records_the_principal_its_authenticator_names(runs_dir: Path) -> None:
    conductor, app = _app(runs_dir)
    resp = asyncio.run(_send_a2a(app, to_document(request("fact.checker", claim()))))
    assert resp.task.status.state == TaskState.TASK_STATE_COMPLETED

    async def agui() -> None:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as hc:
            doc = to_document(request("fact.checker", claim()))
            await hc.post("/agui", json=_agui_body(doc, "t1"))

    asyncio.run(agui())
    stored = list(conductor.store.iter_envelopes())
    assert len(stored) == 2
    assert all(e["acting_for"] == to_document(TEST_PRINCIPAL) for e in stored)
    status, runs = _get(app, "/runs")
    assert status == 200 and {r["acting_for"] for r in runs} == {TEST_PRINCIPAL.name}


@pytest.mark.requirement("DD-REGISTRY")
def test_manifest_samples_and_schema_are_served(runs_dir: Path) -> None:
    _, app = _app(runs_dir)
    status, manifest = _get(app, "/agents")
    assert status == 200
    by_id = {m["agent_id"]: m for m in manifest["agents"]}
    assert by_id["quality.reviewer"]["derivations"]["score"] == {
        "how": "lexical",
        "recorded_in": None,
    }
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
