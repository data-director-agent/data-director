"""A2A JSON-RPC binding (ADR-0001). The only importer of `a2a` (ADR-0006).

The request is an `InvocationRequest` carried as a data part of the user message; the response
is the `Envelope` carried as a data part of the task's single artifact. `a2a-sdk` 1.x is
protobuf-based, so documents cross as `google.protobuf.Struct` values via the SDK helpers.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from a2a.helpers import (
    get_data_parts,
    new_data_part,
    new_task_from_user_message,
    new_text_part,
)
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from google.protobuf.json_format import MessageToDict
from starlette.routing import BaseRoute

from dd_sdk.contract.models import InvocationRequest
from dd_sdk.contract.validate import ContractViolation
from dd_sdk.wire import ENVELOPE_JSON_ARTIFACT, META_DELEGATION_TOKEN, META_TRACEPARENT
from workbench.conductor import Conductor, UnknownAgent

PROTOCOL_VERSION = "1.0"


def agent_card(conductor: Conductor, base_url: str) -> AgentCard:
    skills = [
        AgentSkill(
            id=entry["agent_id"],
            name=entry["agent_id"],
            description=entry["description"],
            tags=[
                "data-director",
                f"grounding:{entry['grounding_mode']}",
                *(f"accepts:{name}" for name in entry["accepts"]),
                *entry["requirement_ids"],
            ],
        )
        for entry in conductor.registry.manifest()
    ]
    return AgentCard(
        name="Data Director Workbench",
        description=(
            "Reference workbench for the RDA Data Director Blueprint. Send an InvocationRequest "
            "as a data part; receive an Envelope as a data artifact. Every envelope requires "
            "human review."
        ),
        version="0.1.0",
        default_input_modes=["application/json"],
        default_output_modes=["application/json"],
        capabilities=AgentCapabilities(streaming=False),
        supported_interfaces=[
            AgentInterface(
                protocol_binding="JSONRPC",
                url=base_url.rstrip("/") + "/a2a",
                protocol_version=PROTOCOL_VERSION,
            )
        ],
        skills=skills,
    )


class WorkbenchExecutor(AgentExecutor):
    def __init__(self, conductor: Conductor) -> None:
        self.conductor = conductor

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
        token = metadata.get(META_DELEGATION_TOKEN)
        try:
            request = InvocationRequest.model_validate(inputs[0])
            if token:
                # A delegation agent calling back under its grant (ADR-0012).
                envelope = await asyncio.to_thread(
                    self.conductor.invoke_delegated,
                    request,
                    str(token),
                    str(metadata.get(META_TRACEPARENT, "")),
                )
            else:
                envelope = await asyncio.to_thread(self.conductor.invoke, request)
        except (ContractViolation, ValueError, UnknownAgent) as exc:
            await updater.failed(updater.new_agent_message([new_data_part({"error": str(exc)})]))
            return
        document = envelope.to_document()
        await updater.add_artifact(
            [new_data_part(document, media_type="application/json")], name="envelope"
        )
        if token:
            # The stored JSON, as text, so the caller's hash of it matches the conductor's.
            await updater.add_artifact(
                [new_text_part(json.dumps(document))], name=ENVELOPE_JSON_ARTIFACT
            )
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("invocations are synchronous; nothing to cancel")


def a2a_routes(conductor: Conductor, base_url: str) -> tuple[AgentCard, list[BaseRoute]]:
    card = agent_card(conductor, base_url)
    handler = DefaultRequestHandler(
        agent_executor=WorkbenchExecutor(conductor), task_store=InMemoryTaskStore(), agent_card=card
    )
    routes: list[BaseRoute] = [
        *create_agent_card_routes(card),
        *create_jsonrpc_routes(handler, "/a2a"),
    ]
    return card, routes
