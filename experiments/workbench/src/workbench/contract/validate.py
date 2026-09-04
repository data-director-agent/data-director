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

from workbench.contract.models import OutcomeStatus

SCHEMA_DIR = Path(__file__).resolve().parents[3] / "schema" / "generated"
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
    return errors


def validate_envelope(document: dict[str, Any]) -> None:
    errors = _schema_errors(ENVELOPE_SCHEMA, document) + conditional_errors(document)
    if errors:
        raise ContractViolation("Envelope", errors)


def validate_request(document: dict[str, Any]) -> None:
    errors = _schema_errors(REQUEST_SCHEMA, document)
    if errors:
        raise ContractViolation("InvocationRequest", errors)
