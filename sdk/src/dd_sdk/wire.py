"""How an `AgentResult` and an `AgentSpec` cross A2A between the workbench and an agent (ADR-0011).

Workbench → agent: one A2A user message. Its single data part is the `InvocationRequest`
document; its `metadata` carries `dd.input_ref`, `dd.input_hash` and the W3C `traceparent` of the
conductor's `invoke_agent` span.

Agent → workbench: a completed task whose single artifact, named `agent-result`, has one data
part `{"result": <AgentResult document>, "spans": [<span JSON>, ...]}`. Each span is the string
`ReadableSpan.to_json` produced, carried as a string so protobuf's `Struct` (which has only
floating-point numbers) cannot alter it. The agent never returns an `Envelope`: the conductor
builds that.

The agent card declares the extension `EXTENSION_URI`, whose `params` are `describe(spec)`.

Both sides import this module, so the keys are spelt in one place.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import TypeAdapter

from dd_sdk.agent import AgentResult
from dd_sdk.contract.models import EvidenceItem, Grounded, Outcome, Payload, to_document

# TODO: a persistent identifier for the extension. The w3id namespace the problem types use is
# not yet registered either (contract/problem.py).
EXTENSION_URI = "https://w3id.org/data-director/a2a/agent-spec/v0"

META_INPUT_REF = "dd.input_ref"
META_INPUT_HASH = "dd.input_hash"
META_TRACEPARENT = "traceparent"

ARTIFACT_NAME = "agent-result"
JSONRPC_PATH = "/a2a"
CARD_PATH = "/.well-known/agent-card.json"

_payload_adapter: TypeAdapter[Any] = TypeAdapter(Payload)


class WireError(Exception):
    """A document on the wire does not have the shape this module writes."""


def result_to_document(result: AgentResult) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "outcome": to_document(result.outcome),
        "evidence": [to_document(e) for e in result.evidence],
    }
    if result.payload is not None:
        doc["payload"] = to_document(result.payload)
    for key in ("model_id", "input_tokens", "output_tokens"):
        value = getattr(result, key)
        if value is not None:
            doc[key] = value
    return doc


def result_from_document(doc: dict[str, Any], spans: list[str]) -> AgentResult:
    """Rebuild an `AgentResult`, parsing the payload by its `schema_class` against the contract.

    Raises `WireError` for a document the contract does not admit.
    """
    try:
        payload: Grounded | None = (
            _payload_adapter.validate_python(doc["payload"]) if "payload" in doc else None
        )
        return AgentResult(
            outcome=Outcome.model_validate(doc["outcome"]),
            payload=payload,
            evidence=[EvidenceItem.model_validate(e) for e in doc.get("evidence", [])],
            model_id=doc.get("model_id"),
            input_tokens=_int_or_none(doc.get("input_tokens")),
            output_tokens=_int_or_none(doc.get("output_tokens")),
            spans=tuple(json.loads(s) for s in spans),
        )
    except (KeyError, ValueError, TypeError) as exc:  # pydantic.ValidationError is a ValueError
        raise WireError(f"agent result does not conform to the contract: {exc}") from exc


def _int_or_none(value: Any) -> int | None:
    # Struct carries every number as a double; token counts are integers.
    return None if value is None else int(value)
