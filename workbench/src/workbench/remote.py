"""An agent that runs in another process, reached over A2A (ADR-0011).

`RemoteAgent.call` sends the `InvocationRequest` with the conductor's `input_ref`, `input_hash`,
`traceparent` and, for a delegation agent, its `DelegationGrant` (ADR-0012), waits for the task
to finish, and returns `Received`: the agent's `AgentResult` and, beside it, the spans the agent
recorded. The conductor imports those spans into its trace before linting. `RemoteAgent`
deliberately has no `Agent.run`, so there is no way to take the result and leave the spans
behind. Nothing here decides whether the result is acceptable; the conductor's input check,
payload check and grounding linter do.

`from_url` reads the agent card and rebuilds the `AgentSpec` from the Data Director extension,
resolving class names against the central contract.

Each call opens its own event loop (`asyncio.run`): the conductor is synchronous, and every
transport already calls it from a worker thread. `client_factory` gives the httpx client for one
call; tests pass one bound to an in-process ASGI app, so the A2A wire is exercised without a
network.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
from a2a.client import ClientConfig, create_client
from a2a.helpers import get_data_parts, get_text_parts, new_data_part
from a2a.types import Message, Role, SendMessageRequest, TaskState
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from dd_sdk.agent import AgentResult, AgentSpec, RunContext, SpecError, spec_from_description
from dd_sdk.contract.models import InvocationRequest, new_invocation_id, to_document
from dd_sdk.delegate import DelegationGrant
from dd_sdk.tracing import records_from_jsonl
from dd_sdk.wire import (
    ARTIFACT_NAME,
    CARD_PATH,
    EXTENSION_URI,
    META_INPUT_HASH,
    META_INPUT_REF,
    META_TRACEPARENT,
    WireError,
    reply_from_document,
)

DEFAULT_TIMEOUT_S = 60.0

ClientFactory = Callable[[str, float], httpx.AsyncClient]


class RemoteAgentError(Exception):
    """The agent could not be reached, failed its task, or answered outside the contract."""


def default_client(base_url: str, timeout_s: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=base_url, timeout=timeout_s)


@dataclass(frozen=True)
class Received:
    """What came back from one invocation: the agent's result and the spans it recorded, as
    `ReadableSpan.to_json` documents. An in-process agent's spans are already in the conductor's
    trace, so it has none here."""

    result: AgentResult
    spans: tuple[dict[str, Any], ...] = ()


def spec_from_card(card: dict[str, Any]) -> AgentSpec:
    """The `AgentSpec` an agent card declares through the Data Director extension."""
    extensions = (card.get("capabilities") or {}).get("extensions") or []
    for ext in extensions:
        if ext.get("uri") == EXTENSION_URI:
            return spec_from_description(ext.get("params") or {})
    raise SpecError(f"agent card {card.get('name')!r} does not declare {EXTENSION_URI}")


@dataclass
class RemoteAgent:
    spec: AgentSpec
    url: str
    timeout_s: float = DEFAULT_TIMEOUT_S
    client_factory: ClientFactory = default_client

    @classmethod
    def from_url(
        cls,
        url: str,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        client_factory: ClientFactory = default_client,
    ) -> RemoteAgent:
        """Read the card at `url`. Raises `RemoteAgentError` if it cannot be read, `SpecError`
        if it does not describe a Data Director agent this contract admits."""

        async def fetch() -> dict[str, Any]:
            async with client_factory(url, timeout_s) as hc:
                response = await hc.get(CARD_PATH)
                response.raise_for_status()
                card: dict[str, Any] = response.json()
                return card

        try:
            card = asyncio.run(fetch())
        except (httpx.HTTPError, ValueError) as exc:
            raise RemoteAgentError(f"cannot read the agent card at {url}: {exc}") from exc
        return cls(
            spec=spec_from_card(card), url=url, timeout_s=timeout_s, client_factory=client_factory
        )

    def call(
        self, request: InvocationRequest, ctx: RunContext, grant: DelegationGrant | None = None
    ) -> Received:
        carrier: dict[str, str] = {}
        TraceContextTextMapPropagator().inject(carrier)  # the conductor's current span
        metadata = {
            META_INPUT_REF: ctx.input_ref,
            META_INPUT_HASH: ctx.input_hash,
            META_TRACEPARENT: carrier.get(META_TRACEPARENT, ""),
        }
        if grant is not None:  # a delegation agent's callback (ADR-0012)
            metadata |= grant.metadata()
        try:
            body = asyncio.run(self._send(to_document(request), metadata))
        except (httpx.HTTPError, TimeoutError) as exc:
            raise RemoteAgentError(f"{self.spec.agent_id} at {self.url}: {exc!r}") from exc
        return self._parse(body)

    async def _send(self, request_doc: dict[str, Any], metadata: dict[str, str]) -> Any:
        async with asyncio.timeout(self.timeout_s):
            async with self.client_factory(self.url, self.timeout_s) as hc:
                client = await create_client(
                    agent=self.url, client_config=ClientConfig(streaming=False, httpx_client=hc)
                )
                message = Message(
                    role=Role.ROLE_USER,
                    parts=[new_data_part(request_doc)],
                    message_id=new_invocation_id(),
                    metadata=metadata,
                )
                last = None
                async for response in client.send_message(SendMessageRequest(message=message)):
                    last = response
                return last

    def _parse(self, response: Any) -> Received:
        agent_id = self.spec.agent_id
        task = getattr(response, "task", None)
        if task is None:
            raise RemoteAgentError(f"{agent_id} returned no task")
        if task.status.state != TaskState.TASK_STATE_COMPLETED:
            state = TaskState.Name(task.status.state)
            raise RemoteAgentError(
                _failure_detail(task) or f"{agent_id} task ended in {state}, not completed"
            )
        artifacts = [a for a in task.artifacts if a.name == ARTIFACT_NAME]
        if len(artifacts) != 1:
            raise RemoteAgentError(
                f"{agent_id} returned {len(artifacts)} {ARTIFACT_NAME} artifacts"
            )
        parts = get_data_parts(artifacts[0].parts)
        if len(parts) != 1 or not isinstance(parts[0], dict):
            raise RemoteAgentError(f"{agent_id} returned a malformed {ARTIFACT_NAME} artifact")
        try:
            result, spans = reply_from_document(parts[0])
            records_from_jsonl(list(spans))  # every span must be readable by the linter
        except (WireError, KeyError, ValueError, TypeError) as exc:
            raise RemoteAgentError(f"{agent_id}: {exc}") from exc
        return Received(result, spans)


def _failure_detail(task: Any) -> str | None:
    message = task.status.message if task.status.HasField("message") else None
    if message is None:
        return None
    for part in get_data_parts(message.parts):
        if isinstance(part, dict) and "error" in part:
            return str(part["error"])
    text = get_text_parts(message.parts)
    return " ".join(text) if text else None
