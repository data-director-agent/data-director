"""The elicit stage (§8) — asking, not asking, and the replay contract.

The load-bearing test here is `test_the_question_set_is_deterministic`. LangGraph re-runs an
interrupted node from the top, so everything the node computes before it pauses runs twice; if
the question set were not stable the researcher could be shown one set of questions and have
their answers matched against another. Nothing else in the suite would catch that.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from langgraph.runtime import Runtime

from standards_advisor import __version__
from standards_advisor.context import RunContext
from standards_advisor.intake import load_intake_config
from standards_advisor.models.common import (
    AgentRef,
    Derivation,
    LifecyclePhase,
    StageStatus,
)
from standards_advisor.models.elicitation import IntakeFacet
from standards_advisor.models.inputs import DatasetInput
from standards_advisor.nodes.elicit import elicit_node
from standards_advisor.prompting import PromptLibrary
from standards_advisor.provenance import ProvenanceHandler, RunDirectory
from standards_advisor.ranking.weights import load_ranking_config
from standards_advisor.registry import get_registry
from standards_advisor.settings import Settings
from standards_advisor.state import initial_state
from tests.conftest import PLANNED_DICTIONARY


def _context(settings: Settings, tmp_path: Path) -> RunContext:
    run_dir = RunDirectory(tmp_path / "runs", "test-run")
    return RunContext(
        registry=get_registry("empty"),
        registry_route="empty",
        prompts=PromptLibrary(settings.prompts_root),
        ranking=load_ranking_config(settings.ranking_config_path()),
        intake=load_intake_config(settings.intake_config_path()),
        run_dir=run_dir,
        events=ProvenanceHandler(run_dir),
        agent=AgentRef(identity="urn:dd:agent:test", version=__version__),
        model_id="fake:fake",
    )


def _planned(**overrides: object) -> DatasetInput:
    fields: dict[str, object] = {
        "phase": LifecyclePhase.PRE_COLLECTION,
        "dictionary_path": str(PLANNED_DICTIONARY),
    }
    fields.update(overrides)
    return DatasetInput.model_validate(fields)


def _run(settings: Settings, tmp_path: Path, inputs: DatasetInput):
    ctx = _context(settings, tmp_path)
    runtime = Runtime(context=ctx)
    return elicit_node(initial_state("test-run", inputs), runtime), ctx


def test_a_collected_run_asks_nothing_and_still_reports(settings, tmp_path, sample_input):
    """The stage runs on every path, so the graph needs no conditional edge.

    `test_provenance` compares the manifest's stages against `list(StageName)`, which only holds
    because of this — a stage that were skipped instead would break that assertion.
    """
    update, _ctx = _run(settings, tmp_path, sample_input)

    assert update["answers"] is None
    report = update["stage_reports"][0]
    assert report.status is StageStatus.EMPTY
    assert any("collected" in note for note in report.notes)


def test_a_pre_collection_run_with_no_answers_tries_to_pause(settings, tmp_path):
    """`interrupt()` only works inside a graph, and that is the point being asserted.

    Calling it outside a runnable context raises `RuntimeError`, which is exactly what proves
    the node reached the interrupt rather than quietly carrying on with no answers. The pause as
    a *usable* outcome is `test_resume`'s subject, because it needs the graph and a checkpoint.
    """
    with pytest.raises(RuntimeError, match="outside of a runnable context"):
        _run(settings, tmp_path, _planned())


def test_every_question_explains_why_it_is_asked(settings):
    """§8.2 of the Blueprint: the agent assists and recommends, it does not direct.

    A question put to a researcher without saying what it is for is an interrogation. The loader
    already requires `why` to be present; this asserts nobody satisfied it with an empty string.
    """
    intake = load_intake_config(settings.intake_config_path())
    for question in intake.questions_for(LifecyclePhase.PRE_COLLECTION):
        assert question.why.strip(), f"{question.id} does not say why it is asked"
        assert question.text.strip().endswith("?"), f"{question.id} is not phrased as a question"


def test_answers_supplied_up_front_mean_no_pause(settings, tmp_path):
    """What makes a pre-collection run scriptable, and the whole test suite single-invoke."""
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps({"subject": ["Soil Science"]}), encoding="utf-8")

    update, _ctx = _run(settings, tmp_path, _planned(answers_path=str(answers)))

    context = update["answers"]
    assert context is not None
    assert context.interactive is False
    assert context.values_for(IntakeFacet.SUBJECT) == ["Soil Science"]


def test_the_question_set_is_deterministic(settings, tmp_path):
    """The replay contract. Two calls must give the same questions in the same order.

    A node that paused is re-run from the top on resume, so anything non-deterministic before
    the `interrupt()` — a model call, a shuffle, a timestamp in an id — would silently mismatch
    the answers against the questions.
    """
    intake = load_intake_config(settings.intake_config_path())
    first = intake.questions_for(LifecyclePhase.PRE_COLLECTION)
    second = intake.questions_for(LifecyclePhase.PRE_COLLECTION)

    assert [q.id for q in first] == [q.id for q in second]
    assert first == second


def test_an_answer_is_recorded_as_skipped_rather_than_absent(settings, tmp_path):
    """ "I do not know" is information, and must not read as though nothing was asked."""
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps({"subject": ["Soil Science"]}), encoding="utf-8")

    update, _ctx = _run(settings, tmp_path, _planned(answers_path=str(answers)))
    context = update["answers"]

    assert len(context.answers) == 8, "one entry per question asked, whatever the caller sent"
    skipped = [answer.question_id for answer in context.answers if answer.skipped]
    assert "field_of_research" in skipped
    assert update["stage_reports"][0].counts == {"questions": 8, "answered": 1, "skipped": 7}


def test_answers_are_recorded_as_researcher_terms_not_registry_terms(settings, tmp_path):
    """R3.5 depends on this staying visible.

    An answer typed by a researcher is not a term from a controlled list. Recording it with a
    `list_name` would be the exact dishonesty §5.1 tier 2 exists to avoid — and with the default
    registry route there is no list to have picked it from anyway.
    """
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps({"subject": ["Soil Science"]}), encoding="utf-8")

    update, _ctx = _run(settings, tmp_path, _planned(answers_path=str(answers)))
    terms = update["answers"].terms_for(IntakeFacet.SUBJECT)

    assert len(terms) == 1
    assert terms[0].derivation is Derivation.RESEARCHER_ANSWER
    assert terms[0].list_name is None
    assert terms[0].list_version is None


def test_a_single_answer_question_keeps_only_the_first(settings, tmp_path):
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps({"target_repository": ["ORDA", "Zenodo"]}), encoding="utf-8")

    update, _ctx = _run(settings, tmp_path, _planned(answers_path=str(answers)))
    context = update["answers"]

    assert context.values_for(IntakeFacet.TARGET_REPOSITORY) == ["ORDA"]
    assert any("takes one answer" in note for note in update["stage_reports"][0].notes)


def test_a_bare_string_is_accepted_where_a_list_was_expected(settings, tmp_path):
    """Lenient on shape: these are typed by people or written by hand."""
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps({"subject": "Soil Science"}), encoding="utf-8")

    update, _ctx = _run(settings, tmp_path, _planned(answers_path=str(answers)))
    assert update["answers"].values_for(IntakeFacet.SUBJECT) == ["Soil Science"]


def test_a_malformed_answers_file_is_recorded_not_raised(settings, tmp_path):
    """A content problem (see `errors`), and specifically not a fallback to prompting.

    Falling back to an interactive prompt would hang a scripted run; the failure is recorded and
    every question comes back skipped.
    """
    answers = tmp_path / "answers.json"
    answers.write_text("{ not json", encoding="utf-8")

    update, _ctx = _run(settings, tmp_path, _planned(answers_path=str(answers)))

    assert any(failure.kind == "answers_unreadable" for failure in update["failures"])
    assert all(answer.skipped for answer in update["answers"].answers)
    assert update["stage_reports"][0].status is StageStatus.EMPTY


def test_a_missing_answers_file_is_recorded_not_raised(settings, tmp_path):
    update, _ctx = _run(settings, tmp_path, _planned(answers_path=str(tmp_path / "gone.json")))
    assert any(failure.kind == "answers_missing" for failure in update["failures"])


def test_an_answer_to_a_question_never_asked_is_reported(settings, tmp_path):
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps({"favourite_colour": ["blue"]}), encoding="utf-8")

    update, _ctx = _run(settings, tmp_path, _planned(answers_path=str(answers)))
    assert any(failure.kind == "answer_unknown_question" for failure in update["failures"])


def test_the_answers_are_written_to_the_run_record(settings, tmp_path):
    """R10: the elicitation is an action on metadata, so it has to be auditable."""
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps({"subject": ["Soil Science"]}), encoding="utf-8")

    _update, ctx = _run(settings, tmp_path, _planned(answers_path=str(answers)))
    recorded = ctx.run_dir.read_json("answers")

    assert recorded is not None
    assert recorded["intake_version"] == "intake.v1"
    assert len(recorded["intake_sha256"]) == 64
    assert recorded["asked_at"] and recorded["answered_at"]


def test_a_pre_collection_input_needs_a_dictionary():
    """Caught at the input, before any stage runs — a caller's mistake, not a content outcome."""
    with pytest.raises(ValueError, match="dictionary_path"):
        DatasetInput(phase=LifecyclePhase.PRE_COLLECTION)


def test_a_pre_collection_input_cannot_carry_data_files():
    """Otherwise a run would profile real data and still report itself as phase 1."""
    with pytest.raises(ValueError, match="no files"):
        DatasetInput(
            phase=LifecyclePhase.PRE_COLLECTION,
            dictionary_path=str(PLANNED_DICTIONARY),
            files=["something.csv"],
        )
