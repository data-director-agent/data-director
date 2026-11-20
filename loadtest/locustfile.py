"""Load test of the whole stack: the app's /api, the harness, the agents and (fake) models.

Each simulated user is one researcher: it starts a conversation in a new project, takes turns with
the orchestrator (as JSON, or streamed as the shell does), browses its lists and now and then runs
`example.hello` directly. Every user keeps to its own conversation, because the app takes one turn
per conversation at a time (app/src/dd_app/turn_lock.py); a 409 here is contention worth seeing.

Run it as README.md says. Settings, all optional:

- LOADTEST_SHAPE: smoke, step or soak (shapes.py).
- LOADTEST_AGENT: the agent turns are sent to; by default the profile's orchestrator.
- LOADTEST_TURNS: turns per conversation before a user starts another (default 5).
- LOADTEST_WAIT_MIN / LOADTEST_WAIT_MAX: think time between tasks, in seconds (default 2 and 8).
- LOADTEST_LISTERS: the weight of `Lister`, a user that only hammers the list routes with no
  think time (default 0: none). With the researchers' weight at 1, `LOADTEST_LISTERS=3` makes
  three in four users listers. Turn p95 should hold while they swamp the listings (#1258); the
  app sheds listings beyond `DD_APP_LISTING_QUEUE` with a 503, which a lister counts as `shed`
  and not as a failure.
- LOADTEST_MAX_P95_MS: the highest 95th-percentile turn time that passes (default 10000).
- LOADTEST_MAX_ERROR_RATIO: the highest share of failed requests that passes (default 0.01).
"""

from __future__ import annotations

import json
import logging
import os
import random
import time
import uuid
from collections.abc import Iterator
from typing import Any

from locust import HttpUser, between, events, task
from locust.env import Environment
from prompts import PROMPTS, SALUTATION
from shapes import StagedShape

__all__ = ["Lister", "Researcher", "StagedShape"]

JSON = {"Content-Type": "application/json", "Accept": "application/json"}
TURN = "/api/conversations/[id]/turns"
STREAM = "/api/conversations/[id]/turns/stream"
FIRST_EVENT = f"{STREAM} first event"
WHOLE_STREAM = f"{STREAM} whole run"
TURN_NAMES = (TURN, WHOLE_STREAM)
log = logging.getLogger(__name__)


def _float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


