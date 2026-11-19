"""advisor.quality: a completeness review of an existing metadata record.

The first agent that is not standards-advisor-shaped. It reads a `MetadataRecord`, retrieves
nothing, and returns a `QualityReview` grounded on the input alone (grounding mode `input_only`).
Every finding and the score are produced by a rule in `checks.yaml` and are badged `lexical`. A
summariser (`dd_sdk.summary`) then writes a short summary beside them: a model's by default, the
rules' own with `DD_QUALITY_SUMMARISER=template` (`factory.py`). It changes no finding.

This is a demonstration of the harness, not a quality framework. The criteria and weights are
hand-chosen; see `checks.yaml` and #18.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from dd_agent_advisor_quality.classes import Finding, MetadataRecord, QualityReview, Severity
from dd_sdk import summary
from dd_sdk.agent import (
    AgentResult,
    AgentSpec,
    Derived,
    RunContext,
    abstain,
    input_evidence,
    input_ref,
)
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
    Derivation,
    GroundingMode,
    InvocationRequest,
    Outcome,
    OutcomeStatus,
    ReasonCode,
)

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
        agent_id="advisor.quality",
        title="Metadata Reviewer",
        icon="🔍",
        version="0.1.0",
        description="Scores the completeness of a metadata record against fixed criteria.",
        action_class="advise",
        accepts=(ClassSchema.of(MetadataRecord),),
        grounding_mode=GroundingMode.INPUT_ONLY,
        payload=ClassSchema.of(QualityReview),
        derivations={
            "score": Derived(Derivation.LEXICAL),
            "findings.severity": Derived(Derivation.LEXICAL),
            "findings.message": Derived(Derivation.LEXICAL, recorded_in="derivation"),
            "summary": Derived(Derivation.MODEL, recorded_in="summary_derivation"),
        },
        serves=("deposit.validate",),
    )

    def __init__(
        self,
        checks: list[dict[str, Any]] | None = None,
        summariser: summary.Summariser | None = None,
    ) -> None:
        self.checks = checks if checks is not None else load_checks()
        self.summariser = summariser or summary.TemplateSummariser()

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        record = request.input
        assert isinstance(record, MetadataRecord)  # the conductor checked spec.accepts
        values = record.model_dump()
        if not any(_present(values.get(c["slot"])) for c in self.checks):
            return abstain(
                ReasonCode.INSUFFICIENT_INPUT,
                "The record is empty on every criterion; there is nothing to review.",
            )

        ref = input_ref(ctx)
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
        statement = (
            f"Completeness {score:.0%}: {len(missing)} of {len(findings)} criteria "
            "unmet. Deterministic rules over the record as given; human review is required."
            if score is not None
            else "No criteria configured."
        )
        told = summary.Findings(
            {
                "record": record.model_dump(mode="json", exclude={"schema_class"}),
                "score": score,
                "findings": [
                    {"criterion": f.criterion, "severity": f.severity.value, "message": f.message}
                    for f in findings
                ],
            },
            " ".join(f.message for f in missing) or "Every criterion is met.",
        )
        summarised, explanation = summary.summarise(self.summariser, told, ctx)
        result = AgentResult(
            outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement=statement),
            payload=QualityReview(
                score=score,
                findings=findings,
                summary=summarised.text,
                summary_derivation=summarised.derivation,
                grounded_on=[ref],
            ),
            evidence=[input_evidence(ctx)],
        )
        return summary.with_calls(result, self.summariser.model_id, explanation)
