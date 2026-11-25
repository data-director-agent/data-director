"""advisor.metadata asks about every value it leaves null, and places the answers a person recorded
(docs/specs/drafting.md, invariants 5 and 6), on its template path."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from test_metadata_agent import draft, sample

from dd_agent_advisor_metadata.form import load_form
from dd_agent_advisor_metadata.location import entry_path
from dd_agent_advisor_metadata.questions import gaps, question_id
from dd_metadata_records.standards import DATACITE_4
from dd_sdk.contract.facts import FactKind, ProjectFact, StandardKind
from dd_sdk.contract.models import Document, DraftAnswer, OutcomeStatus


def drafted(runs_dir: Path, answers: list[DraftAnswer] | None = None) -> Document:
    asked = sample().model_copy(update={"draft_answers": answers or []})
    env, grounded = draft(runs_dir, asked)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert grounded
    return env.payload_as(Document)


def value_at(record: dict[str, Any], path: str) -> Any:
    node: Any = record
    for part in path.replace("]", "").replace("[", ".").split("."):
        node = node[int(part)] if part.isdigit() else node[part]
    return node


def test_every_null_value_has_exactly_one_question_naming_it(runs_dir: Path) -> None:
    document = drafted(runs_dir)
    record = json.loads(document.document_text)
    asked = {q.gap_property or "": q for q in document.document_questions}
    # A place is asked about first by its entry: whether it may be published (#1073).
    first = {g.path: entry_path(g) for g in gaps(record) if g.prop == "geoLocations"}
    nulls = [first.get(g.path, g.path) for g in gaps(record)]
    assert first and nulls and sorted(asked) == sorted(nulls)
    for path, question in asked.items():
        assert path and (path in first.values() or value_at(record, path) is None)
        assert question.question_id == question_id(path)
        assert question.gap_section is None and question.gap_file is None
        assert question.suggested_answer is None  # the template suggests nothing


def test_question_ids_are_the_same_in_every_draft(runs_dir: Path) -> None:
    first = [q.question_id for q in drafted(runs_dir).document_questions]
    again = [q.question_id for q in drafted(runs_dir).document_questions]
    assert first == again and len(set(first)) == len(first)


def test_an_answer_is_placed_as_given_and_asked_no_more(runs_dir: Path) -> None:
    before = drafted(runs_dir)
    title = next(q for q in before.document_questions if q.gap_property == "titles[0].title")
    answer = DraftAnswer(answered_question=title.question_id, answer_text="Soil survey, 2026")
    after = drafted(runs_dir, [answer])

    record = json.loads(after.document_text)
    assert record["titles"] == [{"title": "Soil survey, 2026"}]
    asked = {q.question_id for q in after.document_questions}
    assert title.question_id not in asked
    assert asked == {q.question_id for q in before.document_questions} - {title.question_id}


def test_an_answer_to_a_question_not_asked_or_left_blank_is_not_placed(runs_dir: Path) -> None:
    before = drafted(runs_dir)
    blank = before.document_questions[0].question_id
    answers = [
        DraftAnswer(answered_question="q-" + "f" * 16, answer_text="Anything"),
        DraftAnswer(answered_question=blank, answer_text="  "),
    ]
    after = drafted(runs_dir, answers)
    assert after.document_text == before.document_text
    assert after.document_questions == before.document_questions


def test_the_rule_table_marks_only_what_a_model_may_suggest() -> None:
    form = load_form(DATACITE_4)
    suggestable = {prop for prop, entry in form.items() if entry.suggest}
    # Who made it, when, under what rights and with whose money only the researcher can say.
    for prop in ("creators", "contributors", "dates", "rightsList", "fundingReferences"):
        assert prop not in suggestable
    assert all(form[prop].ask for prop in suggestable)


def test_the_licence_question_names_the_licences_the_repository_accepts(runs_dir: Path) -> None:
    """#1074: a researcher whose journal asks for another licence learns of the clash when asked,
    not when validation refuses the record."""
    asked = sample()
    assert asked.requirements is not None
    eidc = asked.requirements.model_copy(
        update={"repository_name": "EIDC", "licences": ["OGL-UK-3.0", "CC-BY-4.0"]}
    )
    env, _ = draft(runs_dir, asked.model_copy(update={"requirements": eidc}))
    document = env.payload_as(Document)
    (licence,) = [
        q for q in document.document_questions if (q.gap_property or "").startswith("rightsList")
    ]
    assert licence.question_prompt.endswith("EIDC accepts: OGL-UK-3.0, CC-BY-4.0.")


def test_without_licences_the_licence_question_names_none(runs_dir: Path) -> None:
    asked = sample()
    assert asked.requirements is not None
    open_ = asked.requirements.model_copy(update={"licences": None})
    env, _ = draft(runs_dir, asked.model_copy(update={"requirements": open_}))
    (licence,) = [
        q
        for q in env.payload_as(Document).document_questions
        if (q.gap_property or "").startswith("rightsList")
    ]
    assert "accepts" not in licence.question_prompt


def _standard(name: str, kind: str, target: str = "dataset") -> ProjectFact:
    return ProjectFact(
        fact_kind=FactKind.STANDARD,
        fact_subject=f"{name} {target}",
        standard_name=name,
        standard_kind=StandardKind(kind),
        standard_target=target,
    )


def _subjects_prompts(runs_dir: Path, decisions: list[ProjectFact]) -> list[str]:
    asked = sample().model_copy(update={"project_decisions": decisions})
    env, _ = draft(runs_dir, asked)
    return [
        q.question_prompt
        for q in env.payload_as(Document).document_questions
        if (q.gap_property or "").startswith("subjects")
    ]


def test_the_subjects_question_names_the_vocabularies_the_project_chose(runs_dir: Path) -> None:
    """#1391: a vocabulary a person chose for the dataset is named where its terms are asked for;
    a format, or one chosen for a field's values, is not."""
    decisions = [
        _standard("AGROVOC", "controlled_vocabulary"),
        _standard("CSV", "data_format"),
        _standard("ISO 8601", "field_format", "field:sampled_on"),
    ]
    prompts = _subjects_prompts(runs_dir, decisions)
    assert prompts
    for prompt in prompts:
        assert "AGROVOC" in prompt
        assert "CSV" not in prompt
        assert "ISO 8601" not in prompt


def test_without_a_chosen_vocabulary_the_subjects_question_names_none(runs_dir: Path) -> None:
    assert _subjects_prompts(runs_dir, []) == _subjects_prompts(
        runs_dir, [_standard("CSV", "data_format")]
    )
