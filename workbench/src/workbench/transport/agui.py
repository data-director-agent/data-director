"""AG-UI run events for the shell (ADR-0001). The only importer of `ag_ui` (ADR-0006).

Two events per run, `RUN_STARTED` then `RUN_FINISHED` with the envelope as `result`. With one
synchronous agent there is nothing else to carry; streaming and the `suspended` interrupt
arrive with the events that need them.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from ag_ui.core import EventType, RunErrorEvent, RunFinishedEvent, RunStartedEvent
from ag_ui.encoder import EventEncoder
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

from dd_sdk.contract.models import InvocationRequest
from dd_sdk.contract.validate import ContractViolation
from workbench.conductor import Conductor


def _events_for(envelope: dict[str, Any], thread_id: str, run_id: str) -> list[Any]:
    return [
        RunStartedEvent(type=EventType.RUN_STARTED, thread_id=thread_id, run_id=run_id),
        RunFinishedEvent(
            type=EventType.RUN_FINISHED, thread_id=thread_id, run_id=run_id, result=envelope
        ),
    ]


def _sse(events: list[Any], accept: str | None) -> Response:
    encoder = EventEncoder(accept=accept or "text/event-stream")

    async def gen() -> AsyncIterator[str]:
        for ev in events:
            yield encoder.encode(ev)

    return StreamingResponse(gen(), media_type=encoder.get_content_type())


async def run_agent(request: Request, conductor: Conductor) -> Response:
    """POST /agui — body is an AG-UI RunAgentInput; `forwardedProps.request` (or `forwarded_props`)
    carries the InvocationRequest document."""
    body = await request.json()
    thread_id = str(body.get("threadId") or body.get("thread_id") or "thread")
    run_id = str(body.get("runId") or body.get("run_id") or "run")
    props = body.get("forwardedProps") or body.get("forwarded_props") or {}
    doc = props.get("request") if isinstance(props, dict) else None
    accept = request.headers.get("accept")
    if not isinstance(doc, dict):
        return _sse(
            [
                RunErrorEvent(
                    type=EventType.RUN_ERROR,
                    message="forwardedProps.request must be an InvocationRequest",
                )
            ],
            accept,
        )
    try:
        invocation = InvocationRequest.model_validate(doc)
        envelope = await asyncio.to_thread(conductor.invoke, invocation)
    except (ContractViolation, ValueError) as exc:
        return _sse([RunErrorEvent(type=EventType.RUN_ERROR, message=str(exc))], accept)
    return _sse(_events_for(envelope.to_document(), thread_id, run_id), accept)


async def replay_run(request: Request, conductor: Conductor) -> Response:
    """GET /agui/runs/{invocation_id} — the same two events, from the store."""
    invocation_id = request.path_params["invocation_id"]
    envelope = conductor.store.get(invocation_id)
    if envelope is None:
        return JSONResponse({"error": f"no run {invocation_id}"}, status_code=404)
    return _sse(
        _events_for(envelope, thread_id="replay", run_id=invocation_id),
        request.headers.get("accept"),
    )
