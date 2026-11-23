"""A Data Management Plan's storage question offers the institution's storage services from the
deployment's profile, by rule, beside the question and never in the plan (docs/specs/drafting.md,
invariant 7)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from dd_agent_advisor_documentation import storage
from dd_agent_advisor_documentation.agent import DocumentationEditor
from dd_agent_advisor_documentation.storage import HEADING
from dd_harness.conductor import Conductor
from dd_harness.testing import PERMISSIVE, TEST_PRINCIPAL, make_conductor, request
from dd_sdk.contract.facts import FactKind, ProjectFact, SensitivityDecision
from dd_sdk.contract.models import (
    Derivation,
    Document,
    DocumentKind,
    DocumentQuestion,
    DraftRequest,
    OutcomeStatus,
)
from dd_sdk.contract.questions import SUGGESTED_FROM_INSTITUTION

CLOUD = {"storage_id": "cloud-drive", "storage_name": "Cloud drive", "storage_backup": "Versioned"}
FILESTORE = {
    "storage_id": "research-filestore",
    "storage_name": "Research filestore",
    "approved_for_sensitive": True,
    "storage_backup": "Nightly snapshots replicated to a second site",
}
SENSITIVE = ProjectFact(
    fact_kind=FactKind.SENSITIVITY,
    fact_subject="participants",
    sensitive_subject="Interview recordings",
    sensitivity_decision=SensitivityDecision.WITHHOLD,
)


def conductor(tmp_path: Path, storage: list[dict[str, Any]] | None) -> Conductor:
    data = yaml.safe_load(PERMISSIVE.read_text())
    if storage is not None:
        data["institution_storage"] = storage
    profile = tmp_path / "profile.yaml"
    profile.write_text(yaml.safe_dump(data))
    return make_conductor(tmp_path / "runs", DocumentationEditor(), profile=profile)


def plan(held: Conductor, **update: Any) -> Document:
    given = DraftRequest.model_validate({"document_kind": DocumentKind.DMP, **update})
    env = held.invoke(request("advisor.documentation", given), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert held.grounding_reports[env.invocation_id].passed
    return env.payload_as(Document)


def storage_question(document: Document) -> DocumentQuestion:
    return next(q for q in document.document_questions if q.gap_section == HEADING)


def test_the_storage_question_offers_the_profiles_services_and_the_plan_holds_none(
    tmp_path: Path,
) -> None:
    drafted = plan(conductor(tmp_path, [CLOUD, FILESTORE]))
    asked = storage_question(drafted)
    assert asked.suggestion_derivation == Derivation.TEMPLATE
    assert asked.suggested_from == SUGGESTED_FROM_INSTITUTION
    assert asked.suggested_answer is not None
    for name in ("Cloud drive", "Research filestore"):
        assert name in asked.suggested_answer
        assert name not in drafted.document_text
    # Only the storage question is offered them.
    others = [q for q in drafted.document_questions if q is not asked]
    assert all(q.suggested_from != SUGGESTED_FROM_INSTITUTION for q in others)


def test_with_sensitive_data_the_approved_service_comes_first(tmp_path: Path) -> None:
    asked = storage_question(
        plan(conductor(tmp_path, [CLOUD, FILESTORE]), project_decisions=[SENSITIVE])
    )
    assert asked.suggested_answer is not None
    offered = asked.suggested_answer
    assert offered.index("Research filestore") < offered.index("Cloud drive")


def test_without_storage_in_the_profile_nothing_is_offered(tmp_path: Path) -> None:
    asked = storage_question(plan(conductor(tmp_path, None)))
    assert asked.suggested_from != SUGGESTED_FROM_INSTITUTION


def test_storage_a_caller_sends_is_replaced_by_the_profiles(tmp_path: Path) -> None:
    forged = {**FILESTORE, "storage_id": "usb-stick", "storage_name": "My USB stick"}
    sent = {"profile_ref": "profile:test-permissive@v9", **forged}
    asked = storage_question(plan(conductor(tmp_path, [CLOUD]), institution_storage=[sent]))
    assert asked.suggested_answer is not None
    assert "My USB stick" not in asked.suggested_answer
    assert "Cloud drive" in asked.suggested_answer


def test_a_suggestion_already_offered_is_kept(tmp_path: Path) -> None:
    question = DocumentQuestion(
        question_id="q-" + "0" * 16,
        question_prompt="Where?",
        gap_section=HEADING,
        suggested_answer="On the lab server.",
        suggestion_derivation=Derivation.MODEL,
    )
    given = DraftRequest.model_validate(
        {
            "document_kind": "dmp",
            "institution_storage": [{"profile_ref": "profile:p@v1", **CLOUD}],
        }
    )
    (kept,) = storage.offer([question], given)
    assert kept.suggested_answer == "On the lab server."
