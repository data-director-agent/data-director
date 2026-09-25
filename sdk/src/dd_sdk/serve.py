"""Serve one agent over A2A (ADR-0011). With `dd_sdk.delegate`, one of the SDK's two importers of
`a2a` (ADR-0012).

`app(agent, base_url)` is a Starlette application with the agent card at
`/.well-known/agent-card.json` and the JSON-RPC binding at `/a2a`. `main(build)` is the console
script every agent package exposes (`<agent> serve --port N`).

Per request the server starts an isolated tracer, parents it to the `traceparent` the workbench
sent, runs the agent in a worker thread, and returns the result with the spans the agent emitted.
It does no governance: the workbench's conductor applies the policy gate, the input check and the
grounding linter to whatever comes back.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable
from typing import Any

from a2a.helpers import get_data_parts, new_data_part, new_task_from_user_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentExtension, AgentInterface, AgentSkill
from google.protobuf.json_format import MessageToDict
from opentelemetry import context as otel_context
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from starlette.applications import Starlette

from dd_sdk import delegate as delegation
from dd_sdk.agent import Agent, AgentResult, RunContext, describe
from dd_sdk.contract.models import InvocationRequest
from dd_sdk.tracing import make_tracing
from dd_sdk.wire import (
    ARTIFACT_NAME,
    EXTENSION_URI,
    JSONRPC_PATH,
    META_INPUT_HASH,
    META_INPUT_REF,
    META_TRACEPARENT,
    reply_to_document,
)

PROTOCOL_VERSION = "1.0"


def agent_card(agent: Agent, base_url: str) -> AgentCard:
    spec = agent.spec
    entry = describe(spec)
    return AgentCard(
        name=spec.agent_id,
        description=spec.description,
        version=spec.version,
        default_input_modes=["application/json"],
        default_output_modes=["application/json"],
        capabilities=AgentCapabilities(
            streaming=False,
            extensions=[
                AgentExtension(
                    uri=EXTENSION_URI,
                    description="Data Director agent specification (dd_sdk.agent.describe).",
                    required=True,
                    params=entry,
                )
            ],
        ),
        supported_interfaces=[
            AgentInterface(
                protocol_binding="JSONRPC",
                url=base_url.rstrip("/") + JSONRPC_PATH,
                protocol_version=PROTOCOL_VERSION,
            )
        ],
        skills=[
            AgentSkill(
                id=spec.agent_id,
                name=spec.agent_id,
                description=spec.description,
                tags=[
                    "data-director",
                    f"grounding:{spec.grounding_mode.value}",
                    *(f"accepts:{name}" for name in entry["accepts"]),
                    *spec.requirement_ids,
                ],
            )
        ],
    )


def run_traced(
    agent: Agent,
    request: InvocationRequest,
    metadata: dict[str, Any],
    delegate_client_factory: delegation.ClientFactory = delegation.default_client,
) -> dict[str, Any]:
    """Run the agent under a tracer parented to the caller's span; return the artifact body.

    If the workbench sent a delegation grant (ADR-0012), the agent's context carries a
    `delegate` bound to it. An exception from the agent propagates; the executor turns it into a
    failed task.
    """
    tracing = make_tracing(service_name=agent.spec.agent_id)
    parent = TraceContextTextMapPropagator().extract(
        {META_TRACEPARENT: str(metadata.get(META_TRACEPARENT, ""))}
    )
    grant = delegation.DelegationGrant.from_metadata(metadata)
    token = otel_context.attach(parent)
    try:
        result: AgentResult = agent.run(
            request,
            RunContext(
                tracer=tracing.tracer,
                input_ref=str(metadata.get(META_INPUT_REF, "")),
                input_hash=str(metadata.get(META_INPUT_HASH, "")),
                delegate=(
                    delegation.WorkbenchDelegate(
                        grant=grant,
                        parent=request,
                        tracer=tracing.tracer,
                        client_factory=delegate_client_factory,
                    )
                    if grant is not None
                    else None
                ),
            ),
        )
    finally:
        otel_context.detach(token)
        spans = [s.to_json(indent=None) for s in tracing.memory.get_finished_spans()]
        tracing.shutdown()
    return reply_to_document(result, spans)


class AgentServerExecutor(AgentExecutor):
    def __init__(
        self,
        agent: Agent,
        delegate_client_factory: delegation.ClientFactory = delegation.default_client,
    ) -> None:
        self.agent = agent
        self.delegate_client_factory = delegate_client_factory

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        message = context.message
        if message is None:
            raise ValueError("A2A request carried no message")
        task = context.current_task or new_task_from_user_message(message)
        if not context.current_task:
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.start_work()

        inputs: list[Any] = get_data_parts(message.parts)
        if len(inputs) != 1:
            await updater.failed(
                updater.new_agent_message(
                    [new_data_part({"error": f"expected exactly one data part, got {len(inputs)}"})]
                )
            )
            return
        metadata = MessageToDict(message.metadata) if message.HasField("metadata") else {}
        try:
            request = InvocationRequest.model_validate(inputs[0])
            body = await asyncio.to_thread(
                run_traced, self.agent, request, metadata, self.delegate_client_factory
            )
        except Exception as exc:  # noqa: BLE001 — reported to the conductor, which records it
            await updater.failed(
                updater.new_agent_message(
                    [new_data_part({"error": f"{type(exc).__name__}: {exc}"})]
                )
            )
            return
        await updater.add_artifact(
            [new_data_part(body, media_type="application/json")], name=ARTIFACT_NAME
        )
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("invocations are synchronous; nothing to cancel")


def app(
    agent: Agent,
    base_url: str = "http://127.0.0.1:8100",
    delegate_client_factory: delegation.ClientFactory = delegation.default_client,
) -> Starlette:
    """`delegate_client_factory` gives the httpx client a delegation agent uses to call the
    workbench back; tests bind it to the workbench's in-process app."""
    card = agent_card(agent, base_url)
    handler = DefaultRequestHandler(
        agent_executor=AgentServerExecutor(agent, delegate_client_factory),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    return Starlette(
        routes=[*create_agent_card_routes(card), *create_jsonrpc_routes(handler, JSONRPC_PATH)]
    )


def main(build: Callable[[], Agent], argv: list[str] | None = None) -> int:
    """Console script for an agent package: `<agent> serve [--host H] [--port N]`."""
    import uvicorn

    agent = build()
    parser = argparse.ArgumentParser(prog=agent.spec.agent_id, description=agent.spec.description)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("serve", help="serve this agent over A2A")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8100)
    p.add_argument(
        "--public-url",
        default=None,
        help="the base URL the agent card advertises, if not http://HOST:PORT",
    )
    args = parser.parse_args(argv)
    base_url = args.public_url or f"http://{args.host}:{args.port}"
    uvicorn.run(app(agent, base_url), host=args.host, port=args.port)
    return 0
