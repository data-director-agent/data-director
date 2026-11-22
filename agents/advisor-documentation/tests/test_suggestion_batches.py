"""A long data dictionary's suggestions are asked in batches, and a reply that does not parse costs
only what it left out (#1318): one cut off part-way keeps the suggestions it holds whole, and one
malformed item among valid ones drops that item alone. When nothing can be suggested, the
statement says why in plain words."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dd_agent_advisor_documentation.agent import DocumentationEditor
from dd_agent_advisor_documentation.prose import ModelWriter
from dd_agent_advisor_documentation.replies import (
    BATCH,
    CUT_SHORT,
    NOT_IN_FORM,
    batches,
    salvage,
)
from dd_agent_advisor_documentation.suggestions import (
    SUGGEST_PROMPT,
    SUGGESTED_COLUMNS,
    SuggestedAnswer,
)
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.contract.models import (
    Document,
    DocumentKind,
    DraftRequest,
    Envelope,
    FileInventory,
    InventoryFile,
    OutcomeStatus,
    TableField,
)
from dd_sdk.model import ModelRequest, ModelResponse
from dd_sdk.testing import FakeModel

MODEL = "claude-test"


class CutOffModel(FakeModel):
    """A model whose every reply stops at its length limit, as a provider reports it."""

    def send(self, request: ModelRequest) -> ModelResponse:
        return replace(super().send(request), stop="max_tokens")


def wide_table(fields: int) -> DraftRequest:
    """A data dictionary request for one table of `fields` distinct fields: two suggestable
    questions (definition and unit) for each."""
    table = InventoryFile(
        file_path="data/wide.csv",
        file_size=100,
        file_sha256="0" * 64,
        file_media_type="text/csv",
        file_identified_by="extension",
        file_fields=[TableField(name=f"var_{n:03}", field_type="number") for n in range(fields)],
    )
    inventory = FileInventory(
        inventory_files=[table],
        inventory_tool="dd-inventory",
        inventory_tool_version="1",
        inventory_made_at=datetime(2026, 11, 22, tzinfo=UTC),
    )
    return DraftRequest(document_kind=DocumentKind.DATA_DICTIONARY, inventory=inventory)


def asked_ids(sent: ModelRequest) -> list[str]:
    """The question identifiers a suggestion call asked about, read from its prompt."""
    content = sent.messages[0]["content"]  # type: ignore[index]
    questions = content.split("\n", 1)[1].split("\n\nFacts:\n", 1)[0]
    return [q["question_id"] for q in json.loads(questions)]


def answering(write: Callable[[list[dict[str, object]]], str]) -> Callable[[ModelRequest], str]:
    """A replier that suggests "Answer to <id>" for every question it is asked, written out by
    `write`, which may spoil the reply."""

    def reply(sent: ModelRequest) -> str:
        assert sent.system == SUGGEST_PROMPT
        return write([{"question_id": q, "answer": f"Answer to {q}"} for q in asked_ids(sent)])

    return reply


def whole(items: list[dict[str, object]]) -> str:
    return json.dumps({"suggestions": items})


def draft(runs_dir: Path, model: FakeModel, asked: DraftRequest) -> tuple[Envelope, Document]:
    conductor = make_conductor(runs_dir, DocumentationEditor(writer=ModelWriter(model)))
    env = conductor.invoke(request("advisor.documentation", asked), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    return env, env.payload_as(Document)


def suggestable(document: Document) -> list[str]:
    return [q.question_id for q in document.document_questions if q.gap_column in SUGGESTED_COLUMNS]


def suggested(document: Document) -> dict[str, str]:
    return {
        q.question_id: q.suggested_answer
        for q in document.document_questions
        if q.suggested_answer is not None
    }


def test_batches_keep_order_and_size() -> None:
    items = list(range(2 * BATCH + 1))
    got = batches(items)
    assert [len(b) for b in got] == [BATCH, BATCH, 1]
    assert [i for b in got for i in b] == items
    assert batches([]) == []
    with pytest.raises(ValueError):
        batches(items, 0)


def test_a_long_dictionary_is_asked_in_batches_and_every_answer_is_offered(
    runs_dir: Path,
) -> None:
    model = FakeModel(answering(whole), model_id=MODEL)
    env, document = draft(runs_dir, model, wide_table(BATCH + 5))
    ids = suggestable(document)
    assert len(ids) > 2 * BATCH  # enough questions for three calls

    sent = [asked_ids(s) for s in model.sent]
    assert len(sent) == len(batches(ids))
    assert all(0 < len(b) <= BATCH for b in sent)
    assert sorted(q for b in sent for q in b) == sorted(ids)
    # Every question got its suggestion, and every call is on the run's record.
    assert suggested(document) == {q: f"Answer to {q}" for q in ids}
    assert len(env.telemetry.model_calls) == len(sent)


def test_a_malformed_item_among_valid_ones_drops_only_itself(runs_dir: Path) -> None:
    def spoil_first(items: list[dict[str, object]]) -> str:
        items[0]["answer"] = 42  # not a string: the reply no longer matches its schema
        return whole(items)

    model = FakeModel(answering(spoil_first), model_id=MODEL)
    env, document = draft(runs_dir, model, wide_table(3))
    ids = suggestable(document)
    first, rest = ids[0], ids[1:]
    assert suggested(document) == {q: f"Answer to {q}" for q in rest}
    # The statement names the item that was not offered.
    assert first in env.outcome.statement


def test_a_reply_cut_off_part_way_keeps_what_it_holds_whole(runs_dir: Path) -> None:
    def cut(items: list[dict[str, object]]) -> str:
        text = whole(items)
        return text[: text.index(str(items[3]["question_id"])) + 5]  # inside the fourth item

    model = CutOffModel(answering(cut), model_id=MODEL)
    env, document = draft(runs_dir, model, wide_table(4))
    ids = suggestable(document)
    assert suggested(document) == {q: f"Answer to {q}" for q in ids[:3]}
    # The statement says how many went without, and why, in plain words.
    assert CUT_SHORT in env.outcome.statement


@pytest.mark.parametrize(
    ("model", "why"),
    [
        (FakeModel("I would rather not.", model_id=MODEL), NOT_IN_FORM),
        (CutOffModel('{"suggestions": [{"question_id": "q-', model_id=MODEL), CUT_SHORT),
    ],
)
def test_when_nothing_can_be_suggested_the_statement_says_why(
    runs_dir: Path, model: FakeModel, why: str
) -> None:
    env, document = draft(runs_dir, model, wide_table(BATCH))
    assert len(model.sent) > 1  # every batch was asked
    assert suggested(document) == {}
    assert why in env.outcome.statement


def test_salvage_keeps_whole_items_and_names_a_malformed_one() -> None:
    text = (
        '{"suggestions": [{"question_id": "q-1", "answer": "Age in years"}, '
        '{"question_id": "q-2", "answer": 7}, {"answer": "no identifier", "extra": 1}, '
        '{"question_id": "q-3", "answer": "Height'
    )
    got = salvage(text, "suggestions", SuggestedAnswer, "question_id")
    assert got.items == (SuggestedAnswer(question_id="q-1", answer="Age in years"),)
    assert got.unusable == ("q-2", None)


@pytest.mark.parametrize("text", ["", "not json", '{"other": []}', '{"suggestions": {}}'])
def test_salvage_of_a_reply_with_no_list_keeps_nothing(text: str) -> None:
    got = salvage(text, "suggestions", SuggestedAnswer, "question_id")
    assert got.items == () and got.unusable == ()