class Researcher(HttpUser):
    host = "http://127.0.0.1:7860"
    wait_time = between(_float("LOADTEST_WAIT_MIN", 2), _float("LOADTEST_WAIT_MAX", 8))

    agent_id: str
    conversation_id: str
    follows: str | None
    turns: int

    def on_start(self) -> None:
        self.agent_id = os.environ.get("LOADTEST_AGENT") or self._orchestrator()
        self._new_conversation()

    def _orchestrator(self) -> str:
        with self.client.get("/api/agents", headers=JSON, catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"no agents: {response.status_code}")
                raise RuntimeError("GET /api/agents failed; is the stack up?")
            orchestrator = response.json()["profile"]["orchestrator"]
        if not orchestrator:
            raise RuntimeError("The profile names no orchestrator; set LOADTEST_AGENT.")
        return str(orchestrator)

    def _new_conversation(self) -> None:
        response = self.client.post("/api/conversations", data="{}", headers=JSON)
        response.raise_for_status()
        self.conversation_id = response.json()["conversation_id"]
        self.follows, self.turns = None, 0

    def _turn_body(self) -> dict[str, Any]:
        if self.turns >= int(os.environ.get("LOADTEST_TURNS", 5)):
            self._new_conversation()
        return {
            "agent_id": self.agent_id,
            "message_text": random.choice(PROMPTS),
            "follows": self.follows,
        }

    def _took_turn(self, envelope: dict[str, Any]) -> None:
        self.follows = envelope["invocation_id"]
        self.turns += 1

    @task(3)
    def send_turn(self) -> None:
        body = self._turn_body()
        url = f"/api/conversations/{self.conversation_id}/turns"
        with self.client.post(
            url, data=json.dumps(body), headers=JSON, name=TURN, catch_response=True
        ) as response:
            if response.status_code == 200:
                self._took_turn(response.json()["envelope"])
            elif response.status_code == 409:
                response.failure("409 turn conflict")
                self._new_conversation()
            else:
                response.failure(f"{response.status_code}: {response.text[:200]}")

    @task(1)
    def stream_turn(self) -> None:
        """A turn streamed as AG-UI events, as the shell sends it. Locust times the request to its
        headers; the time to the first event and to the end of the run are reported beside it."""
        turn = self._turn_body()  # may start a new conversation, so before the id is read
        body = {
            "threadId": self.conversation_id,
            "runId": str(uuid.uuid4()),
            "messages": [],
            "forwardedProps": turn,
        }
        url = f"/api/conversations/{self.conversation_id}/turns/stream"
        headers = {**JSON, "Accept": "text/event-stream"}
        started = time.perf_counter()
        with self.client.post(
            url,
            data=json.dumps(body),
            headers=headers,
            name=STREAM,
            stream=True,
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"{response.status_code}: {response.text[:200]}")
                if response.status_code == 409:
                    self._new_conversation()
                return
            outcome = self._read_stream(response.iter_lines(decode_unicode=True), started)
            failure = self._finish_stream(outcome)
            if failure:
                response.failure(failure)
            _report(WHOLE_STREAM, started, failure)

    @staticmethod
    def _read_stream(lines: Iterator[str], started: float) -> dict[str, Any] | None:
        """The stream's closing event, RUN_FINISHED or RUN_ERROR; reports its first event."""
        outcome = None
        first = True
        for line in lines:
            if not line or not line.startswith("data:"):
                continue
            if first:
                _report(FIRST_EVENT, started, None)
                first = False
            event = json.loads(line[5:])
            if event.get("type") in ("RUN_FINISHED", "RUN_ERROR"):
                outcome = event
        return outcome

    def _finish_stream(self, outcome: dict[str, Any] | None) -> str | None:
        """Why the streamed turn failed, or None, having taken the turn if it succeeded."""
        if outcome is None:
            return "stream ended without RUN_FINISHED"
        if outcome["type"] == "RUN_ERROR":
            self._new_conversation()
            return f"RUN_ERROR: {str(outcome.get('message'))[:200]}"
        if not isinstance(outcome.get("result"), dict):
            return "RUN_FINISHED without an envelope (cancelled?)"
        self._took_turn(outcome["result"])
        return None

    @task(2)
    def browse(self) -> None:
        for path in ("/api/conversations", "/api/projects", "/api/runs"):
            self.client.get(path, headers=JSON)
        self.client.get(
            f"/api/conversations/{self.conversation_id}",
            headers=JSON,
            name="/api/conversations/[id]",
        )

    @task(1)
    def start_run(self) -> None:
        body = {"agent_id": "example.hello", "input": SALUTATION}
        self.client.post("/api/runs", data=json.dumps(body), headers=JSON)


class Lister(HttpUser):
    """Keeps the list routes busy with no think time, to show that turns still complete while
    listings are slow (#1258). Off unless LOADTEST_LISTERS is above 0."""

    host = "http://127.0.0.1:7860"
    weight = int(_float("LOADTEST_LISTERS", 0))
    wait_time = between(0, 0.5)

    @task
    def list_everything(self) -> None:
        for path in ("/api/projects", "/api/conversations", "/api/runs"):
            with self.client.get(path, headers=JSON, catch_response=True) as response:
                if response.status_code == 503 and response.headers.get("Retry-After"):
                    response.request_meta["name"] = f"{path} shed"
                    response.success()


def _report(name: str, started: float, failure: str | None) -> None:
    """Record a timing Locust cannot see for itself, from `started` to now."""
    events.request.fire(  # type: ignore[no-untyped-call]
        request_type="SSE",
        name=name,
        response_time=(time.perf_counter() - started) * 1000,
        response_length=0,
        exception=RuntimeError(failure) if failure else None,
        context={},
    )


@events.quitting.add_listener  # type: ignore[untyped-decorator]
def _thresholds(environment: Environment, **_: Any) -> None:
    """Fail the run (exit code 1) if turns were too slow or too many requests failed."""
    max_p95 = _float("LOADTEST_MAX_P95_MS", 10_000)
    max_errors = _float("LOADTEST_MAX_ERROR_RATIO", 0.01)
    stats = environment.stats
    problems = []
    for name in TURN_NAMES:
        entry = stats.get(name, "SSE" if name == WHOLE_STREAM else "POST")
        if entry.num_requests:
            p95 = entry.get_response_time_percentile(0.95)
            if p95 > max_p95:
                problems.append(f"{name} p95 {p95:.0f} ms > {max_p95:.0f} ms")
    if stats.total.fail_ratio > max_errors:
        problems.append(f"error ratio {stats.total.fail_ratio:.2%} > {max_errors:.2%}")
    if problems:
        log.error("Load test thresholds not met:\n  %s", "\n  ".join(problems))
        environment.process_exit_code = 1
