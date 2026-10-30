"""The document double drafts one project document of each kind through the conductor
(ADR-0035), and each passes the input check, the gate and the grounding linter."""

from __future__ import annotations

from pathlib import Path

import pytest

from dd_harness.testing import (
    TEST_PRINCIPAL,
    DocumentStub,
    document_request,
    make_conductor,
    request,
)
from dd_sdk.contract.models import Document, DocumentKind, OutcomeStatus


@pytest.mark.parametrize("kind", list(DocumentKind))
def test_the_document_stub_drafts_a_proposed_document_of_each_kind(
    runs_dir: Path, kind: DocumentKind
) -> None:
    conductor = make_conductor(runs_dir, DocumentStub())
    env = conductor.invoke(
        request("stub.document", document_request(kind)), acting_for=TEST_PRINCIPAL
    )
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome
    assert env.payload is not None
    document = Document.model_validate(env.payload.model_dump())
    assert document.document_kind == kind
    assert document.document_text and document.media_type
    assert document.revises is None  # a first draft, for which the conductor mints an id
    stored = conductor.store.get(env.invocation_id)
    assert stored is not None and stored["payload"]["schema_class"] == "Document"
