"""A data dictionary's suggestions draw on the definitions and units the researcher already gave,
and on the project's decisions (docs/specs/drafting.md, invariant 7): once a person has answered
some fields, the model is shown those answers as examples, so it can suggest the rest in their
wording and with the naming conventions they show, and the standards and vocabularies chosen, so
it can suggest in their terms. Nothing the model is shown is written into a cell."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from test_prose import StubClient, draft, sample, template_draft
from test_suggestions import DICTIONARY, every_suggestion, suggestible

from dd_agent_advisor_documentation.dictionary import supplied_definitions
from dd_agent_advisor_documentation.suggestions import (
    MAX_DEFINITIONS,
    PROJECT_DECISIONS,
    RESEARCHER_DEFINITIONS,
    SUGGEST_PROMPT,
)
from dd_sdk.contract.facts import FactKind, ProjectFact
from dd_sdk.contract.models import Document, DraftAnswer

AGROVOC = ProjectFact(
    fact_kind=FactKind.STANDARD,
    fact_subject="AGROVOC",
    standard_name="AGROVOC",
    standard_id="https://doi.org/10.25504/FAIRsharing.anpj91",
    standard_target="dataset",
)


def suggestion_facts(client: StubClient) -> list[dict[str, Any]]:
    """The facts each data dictionary suggestion call was sent, one per batch."""
    return [
        json.loads(sent["messages"][0]["content"].split("\n\nFacts:\n", 1)[1])
        for sent in client.sent
        if sent["system"] == SUGGEST_PROMPT
    ]


@pytest.mark.requirement("R5")
def test_the_projects_decisions_are_shown_to_the_suggester_and_never_written(
    runs_dir: Path,
) -> None:
    asked = sample(DICTIONARY).model_copy(update={"project_decisions": [AGROVOC]})
    template = template_draft(runs_dir, asked)
    client = StubClient(every_suggestion(template))
    env, grounded = draft(runs_dir, client, asked)
    assert grounded
    sent = suggestion_facts(client)
    assert sent
    for facts in sent:
        assert facts[PROJECT_DECISIONS][0]["standard_name"] == "AGROVOC"
    # Shown, never written: the dictionary is the template's to the byte.
    assert env.payload_as(Document).document_text == template.document_text


@pytest.mark.requirement("R5")
def test_without_decisions_the_suggester_is_shown_none(runs_dir: Path) -> None:
    asked = sample(DICTIONARY)
    template = template_draft(runs_dir, asked)
    client = StubClient(every_suggestion(template))
    draft(runs_dir, client, asked)
    sent = suggestion_facts(client)
    assert sent and all(PROJECT_DECISIONS not in f for f in sent)


@pytest.mark.requirement("R5")
def test_before_any_answer_the_suggester_is_shown_no_definitions(runs_dir: Path) -> None:
    asked = sample(DICTIONARY)
    template = template_draft(runs_dir, asked)
    client = StubClient(every_suggestion(template))
    draft(runs_dir, client, asked)
    sent = suggestion_facts(client)
    assert sent and all(RESEARCHER_DEFINITIONS not in f for f in sent)


@pytest.mark.requirement("R5")
def test_a_definition_given_is_shown_as_an_example_and_no_longer_asked(runs_dir: Path) -> None:
    asked = sample(DICTIONARY)
    template = template_draft(runs_dir, asked)
    answered = next(q for q in suggestible(template) if q.gap_column == "description")
    given = DraftAnswer(answered_question=answered.question_id, answer_text="Soil pH in water")
    client = StubClient(every_suggestion(template))
    env, grounded = draft(runs_dir, client, asked.model_copy(update={"draft_answers": [given]}))
    assert grounded
    sent = suggestion_facts(client)
    assert sent
    example = {"file": answered.gap_file, "field": answered.gap_field}
    for facts in sent:
        assert {**example, "description": "Soil pH in water"} in facts[RESEARCHER_DEFINITIONS]
    asked_now = {q.question_id for q in env.payload_as(Document).document_questions}
    assert answered.question_id not in asked_now


def test_the_definitions_shown_are_capped() -> None:
    rows = "".join(f"t.csv,f{i},d{i},supplied,,unknown\n" for i in range(MAX_DEFINITIONS + 5))
    text = "file,field,description,description_source,unit,unit_source\n" + rows
    got = supplied_definitions(text, ["description", "unit"], MAX_DEFINITIONS)
    assert len(got) == MAX_DEFINITIONS
    assert got[0] == {"file": "t.csv", "field": "f0", "description": "d0"}
