"""Validate documents against the generated JSON Schema, plus the conditional rules.

JSON Schema validation fails loudly: a contract violation is a programmer or configuration
error, never a content outcome. The conditional rules (which the LinkML source states in
prose and gen-json-schema cannot emit) are applied here so that an envelope's outcome and its
supporting fields cannot disagree.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator
from jsonschema.exceptions import ValidationError

from dd_sdk.contract.models import TOOL_SOURCE_PREFIX, GroundingMode, OutcomeStatus
from dd_sdk.evidence import (
    CANONICALISATIONS,
    ENVELOPE_CANONICALISATION,
    INPUT_CANONICALISATION,
)

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schema" / "generated"
ENVELOPE_SCHEMA = SCHEMA_DIR / "envelope.schema.json"
REQUEST_SCHEMA = SCHEMA_DIR / "invocation_request.schema.json"


class ContractViolation(Exception):
    """A document does not conform to the contract. Carries every violation found."""

    def __init__(self, document_kind: str, messages: list[str]) -> None:
        self.document_kind = document_kind
        self.messages = messages
        joined = "\n  - ".join(messages)
        super().__init__(f"{document_kind} violates the contract:\n  - {joined}")


@cache
def _validator(path: Path) -> Draft7Validator:
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft7Validator.check_schema(schema)
    return Draft7Validator(schema)


def _schema_errors(path: Path, document: dict[str, Any]) -> list[str]:
    # Sorted by the message, not by `str(error)`, which pretty-prints the whole schema each time.
    errors: list[ValidationError] = list(_validator(path).iter_errors(document))
    return sorted(
        f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errors
    )


def _object(value: Any) -> dict[str, Any]:
    """`value` if it is a JSON object, else an empty one. The schema reports a value of the
    wrong type; the conditional rules read past it rather than raise."""
    return value if isinstance(value, dict) else {}


def _objects(value: Any) -> list[dict[str, Any]]:
    """The objects in `value` if it is a JSON array, else none; as `_object`."""
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def conditional_errors(envelope: dict[str, Any]) -> list[str]:
    """The rules the LinkML source states in prose. Applied to the JSON document, not the model,
    so they hold for documents produced outside Python too. A document of any shape gives a list
    of errors, never an exception: a value of the wrong type is the schema's to report."""
    errors: list[str] = []
    outcome = _object(envelope.get("outcome"))
    status = outcome.get("status")
    has_problem = envelope.get("problem") is not None
    has_payload = envelope.get("payload") is not None
    has_reason = outcome.get("reason_code") is not None

    if status in (OutcomeStatus.FAILED, OutcomeStatus.SUSPENDED) and not has_problem:
        errors.append(f"outcome.status={status} requires problem (RFC 9457)")
    if status in (OutcomeStatus.ABSTAINED, OutcomeStatus.REFERRED) and not has_reason:
        errors.append(f"outcome.status={status} requires outcome.reason_code")
    if status == OutcomeStatus.REFERRED and not outcome.get("referred_to"):
        errors.append("outcome.status=referred requires outcome.referred_to")
    if status == OutcomeStatus.SUCCEEDED and not has_payload:
        errors.append("outcome.status=succeeded requires payload")
    if status != OutcomeStatus.SUCCEEDED and has_payload:
        errors.append(f"outcome.status={status} must not carry a payload")
    if status not in (OutcomeStatus.FAILED, OutcomeStatus.SUSPENDED) and has_problem:
        errors.append(f"outcome.status={status} must not carry a problem")
    if has_payload != ("payload_schema" in envelope):
        errors.append(
            "a payload requires payload_schema, and payload_schema a payload "
            "(docs/specs/contract.md)"
        )
    errors.extend(grounding_errors(envelope))
    return errors


