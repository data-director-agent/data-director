"""A project fact has what its kind needs (docs/specs/projects.md, invariant 28): a sharing
commitment read from a plan names the passage it rests on and the document that holds it (#962)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from dd_sdk.contract.facts import FACT_NEEDS, FactKind, ProjectFact

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
