"""A project fact has what its kind needs (docs/specs/projects.md, invariant 28): a sharing
commitment read from a plan names the passage it rests on and the document that holds it (#962),
and a standard chosen names the standard, and what it is chosen for only as the dataset or one
field (#1391); a project's data management plan names the attached document, under the one
subject a plan has (#1447)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from dd_sdk.contract.facts import FACT_NEEDS, PLAN_SUBJECT, FactKind, ProjectFact

COMMITMENT: dict[str, Any] = {
    "fact_kind": "sharing_commitment",
    "fact_subject": "Survey responses",
    "commitment_repository": "ORDA",
    "commitment_access": "open",
    "commitment_licence": "CC BY 4.0",
    "commitment_quote": "Survey responses will be shared openly in ORDA under CC BY 4.0.",
    "commitment_document": "a" * 64,
}


def test_a_sharing_commitment_names_its_passage_and_document() -> None:
    fact = ProjectFact.model_validate(COMMITMENT)
    assert fact.fact_kind == FactKind.SHARING_COMMITMENT
    assert set(FACT_NEEDS[FactKind.SHARING_COMMITMENT]) <= fact.model_fields_set


@pytest.mark.parametrize("slot", FACT_NEEDS[FactKind.SHARING_COMMITMENT])
def test_a_sharing_commitment_without_its_passage_or_document_is_refused(slot: str) -> None:
    with pytest.raises(ValidationError):
        ProjectFact.model_validate({**COMMITMENT, slot: None})


def test_a_commitment_names_its_document_by_digest() -> None:
    with pytest.raises(ValidationError):
        ProjectFact.model_validate({**COMMITMENT, "commitment_document": "dmp.docx"})


def test_where_and_how_a_commitment_shares_are_optional() -> None:
    """A plan may name an output without saying where, how openly or under what licence."""
    bare = {
        k: v
        for k, v in COMMITMENT.items()
        if not k.startswith(("commitment_r", "commitment_a", "commitment_l"))
    }
    assert ProjectFact.model_validate(bare).commitment_repository is None


STANDARD: dict[str, Any] = {
    "fact_kind": "standard",
    "fact_subject": "Darwin Core",
    "standard_name": "Darwin Core",
    "standard_id": "https://doi.org/10.25504/FAIRsharing.xvf5y3",
    "standard_kind": "metadata_standard",
    "standard_target": "dataset",
}


def test_a_standard_names_what_was_chosen() -> None:
    fact = ProjectFact.model_validate(STANDARD)
    assert fact.fact_kind == FactKind.STANDARD
    assert set(FACT_NEEDS[FactKind.STANDARD]) <= fact.model_fields_set


def test_a_standard_without_its_name_is_refused() -> None:
    with pytest.raises(ValidationError):
        ProjectFact.model_validate({**STANDARD, "standard_name": None})


@pytest.mark.parametrize("target", ["dataset", "field:species"])
def test_a_standard_is_chosen_for_the_dataset_or_one_field(target: str) -> None:
    assert ProjectFact.model_validate({**STANDARD, "standard_target": target}).standard_target


@pytest.mark.parametrize("target", ["field:", "table", "species"])
def test_a_standard_chosen_for_anything_else_is_refused(target: str) -> None:
    with pytest.raises(ValidationError):
        ProjectFact.model_validate({**STANDARD, "standard_target": target})


def test_only_its_name_is_needed() -> None:
    """A researcher may state a standard by name alone, with no registry record."""
    bare = {"fact_kind": "standard", "fact_subject": "ISO 8601", "standard_name": "ISO 8601"}
    assert ProjectFact.model_validate(bare).standard_kind is None


PLAN: dict[str, Any] = {
    "fact_kind": "data_management_plan",
    "fact_subject": PLAN_SUBJECT,
    "plan_document": "b" * 64,
}


def test_a_plan_fact_names_the_attached_document_by_digest() -> None:
    fact = ProjectFact.model_validate(PLAN)
    assert fact.fact_kind == FactKind.DATA_MANAGEMENT_PLAN
    assert set(FACT_NEEDS[FactKind.DATA_MANAGEMENT_PLAN]) <= fact.model_fields_set


@pytest.mark.parametrize("document", [None, "dmp.docx"])
def test_a_plan_fact_without_a_document_digest_is_refused(document: str | None) -> None:
    with pytest.raises(ValidationError):
        ProjectFact.model_validate({**PLAN, "plan_document": document})


def test_a_project_has_one_plan_subject() -> None:
    """Every plan fact has the same subject, so the last decision on it is the current plan."""
    with pytest.raises(ValidationError):
        ProjectFact.model_validate({**PLAN, "fact_subject": "grant/dmp.docx"})
