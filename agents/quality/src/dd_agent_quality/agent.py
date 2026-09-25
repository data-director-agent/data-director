"""quality.reviewer: a completeness review of an existing metadata record.

The first agent that is not R3-shaped. It reads a `MetadataRecord`, retrieves nothing and calls
no model, and returns a `QualityReview` grounded on the input alone (grounding mode
`input_only`: a model *may* be called under this mode; this agent does not). Every finding is
produced by a rule in `checks.yaml` and is badged `lexical`.

This is a demonstration of the harness, not a quality framework. The criteria and weights are
hand-chosen; see the TODO in `checks.yaml`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from dd_agent_quality.classes import Finding, MetadataRecord, QualityReview, Severity
from dd_sdk import serve
from dd_sdk.agent import AgentResult, AgentSpec, Derived, RunContext
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
    Derivation,
    EvidenceItem,
    GroundingMode,
    GroundingRef,
    InvocationRequest,
    Outcome,
    OutcomeStatus,
    ReasonCode,
)
from dd_sdk.evidence import HASH_ALGORITHM, INPUT_CANONICALISATION

HERE = Path(__file__).resolve().parent
CHECKS = HERE / "checks.yaml"


def load_checks(path: Path = CHECKS) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    checks: list[dict[str, Any]] = data["checks"]
    return checks


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return len(value) > 0
    return True


class QualityReviewer:
    spec = AgentSpec(
        agent_id="quality.reviewer",
        version="0.1.0",
        description="Scores the completeness of a metadata record against fixed criteria.",
        requirement_ids=("R4.1",),
        action_class="advise",
        accepts=(ClassSchema.of(MetadataRecord),),
        grounding_mode=GroundingMode.INPUT_ONLY,
        payload=ClassSchema.of(QualityReview),
        derivations={
            "score": Derived(Derivation.LEXICAL),
            "findings.severity": Derived(Derivation.LEXICAL),
            "findings.message": Derived(Derivation.LEXICAL, recorded_in="derivation"),
        },
    )

    def __init__(self, checks: list[dict[str, Any]] | None = None) -> None:
        self.checks = checks if checks is not None else load_checks()

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        record = request.input
        assert isinstance(record, MetadataRecord)  # the conductor checked spec.accepts
        values = record.model_dump()
        if not any(_present(values.get(c["slot"])) for c in self.checks):
            return AgentResult(
                outcome=Outcome(
                    status=OutcomeStatus.ABSTAINED,
                    reason_code=ReasonCode.INSUFFICIENT_INPUT,
                    statement="The record is empty on every criterion; there is nothing to review.",
                )
            )

        ref = GroundingRef(source_id=ctx.input_ref, content_hash=ctx.input_hash)
        findings: list[Finding] = []
        total = 0.0
        earned = 0.0
        for check in self.checks:
            weight = float(check["weight"])
            total += weight
            present = _present(values.get(check["slot"]))
            if present:
                earned += weight
                severity, message = Severity.INFO, f"{check['slot']} is present."
            else:
                severity, message = Severity(check["missing_severity"]), str(check["missing"])
            findings.append(
                Finding(
                    criterion=f"{check['slot']}_present",
                    severity=severity,
                    message=message,
                    derivation=Derivation.LEXICAL,
                    grounded_on=[ref],
                )
            )
        score = round(earned / total, 3) if total else None
        missing = [f for f in findings if f.severity != Severity.INFO]
        return AgentResult(
            outcome=Outcome(
                status=OutcomeStatus.SUCCEEDED,
                statement=(
                    f"Completeness {score:.0%}: {len(missing)} of {len(findings)} criteria "
                    "unmet. Deterministic rules over the record as given; human review is required."
                    if score is not None
                    else "No criteria configured."
                ),
            ),
            payload=QualityReview(score=score, findings=findings, grounded_on=[ref]),
            evidence=[
                EvidenceItem(
                    source_id=ctx.input_ref,
                    retrieved_at=datetime.now(UTC),
                    hash_algorithm=HASH_ALGORITHM,
                    canonicalisation=INPUT_CANONICALISATION,
                    content_hash=ctx.input_hash,
                )
            ],
        )


def build() -> QualityReviewer:
    return QualityReviewer()


def main() -> int:
    """Console script: serve this agent over A2A (`dd_sdk.serve`)."""
    return serve.main(build)
