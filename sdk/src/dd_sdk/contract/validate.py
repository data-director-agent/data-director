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

from dd_sdk.contract.models import GroundingMode, OutcomeStatus
from dd_sdk.evidence import CANONICALISATIONS, INPUT_CANONICALISATION

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
    errors: list[ValidationError] = sorted(_validator(path).iter_errors(document), key=str)
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errors]


def conditional_errors(envelope: dict[str, Any]) -> list[str]:
    """The rules the LinkML source states in prose. Applied to the JSON document, not the model,
    so they hold for documents produced outside Python too."""
    errors: list[str] = []
    outcome = envelope.get("outcome") or {}
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
    errors.extend(grounding_errors(envelope))
    return errors


def grounding_errors(envelope: dict[str, Any]) -> list[str]:
    """Self-consistency between grounding_mode, payload and evidence (ADR-0008, ADR-0009).

    Agreement with the trace is the linter's job; these rules hold on the document alone.
    """
    errors: list[str] = []
    mode = envelope.get("grounding_mode")
    status = (envelope.get("outcome") or {}).get("status")
    payload = envelope.get("payload")
    evidence: list[dict[str, Any]] = envelope.get("evidence") or []

    if payload is not None:
        if "schema_class" not in payload:
            errors.append("payload lacks schema_class")
        if "grounded_on" not in payload:
            errors.append("payload lacks grounded_on: every payload class mixes in Grounded")

    for ev in evidence:
        name = ev.get("canonicalisation")
        if name not in CANONICALISATIONS:
            errors.append(f"evidence {ev.get('source_id')!r}: unknown canonicalisation {name!r}")

    if status != OutcomeStatus.SUCCEEDED:
        return errors
    if mode == GroundingMode.RETRIEVAL:
        if payload is not None and not payload.get("grounded_on"):
            errors.append("grounding_mode=retrieval and succeeded requires non-empty grounded_on")
    elif mode in (GroundingMode.INPUT_ONLY, GroundingMode.NONE):
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
        if len(cites_input) != len(evidence):
            errors.append(f"grounding_mode={mode} permits no evidence other than the input")
    return errors


def validate_envelope(document: dict[str, Any]) -> None:
    errors = _schema_errors(ENVELOPE_SCHEMA, document) + conditional_errors(document)
    if errors:
        raise ContractViolation("Envelope", errors)


def validate_request(document: dict[str, Any]) -> None:
    errors = _schema_errors(REQUEST_SCHEMA, document)
    if errors:
        raise ContractViolation("InvocationRequest", errors)
