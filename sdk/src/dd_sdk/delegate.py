"""Delegation: an agent asks the workbench to invoke another agent (ADR-0012).

An agent in grounding mode `delegation` never calls another agent directly. It calls
`ctx.delegate(agent_id, input)`, which sends an `InvocationRequest` back to the workbench's A2A
endpoint with the grant token the conductor issued for this invocation. The workbench runs the
child as an ordinary governed invocation (policy gate, input check, linter, store), records it
against the parent, and answers with the child envelope as the JSON the conductor stored.

`Delegated` carries the envelope and, computed here rather than by the agent, the grounding
reference and evidence item that cite it (`invocation:<child_id>`, `dd-envelope-json-v1`), so
a relayed reply cannot mis-cite what it relays.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from a2a.client import ClientConfig, create_client
from a2a.helpers import get_data_parts, get_text_parts, new_data_part
from a2a.types import Message, Role, SendMessageRequest, TaskState
from opentelemetry.trace import Tracer
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from dd_sdk.agent import DelegationGrant
from dd_sdk.contract.models import (
    Envelope,
    EvidenceItem,
    Frozen,
    GroundingRef,
    InvocationRequest,
    invocation_source_id,
    new_invocation_id,
    to_document,
)
from dd_sdk.evidence import ENVELOPE_CANONICALISATION, HASH_ALGORITHM, envelope_hash
from dd_sdk.tracing import ATTR_CONTENT_HASH, ATTR_SOURCE_ID, delegate_span
from dd_sdk.wire import (
    ENVELOPE_JSON_ARTIFACT,
    META_DELEGATION_TOKEN,
    META_TRACEPARENT,
)

DEFAULT_TIMEOUT_S = 60.0

ClientFactory = Callable[[str, float], httpx.AsyncClient]


class DelegationRefused(Exception):
    """The workbench would not run the delegated invocation, or could not be reached.

    A refusal is not a child outcome: a child that ran and failed comes back as a `Delegated`
    whose envelope says so. This is raised when no child envelope exists at all.
    """


@dataclass(frozen=True)
class Delegated:
    envelope: Envelope
    ref: GroundingRef
    evidence: EvidenceItem


def default_client(base_url: str, timeout_s: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=base_url, timeout=timeout_s)


@dataclass
class WorkbenchDelegate:
    """The `Delegate` `dd_sdk.serve` hands a delegation agent, bound to one grant."""

    grant: DelegationGrant
    parent: InvocationRequest
    tracer: Tracer
    timeout_s: float = DEFAULT_TIMEOUT_S
    client_factory: ClientFactory = default_client

    def __call__(self, agent_id: str, input: Frozen) -> Delegated:
        request = InvocationRequest(
            agent_id=agent_id,
            policy_bundle_ref=self.parent.policy_bundle_ref,  # the conductor applies the grant's
            conversation_id=self.parent.conversation_id,
            input=input,
        )
        with delegate_span(self.tracer, agent_id) as span:
            carrier: dict[str, str] = {}
            TraceContextTextMapPropagator().inject(carrier)
            metadata = {
                META_DELEGATION_TOKEN: self.grant.token,
                META_TRACEPARENT: carrier.get(META_TRACEPARENT, ""),
            }
            try:
                response = asyncio.run(self._send(to_document(request), metadata))
            except (httpx.HTTPError, TimeoutError) as exc:
                raise DelegationRefused(f"workbench at {self.grant.url}: {exc!r}") from exc
            document = _envelope_document(response)
            content_hash = envelope_hash(document)
            source_id = invocation_source_id(str(document.get("invocation_id")))
            span.set_attribute(ATTR_SOURCE_ID, source_id)
            span.set_attribute(ATTR_CONTENT_HASH, content_hash)
        try:
            envelope = Envelope.model_validate(document)
        except ValueError as exc:
            raise DelegationRefused(f"the workbench returned a malformed envelope: {exc}") from exc
        return Delegated(
            envelope=envelope,
            ref=GroundingRef(source_id=source_id, content_hash=content_hash),
            evidence=EvidenceItem(
                source_id=source_id,
                retrieved_at=datetime.now(UTC),
                hash_algorithm=HASH_ALGORITHM,
                canonicalisation=ENVELOPE_CANONICALISATION,
                content_hash=content_hash,
            ),
        )

    async def _send(self, request_doc: dict[str, Any], metadata: dict[str, str]) -> Any:
        async with asyncio.timeout(self.timeout_s):
            async with self.client_factory(self.grant.url, self.timeout_s) as hc:
                client = await create_client(
                    agent=self.grant.url,
                    client_config=ClientConfig(streaming=False, httpx_client=hc),
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


def _envelope_document(response: Any) -> dict[str, Any]:
    task = getattr(response, "task", None)
    if task is None:
        raise DelegationRefused("the workbench returned no task")
    if task.status.state != TaskState.TASK_STATE_COMPLETED:
        detail = _failure_detail(task) or TaskState.Name(task.status.state)
        raise DelegationRefused(f"the workbench refused the delegation: {detail}")
    for artifact in task.artifacts:
        if artifact.name == ENVELOPE_JSON_ARTIFACT:
            texts = get_text_parts(artifact.parts)
            if len(texts) == 1:
                document: dict[str, Any] = json.loads(texts[0])
                return document
    raise DelegationRefused(f"the workbench returned no {ENVELOPE_JSON_ARTIFACT} artifact")


def _failure_detail(task: Any) -> str | None:
    message = task.status.message if task.status.HasField("message") else None
    if message is None:
        return None
    for part in get_data_parts(message.parts):
        if isinstance(part, dict) and "error" in part:
            return str(part["error"])
    text = get_text_parts(message.parts)
    return " ".join(text) if text else None
