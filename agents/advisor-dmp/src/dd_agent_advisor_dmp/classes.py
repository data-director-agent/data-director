"""The input and payload classes of advisor.dmp, as Pydantic models (docs/specs/contract.md).

`schema/dmp.yaml` is the source; `ClassSchema.of` compares each model with the schema generated
from it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from dd_sdk.contract.drafting import ApprovedPlan
from dd_sdk.contract.facts import ProjectDocument, ProjectFact
from dd_sdk.contract.models import Derivation, Frozen, Grounded


class SharingCommitment(Frozen):
    output: str
    repository: str | None = None
    access: str | None = None
    licence: str | None = None


class DmpCommitments(Frozen):
    schema_class: Literal["DmpCommitments"] = "DmpCommitments"
    dmp_identifier: str | None = None
    committed_outputs: list[SharingCommitment] = Field(default_factory=list)
    planned_outputs: list[SharingCommitment] = Field(default_factory=list)
    # Filled by the conductor in a project (`GivenProjectDocuments`, `GivenProjectDecisions`).
    project_documents: list[ProjectDocument] = Field(default_factory=list)
    project_decisions: list[ProjectFact] = Field(default_factory=list)


class DmpReviewRequest(Frozen):
    schema_class: Literal["DmpReviewRequest"] = "DmpReviewRequest"
    # Filled by the conductor in a project (`GivenProjectDocuments`, `GivenProjectDecisions`,
    # `GivenProjectPlan`).
    project_documents: list[ProjectDocument] = Field(default_factory=list)
    project_decisions: list[ProjectFact] = Field(default_factory=list)
    project_plan_approved: ApprovedPlan | None = None


class SectionFinding(Frozen):
    section: str
    finding: str
    quote: str | None = None
    message: str
    reason: str | None = None


class Discrepancy(Frozen):
    output: str
    aspect: str
    committed: str | None = None
    planned: str | None = None
    message: str
    discrepancy_derivation: Derivation
    reason: str | None = None


class Reconciliation(Frozen):
    output: str
    aspect: str
    committed: str | None = None
    planned: str | None = None
    reason: str | None = None


class DmpDiscrepancies(Grounded):
    schema_class: Literal["DmpDiscrepancies"] = "DmpDiscrepancies"
    discrepancies: list[Discrepancy] = Field(default_factory=list)
    reconciled: list[Reconciliation] = Field(default_factory=list)
    section_findings: list[SectionFinding] = Field(default_factory=list)
    dropped: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    # A plan's commitments read from an attached document, for a person to confirm.
    proposed_facts: list[ProjectFact] = Field(default_factory=list)
