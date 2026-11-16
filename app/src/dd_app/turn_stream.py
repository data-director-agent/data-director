"""A conversation turn streamed over AG-UI, and its cancel (docs/specs/app.md, "Run events to the
browser"): `POST /api/conversations/{id}/turns/stream` and
`POST /api/conversations/{id}/turns/{run_id}/cancel`, signed in as the app's other `/api` routes."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import AsyncIterator
from typing import Any

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from dd_app.governance import Governance, TurnConflictError, UnknownConversationError
from dd_app.problems import no_conversation, problem, refused
from dd_app.turn_body import parse_turn
from dd_harness.observe import RunObserver
from dd_harness.transport.agui import REFUSALS, RunsInFlight, sse, stream_run
from dd_sdk.contract.models import Envelope, Principal

log = logging.getLogger(__name__)


class TurnRefusedError(Exception):
    """A streamed turn refused once its stream was open, said in the stream's `RUN_ERROR`."""


class TurnStreams:
    """The turns streaming now, by whom each acts for and its AG-UI `runId`, so that a turn may be
    cancelled while its stream is open (docs/specs/transport.md, Cancelling)."""

    def __init__(self, governance: Governance) -> None:
        self.governance = governance
        self.in_flight = RunsInFlight()

    async def stream(self, request: Request, acting_for: Principal) -> Response:
        """One turn, streamed as its run is made (docs/specs/app.md, "Run events to the browser").

        The body is an AG-UI `RunAgentInput`, as `HttpAgent` posts it: `runId` names the run for
        `cancel`, `threadId` is the conversation's id if given, and `forwardedProps` is the
        turn's body, checked as the JSON route checks it. `messages` is not read: the server builds
        the history from the stored turns. What can be refused before the stream opens is answered
        as the JSON route answers it; a turn refused once the stream is open, such as one that no
        longer follows the latest turn, is `RUN_ERROR` alone."""
        conversation_id = request.path_params["conversation_id"]
        try:
            body = await request.json()
        except ValueError:
            return refused("The body is not JSON.")
        if not isinstance(body, dict):
            return refused("The body must be an AG-UI RunAgentInput.")
        run_id, thread_id = body.get("runId"), body.get("threadId")
        if not isinstance(run_id, str) or not run_id:
            return refused("The body must give `runId`, a string naming this run.")
        if thread_id is not None and thread_id != conversation_id:
            return refused(
                f"`threadId` {thread_id!r} is not this conversation, {conversation_id!r}."
            )
        sent = parse_turn(body.get("forwardedProps"))
        if isinstance(sent, Response):
            return sent
        if (
            await run_in_threadpool(self.governance.conversation, conversation_id, acting_for)
            is None
        ):
            return no_conversation(conversation_id)
        try:
            cancellation = self.in_flight.open(acting_for, run_id)
        except ValueError as exc:
            return problem(409, "run-id-in-use", "This run is already streaming", str(exc))

        async def start(observer: RunObserver, cancel: threading.Event) -> Envelope:
            try:
                return await self.governance.turn(
                    conversation_id, sent, acting_for, observer=observer, cancel=cancel
                )
            except UnknownConversationError:
                raise TurnRefusedError(f"No conversation {conversation_id!r}.") from None

        async def events() -> AsyncIterator[Any]:
            started = time.monotonic()
            try:
                async for event in stream_run(
                    start,
                    thread_id=conversation_id,
                    run_id=run_id,
                    cancellation=cancellation,
                    refusals=(*REFUSALS, TurnConflictError, TurnRefusedError),
                ):
                    yield event
            finally:
                self.in_flight.close(acting_for, run_id)
                log.info(
                    "data-director: streamed turn %s ended in %.1f s",
                    conversation_id,
                    time.monotonic() - started,
                )

        return sse(events())

    async def cancel(self, request: Request, acting_for: Principal) -> Response:
        """Cancel the person's streaming turn whose AG-UI `runId` the path names: `202`, and the
        stream ends with `RUN_FINISHED` cancelled; `404` if they have no such turn streaming. The
        run is stored as failed with `run-cancelled` (docs/specs/transport.md, Cancelling)."""
        run_id = request.path_params["run_id"]
        if not self.in_flight.cancel(acting_for, run_id):
            return problem(
                404,
                "run-not-streaming",
                "No such run streaming",
                f"No run {run_id!r} of yours is streaming.",
            )
        return JSONResponse({"cancelled": run_id}, status_code=202)