def grounding_errors(envelope: dict[str, Any]) -> list[str]:
    """Self-consistency between grounding_mode, payload and evidence (docs/specs/grounding.md).

    Agreement with the trace is the linter's job; these rules hold on the document alone.
    """
    errors: list[str] = []
    mode = envelope.get("grounding_mode")
    status = _object(envelope.get("outcome")).get("status")
    payload = envelope.get("payload")
    evidence = _objects(envelope.get("evidence"))

    if isinstance(payload, dict):
        if "schema_class" not in payload:
            errors.append("payload lacks schema_class")
        if "grounded_on" not in payload:
            errors.append("payload lacks grounded_on: every payload class mixes in Grounded")

    for ev in evidence:
        name = ev.get("canonicalisation")
        if not isinstance(name, str) or name not in CANONICALISATIONS:
            errors.append(f"evidence {ev.get('source_id')!r}: unknown canonicalisation {name!r}")
    errors.extend(_tool_errors(envelope, evidence))

    if status != OutcomeStatus.SUCCEEDED:
        return errors
    if mode == GroundingMode.RETRIEVAL:
        if isinstance(payload, dict) and not payload.get("grounded_on"):
            errors.append("grounding_mode=retrieval and succeeded requires non-empty grounded_on")
    elif mode in (GroundingMode.INPUT_ONLY, GroundingMode.NONE, GroundingMode.DELEGATION):
        errors.extend(_input_grounding_errors(envelope, mode, evidence))
    return errors


def _tool_errors(envelope: dict[str, Any], evidence: list[dict[str, Any]]) -> list[str]:
    """Each item of evidence naming a `tool:` source that is not a record the conductor kept from
    the tool gateway under the same canonicalisation (docs/specs/grounding.md, invariant 15)."""
    # A list, not a set: a hash of the wrong type may not be hashable.
    recorded = [
        (r.get("source_id"), r.get("content_hash"), r.get("canonicalisation"))
        for r in _objects(envelope.get("tool_retrievals"))
    ]
    return [
        f"evidence {ev.get('source_id')!r} names a tool source the gateway did not return"
        for ev in evidence
        if str(ev.get("source_id", "")).startswith(TOOL_SOURCE_PREFIX)
        and (ev.get("source_id"), ev.get("content_hash"), ev.get("canonicalisation"))
        not in recorded
    ]


def _input_grounding_errors(
    envelope: dict[str, Any], mode: Any, evidence: list[dict[str, Any]]
) -> list[str]:
    """The rules for a succeeded envelope whose grounding_mode cites the input: input_only, none
    or delegation."""
    errors: list[str] = []
    cites_input = [
        ev
        for ev in evidence
        if ev.get("canonicalisation") == INPUT_CANONICALISATION
        and str(ev.get("source_id", "")).startswith("input:")
    ]
    if not cites_input:
        errors.append(
            f"grounding_mode={mode} and succeeded requires evidence citing the input "
            f"({INPUT_CANONICALISATION}, source_id input:<invocation_id>)"
        )
    if mode == GroundingMode.DELEGATION:
        errors.extend(_delegation_errors(envelope, evidence, cites_input))
    elif len(cites_input) != len(evidence):
        errors.append(f"grounding_mode={mode} permits no evidence other than the input")
    return errors


def _delegation_errors(
    envelope: dict[str, Any], evidence: list[dict[str, Any]], cites_input: list[dict[str, Any]]
) -> list[str]:
    """Each item of evidence under grounding_mode=delegation that is neither the input nor a
    recorded delegation."""
    errors: list[str] = []
    # A list, not a set: a hash of the wrong type may not be hashable.
    recorded = [
        (f"invocation:{d.get('delegated_invocation_id')}", d.get("content_hash"))
        for d in _objects(envelope.get("delegations"))
    ]
    for ev in evidence:
        if ev in cites_input:
            continue
        if (
            ev.get("canonicalisation") != ENVELOPE_CANONICALISATION
            or (
                ev.get("source_id"),
                ev.get("content_hash"),
            )
            not in recorded
        ):
            errors.append(
                f"grounding_mode=delegation: evidence {ev.get('source_id')!r} is neither "
                f"the input nor a recorded delegation ({ENVELOPE_CANONICALISATION})"
            )
    return errors


def validate_envelope(document: dict[str, Any]) -> None:
    errors = _schema_errors(ENVELOPE_SCHEMA, document) + conditional_errors(document)
    if errors:
        raise ContractViolation("Envelope", errors)


def validate_request(document: dict[str, Any]) -> None:
    errors = _schema_errors(REQUEST_SCHEMA, document)
    if errors:
        raise ContractViolation("InvocationRequest", errors)
