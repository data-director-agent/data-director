"""AG-UI binding: a run's events for a browser (docs/specs/transport.md). The only importer of
`ag_ui` (docs/specs/dependencies.md).

A run streams as it is made: `RUN_STARTED`, `CUSTOM dd.plan` with the conductor's fixed stages,
`STEP_STARTED` and `STEP_FINISHED` for each stage that runs, `CUSTOM dd.grounding` and
`CUSTOM dd.sources` with the checks' reports inside their stages, then `RUN_FINISHED` with the
envelope as `result`. A run the caller cancels ends with `RUN_FINISHED` whose outcome is
`cancelled`, at once, while the conductor finishes and stores it as failed with `run-cancelled`.
`RUN_ERROR` is only for a request the harness could not make a run of.

Agents are called without streaming and the checks judge the finished envelope, so no text of a
reply reaches a browser before the checks have run; only the stages and the reports stream.

AG-UI's thread is the contract's conversation (docs/specs/orchestration.md): a request carrying
`conversation_id` runs in the thread of that id, and a `threadId` that names another is refused. The
history an agent sees travels in the contract (`Message.history`), not in AG-UI `messages`, so every
transport gives an agent the same input.

Whom a run acts for comes from the `Authenticator`, given the request's headers, never from the
body (docs/specs/policy-and-identity.md). Only the principal who started a run may cancel it.
"""

from __future__ import annotations

import asyncio
import dataclasses
import threading
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
from typing import Any

from ag_ui.core import (
    BaseEvent,
    CustomEvent,
    EventType,
    RunErrorEvent,
    RunFinishedCancelledOutcome,
    RunFinishedEvent,
    RunStartedEvent,
    StepFinishedEvent,
    StepStartedEvent,
)
from ag_ui.encoder import EventEncoder
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from dd_harness.conductor import Conductor, UnknownAgent
from dd_harness.grounding import GroundingReport
from dd_harness.identity import Authenticator, IdentityError
from dd_harness.observe import RunObserver, Step
from dd_harness.policy import PolicyError
from dd_harness.sources import SourceReport
from dd_sdk.contract.models import Envelope, InvocationRequest, Principal
from dd_sdk.contract.validate import ContractViolation

PLAN = "dd.plan"
GROUNDING = "dd.grounding"
SOURCES = "dd.sources"

# What a transport answers with `RUN_ERROR`: a request the harness could not make a run of
# (docs/specs/transport.md). Everything else the conductor decides is an outcome.
REFUSALS: tuple[type[Exception], ...] = (
    ContractViolation,
    ValueError,
    UnknownAgent,
    PolicyError,
    IdentityError,
)

Start = Callable[[RunObserver, threading.Event], Awaitable[Envelope]]


def plan_value(steps: tuple[Step, ...]) -> dict[str, Any]:
    return {"steps": [{"id": step.id, "label": step.label} for step in steps]}


def grounding_value(report: GroundingReport) -> dict[str, Any]:
    return dataclasses.asdict(report)


def sources_value(report: SourceReport) -> dict[str, Any]:
    return {"passed": report.passed, **dataclasses.asdict(report)}


class _Events:
    """A run observer that turns what the conductor's thread tells it into AG-UI events on the
    event loop's queue, in the order told."""

    def __init__(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue[BaseEvent]) -> None:
        self._loop = loop
        self._queue = queue

    def _put(self, event: BaseEvent) -> None:
        self._loop.call_soon_threadsafe(self._queue.put_nowait, event)

    def plan(self, steps: tuple[Step, ...]) -> None:
        self._put(CustomEvent(type=EventType.CUSTOM, name=PLAN, value=plan_value(steps)))

    def step_started(self, step: Step) -> None:
        self._put(StepStartedEvent(type=EventType.STEP_STARTED, step_name=step.id))

    def step_finished(self, step: Step) -> None:
        self._put(StepFinishedEvent(type=EventType.STEP_FINISHED, step_name=step.id))

    def grounding(self, report: GroundingReport) -> None:
        self._put(CustomEvent(type=EventType.CUSTOM, name=GROUNDING, value=grounding_value(report)))

    def sources(self, report: SourceReport) -> None:
        self._put(CustomEvent(type=EventType.CUSTOM, name=SOURCES, value=sources_value(report)))


class Cancellation:
    """One streamed run's cancel: `flag` is what the conductor looks at, `asked` what the stream
    waits on. Made and set on the event loop."""

    def __init__(self) -> None:
        self.flag = threading.Event()
        self.asked = asyncio.Event()

    def cancel(self) -> None:
        self.flag.set()
        self.asked.set()


