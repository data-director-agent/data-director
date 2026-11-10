"""Serve one agent over A2A (docs/specs/agents.md). With `dd_sdk.delegate`, one of the SDK's two
importers of `a2a` (docs/specs/orchestration.md).

`app(agent, base_url)` is a Starlette application with the agent card at
`/.well-known/agent-card.json` and the JSON-RPC binding at `/a2a`. `main(build)` is the console
script every agent package exposes (`<agent> serve --port N`); with `--reload`, for development, it
restarts the agent whenever a file in its package or in the SDK changes, its prompts included.

Per request the server starts an isolated tracer, parents it to the `traceparent` the harness
sent, runs the agent in a worker thread, and returns the result with the spans the agent emitted.
It does no governance: the harness's conductor applies the policy gate, the input check and the
grounding linter to whatever comes back.

`request_handler` is the A2A request handler this server and the harness's
(`dd_harness.transport.a2a`) both use. It answers `message/send` alone: A2A's task methods (get,
list, cancel, subscribe) are refused, a message may not name an earlier task, and a task is
forgotten once it ends. Callers are not authenticated to the SDK's task store, so a stored task
would otherwise be readable by any caller, with the request, the reply and the message metadata (a
delegation grant included) (docs/specs/transport.md).
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import os
import sys
from collections.abc import AsyncGenerator, Callable
from pathlib import Path
from typing import Any

from a2a.helpers import get_data_parts, new_data_part, new_task_from_user_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.context import ServerCallContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentExtension,
    AgentInterface,
    AgentSkill,
    CancelTaskRequest,
    GetTaskRequest,
    ListTasksRequest,
    ListTasksResponse,
    Message,
    SendMessageRequest,
    SubscribeToTaskRequest,
    Task,
    TaskState,
)
from a2a.utils.errors import InvalidParamsError, UnsupportedOperationError
from google.protobuf.json_format import MessageToDict
from opentelemetry import context as otel_context
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from starlette.applications import Starlette

from dd_sdk import delegate as delegation
from dd_sdk.agent import Agent, AgentResult, RunContext, describe, typed_request
from dd_sdk.contract.models import InvocationRequest
from dd_sdk.credentials import ConfigError
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
# The exit status for a configuration error. systemd units do not restart on it
# (`RestartPreventExitStatus=`): the agent would only stop again.
EXIT_CONFIG = 2


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
            # An agent answers once, with its finished envelope; the conductor checks the whole
            # envelope before anything is shown. TODO(#159) covers streaming replies to the shell.
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

    If the harness sent a delegation grant (docs/specs/orchestration.md), the agent's context
    carries a `delegate` bound to it. An exception from the agent propagates; the executor turns it
    into a failed task.
    """
    tracing = make_tracing(service_name=agent.spec.agent_id)
    parent = TraceContextTextMapPropagator().extract(
        {META_TRACEPARENT: str(metadata.get(META_TRACEPARENT, ""))}
    )
    grant = delegation.DelegationGrant.from_metadata(metadata)
    token = otel_context.attach(parent)
    try:
        result: AgentResult = agent.run(
            typed_request(agent.spec, request),
            RunContext(
                tracer=tracing.tracer,
                input_ref=str(metadata.get(META_INPUT_REF, "")),
                input_hash=str(metadata.get(META_INPUT_HASH, "")),
                delegate=(
                    delegation.HarnessDelegate(
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


# A task in one of these states has ended: nothing further is sent for it.
ENDED = frozenset(
    {
        TaskState.TASK_STATE_COMPLETED,
        TaskState.TASK_STATE_FAILED,
        TaskState.TASK_STATE_CANCELED,
        TaskState.TASK_STATE_REJECTED,
    }
)
ONE_SHOT = "this server answers message/send alone; it keeps no task to get, list, cancel or follow"


class TransientTaskStore(InMemoryTaskStore):
    """Holds a task only while it runs, and forgets it once it has ended."""

    async def save(self, task: Task, context: ServerCallContext) -> None:
        if task.status.state in ENDED:
            await self.delete(task.id, context)
        else:
            await super().save(task, context)


class OneShotRequestHandler(DefaultRequestHandler):
    """`message/send` and nothing else, each message a task of its own (`ONE_SHOT`)."""

    async def on_message_send(
        self, params: SendMessageRequest, context: ServerCallContext
    ) -> Message | Task:
        if params.message.task_id:
            raise InvalidParamsError(message="a message may not name an earlier task")
        answered: Message | Task = await super().on_message_send(params, context)
        return answered

    async def on_get_task(self, params: GetTaskRequest, context: ServerCallContext) -> Task | None:
        raise UnsupportedOperationError(message=ONE_SHOT)

    async def on_list_tasks(
        self, params: ListTasksRequest, context: ServerCallContext
    ) -> ListTasksResponse:
        raise UnsupportedOperationError(message=ONE_SHOT)

    async def on_cancel_task(
        self, params: CancelTaskRequest, context: ServerCallContext
    ) -> Task | None:
        raise UnsupportedOperationError(message=ONE_SHOT)

    async def on_subscribe_to_task(
        self, params: SubscribeToTaskRequest, context: ServerCallContext
    ) -> AsyncGenerator[Any]:
        # An async generator, as the base's is, which the dispatcher iterates: it yields nothing.
        nothing: tuple[Any, ...] = ()
        for event in nothing:
            yield event
        raise UnsupportedOperationError(message=ONE_SHOT)


def request_handler(executor: AgentExecutor, card: AgentCard) -> DefaultRequestHandler:
    """The A2A request handler for `executor` behind `card` (`OneShotRequestHandler`)."""
    return OneShotRequestHandler(
        agent_executor=executor, task_store=TransientTaskStore(), agent_card=card
    )


def app(
    agent: Agent,
    base_url: str = "http://127.0.0.1:8100",
    delegate_client_factory: delegation.ClientFactory = delegation.default_client,
) -> Starlette:
    """`delegate_client_factory` gives the httpx client a delegation agent uses to call the
    harness back; tests bind it to the harness's in-process app."""
    card = agent_card(agent, base_url)
    handler = request_handler(AgentServerExecutor(agent, delegate_client_factory), card)
    return Starlette(
        routes=[*create_agent_card_routes(card), *create_jsonrpc_routes(handler, JSONRPC_PATH)]
    )


# How `--reload` hands the agent to the reloaded worker, which uvicorn starts from an import string.
BUILD_ENV = "DD_SERVE_BUILD"
BASE_URL_ENV = "DD_SERVE_BASE_URL"
# The files whose change restarts an agent: its code, its prompts and its configuration.
RELOAD_INCLUDES = ["*.py", "*.md", "*.yaml", "*.yml", "*.json"]


def reloadable_app() -> Starlette:
    """The application `main` serves under `--reload`, built afresh in each reloaded worker from
    the `build` that `BUILD_ENV` names (`module:function`)."""
    module, _, name = os.environ[BUILD_ENV].partition(":")
    build: Callable[[], Agent] = getattr(importlib.import_module(module), name)
    return app(build(), os.environ[BASE_URL_ENV])


def _package_dir(build: Callable[[], Agent]) -> str:
    return str(Path(importlib.import_module(build.__module__).__file__ or "").parent)


def main(build: Callable[[], Agent], argv: list[str] | None = None) -> int:
    """Console script for an agent package: `<agent> serve [--host H] [--port N]`.

    A `ConfigError` from `build` is printed as one line and the script exits with `EXIT_CONFIG`,
    before any port is opened."""
    import uvicorn

    try:
        agent = build()
    except ConfigError as exc:
        sys.stderr.write(f"{Path(sys.argv[0]).name}: {exc}\n")
        return EXIT_CONFIG
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
    p.add_argument(
        "--reload",
        action="store_true",
        help="restart when the agent's files change; for development",
    )
    args = parser.parse_args(argv)
    base_url = args.public_url or f"http://{args.host}:{args.port}"
    if not args.reload:
        uvicorn.run(app(agent, base_url), host=args.host, port=args.port)
        return 0
    os.environ[BUILD_ENV] = f"{build.__module__}:{build.__qualname__}"
    os.environ[BASE_URL_ENV] = base_url
    uvicorn.run(
        f"{__name__}:reloadable_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=True,
        reload_dirs=[_package_dir(build), str(Path(__file__).parent)],
        reload_includes=RELOAD_INCLUDES,
    )
    return 0
