"""An answer given for one kind of document, offered to a drafter of another (#1284,
docs/specs/drafting.md, invariant 7): in a project the conductor gives it as `shared_answers`,
never as `draft_answers`, so the drafter may suggest it but not place it."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dd_harness.projects import ProjectStore
from dd_harness.testing import (
    STUB_QUESTION,
    TEST_PRINCIPAL,
    DocumentStub,
    make_conductor,
    request,
)
from dd_sdk.contract.models import DocumentKind, DraftAnswer, DraftRequest, OutcomeStatus


def given_to(tmp_path: Path, projects: ProjectStore, conversation: str, kind: DocumentKind) -> Any:
    """What a drafter of `kind` was given, as the run store keeps it."""
    conductor = make_conductor(tmp_path / "runs", DocumentStub(asks=True))
    conductor.projects = projects
    req = request("stub.document", DraftRequest(document_kind=kind)).model_copy(
        update={"conversation_id": conversation}
    )
    env = conductor.invoke(req, acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    stored = json.loads((tmp_path / "runs" / env.invocation_id / "request.json").read_text())
    return stored["input"]


def test_an_answer_on_a_shared_field_is_offered_to_another_kind_and_not_placed(
    tmp_path: Path,
) -> None:
    projects = ProjectStore(tmp_path / "projects")
    project = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    assert STUB_QUESTION.shared_field is not None

    first = given_to(tmp_path, projects, conversation, DocumentKind.README)
    assert "shared_answers" not in first
    (document,) = projects.documents(project)
    answer = DraftAnswer(answered_question=STUB_QUESTION.question_id, answer_text="Soil cores")
    projects.answer(
        project, document["document_id"], 1, [answer], acted_for=TEST_PRINCIPAL, caused_by="t"
    )

    other = given_to(tmp_path, projects, conversation, DocumentKind.METADATA_RECORD)
    assert "draft_answers" not in other
    [shared] = other["shared_answers"]
    assert shared["shared_field"] == STUB_QUESTION.shared_field.value
    assert shared["answer_text"] == answer.answer_text
    assert shared["answered_question"] == STUB_QUESTION.question_id
    assert shared["answered_in"] == DocumentKind.README.value
    # Nothing is recorded for the metadata record until a person answers it there.
    record = [d for d in projects.documents(project) if d["document_kind"] == "metadata_record"]
    assert [d["answers"] for d in record] == [[]]

    # The same kind is given the answer to place, and nothing to suggest.
    again = given_to(tmp_path, projects, conversation, DocumentKind.README)
    assert "shared_answers" not in again
    assert again["draft_answers"] == [answer.model_dump(mode="json")]