class RunsInFlight:
    """The streamed runs that may still be cancelled, by the principal who started each and its
    AG-UI `runId`. A run leaves when its stream ends, so a finished run cannot be cancelled."""

    def __init__(self) -> None:
        self._runs: dict[tuple[str, str], Cancellation] = {}

    def open(self, principal: Principal, run_id: str) -> Cancellation:
        key = (principal.principal_id, run_id)
        if key in self._runs:
            raise ValueError(f"runId {run_id!r} is already running; send each run with a new one")
        self._runs[key] = cancellation = Cancellation()
        return cancellation

    def close(self, principal: Principal, run_id: str) -> None:
        self._runs.pop((principal.principal_id, run_id), None)

    def cancel(self, principal: Principal, run_id: str) -> bool:
        """Cancel the principal's run `run_id`; False if they have no such run streaming."""
        cancellation = self._runs.get((principal.principal_id, run_id))
        if cancellation is None:
            return False
        cancellation.cancel()
        return True


def _started(thread_id: str, run_id: str) -> RunStartedEvent:
    return RunStartedEvent(type=EventType.RUN_STARTED, thread_id=thread_id, run_id=run_id)


def _retrieve(task: asyncio.Future[Any]) -> None:
    """Read a finished run's exception, so a stream that stopped waiting for it logs no warning
    that it was never read."""
    if not task.cancelled():
        task.exception()


async def stream_run(
    start: Start,
    *,
    thread_id: str,
    run_id: str,
    cancellation: Cancellation | None = None,
) -> AsyncGenerator[BaseEvent]:
    """The events of one run, as the conductor makes it. `start(observer, cancel)` starts the run
    (`Conductor.ainvoke` with that observer and cancel flag, or a caller's wrapper of it) and gives
    its envelope.

    `RUN_STARTED` is sent with the plan, so a request the conductor refuses before it makes a run
    is answered with `RUN_ERROR` alone. Once `cancellation` is asked, the stream ends at once with
    `RUN_FINISHED` whose outcome is `cancelled`; the run goes on in its thread until the conductor
    next looks, and is stored as failed with `run-cancelled`. A stream that ends any other way
    before the run (the client went away) cancels it too.
    """
    cancellation = cancellation or Cancellation()
    queue: asyncio.Queue[BaseEvent] = asyncio.Queue()
    observer = _Events(asyncio.get_running_loop(), queue)
    run = asyncio.ensure_future(start(observer, cancellation.flag))
    run.add_done_callback(_retrieve)
    asked = asyncio.ensure_future(cancellation.asked.wait())
    sent_start = False
    try:
        while True:
            getter = asyncio.ensure_future(queue.get())
            done, _ = await asyncio.wait({getter, run, asked}, return_when=asyncio.FIRST_COMPLETED)
            if getter in done:
                if not sent_start:
                    sent_start = True
                    yield _started(thread_id, run_id)
                yield getter.result()
                continue
            getter.cancel()
            if run in done:
                break
            # Cancelled while the run goes on: what it has said so far, then the end.
            if not sent_start:
                sent_start = True
                yield _started(thread_id, run_id)
            while not queue.empty():
                yield queue.get_nowait()
            yield RunFinishedEvent(
                type=EventType.RUN_FINISHED,
                thread_id=thread_id,
                run_id=run_id,
                outcome=RunFinishedCancelledOutcome(type="cancelled"),
            )
            return
        # The observer's events were put on the loop before the run's result, so they are all
        # queued by now.
        try:
            envelope = run.result()
        except REFUSALS as exc:
            yield RunErrorEvent(type=EventType.RUN_ERROR, message=str(exc))
            return
        if not sent_start:
            sent_start = True
            yield _started(thread_id, run_id)
        while not queue.empty():
            yield queue.get_nowait()
        if cancellation.flag.is_set():
            # Asked as the run ended: the conductor stored it as cancelled, so say so.
            yield RunFinishedEvent(
                type=EventType.RUN_FINISHED,
                thread_id=thread_id,
                run_id=run_id,
                outcome=RunFinishedCancelledOutcome(type="cancelled"),
            )
            return
        yield RunFinishedEvent(
            type=EventType.RUN_FINISHED,
            thread_id=thread_id,
            run_id=run_id,
            result=envelope.to_document(),
        )
    finally:
        asked.cancel()
        if not run.done():
            cancellation.flag.set()


def sse(events: AsyncIterator[BaseEvent] | list[BaseEvent]) -> Response:
    """Server-sent events, one AG-UI event each."""
    encoder = EventEncoder()

    async def gen() -> AsyncIterator[str]:
        if isinstance(events, list):
            for event in events:
                yield encoder.encode(event)
            return
        async for event in events:
            yield encoder.encode(event)

    return StreamingResponse(gen(), media_type=encoder.get_content_type())


def _error(message: str) -> Response:
    return sse([RunErrorEvent(type=EventType.RUN_ERROR, message=message)])


def _stored_events(envelope: dict[str, Any], thread_id: str, run_id: str) -> list[BaseEvent]:
    return [
        _started(thread_id, run_id),
        RunFinishedEvent(
            type=EventType.RUN_FINISHED, thread_id=thread_id, run_id=run_id, result=envelope
        ),
    ]


def agui_routes(
    conductor: Conductor,
    authenticator: Authenticator,
    runs: RunsInFlight | None = None,
) -> list[Route]:
    """`POST /agui` runs one invocation and streams it; `POST /agui/runs/{run_id}/cancel` cancels
    the caller's run of that AG-UI `runId`; `GET /agui/runs/{invocation_id}` replays a stored run
    as `RUN_STARTED` and `RUN_FINISHED`, since its stages were not kept."""
    in_flight = runs if runs is not None else RunsInFlight()

    async def run_agent(request: Request) -> Response:
        """The body is an AG-UI `RunAgentInput`; `forwardedProps.request` (or `forwarded_props`)
        carries the `InvocationRequest` document."""
        body = await request.json()
        if not isinstance(body, dict):
            return _error("the body must be an AG-UI RunAgentInput")
        thread_id = str(body.get("threadId") or body.get("thread_id") or "thread")
        run_id = str(body.get("runId") or body.get("run_id") or "run")
        props = body.get("forwardedProps") or body.get("forwarded_props") or {}
        doc = props.get("request") if isinstance(props, dict) else None
        if not isinstance(doc, dict):
            return _error("forwardedProps.request must be an InvocationRequest")
        try:
            invocation = InvocationRequest.model_validate(doc)
            if invocation.conversation_id is not None:
                given = body.get("threadId") or body.get("thread_id")
                if given and given != invocation.conversation_id:
                    raise ValueError(
                        f"threadId {given!r} is not the request's conversation_id "
                        f"{invocation.conversation_id!r}"
                    )
                thread_id = invocation.conversation_id
            # In a thread: verifying a token may fetch the issuer's keys.
            acting_for = await asyncio.to_thread(authenticator.principal_for, request.headers)
            cancellation = in_flight.open(acting_for, run_id)
        except REFUSALS as exc:
            return _error(str(exc))

        def start(observer: RunObserver, cancel: threading.Event) -> Awaitable[Envelope]:
            return conductor.ainvoke(
                invocation, acting_for=acting_for, observer=observer, cancel=cancel
            )

        async def events() -> AsyncIterator[BaseEvent]:
            try:
                async for event in stream_run(
                    start, thread_id=thread_id, run_id=run_id, cancellation=cancellation
                ):
                    yield event
            finally:
                in_flight.close(acting_for, run_id)

        return sse(events())

    async def cancel_run(request: Request) -> Response:
        run_id = request.path_params["run_id"]
        try:
            acting_for = await asyncio.to_thread(authenticator.principal_for, request.headers)
        except IdentityError as exc:
            return JSONResponse({"error": str(exc)}, status_code=401)
        if not in_flight.cancel(acting_for, run_id):
            return JSONResponse({"error": f"no run {run_id} of yours is running"}, status_code=404)
        return JSONResponse({"cancelled": run_id}, status_code=202)

    async def replay_run(request: Request) -> Response:
        invocation_id = request.path_params["invocation_id"]
        envelope = conductor.store.get(invocation_id)
        if envelope is None:
            return JSONResponse({"error": f"no run {invocation_id}"}, status_code=404)
        thread_id = envelope.get("conversation_id") or "replay"
        return sse(_stored_events(envelope, thread_id, invocation_id))

    return [
        Route("/agui", run_agent, methods=["POST"]),
        Route("/agui/runs/{run_id}/cancel", cancel_run, methods=["POST"]),
        Route("/agui/runs/{invocation_id}", replay_run, methods=["GET"]),
    ]


__all__ = [
    "GROUNDING",
    "PLAN",
    "REFUSALS",
    "SOURCES",
    "Cancellation",
    "RunsInFlight",
    "agui_routes",
    "sse",
    "stream_run",
]
