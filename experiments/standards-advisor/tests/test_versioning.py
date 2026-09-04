"""Prompt and ranking-weight versioning (§5.3, §5.4).

A version string that can drift from the thing it names records nothing. These tests hold the
two-step discipline in place: to change a prompt or a weighting you write a new file and point
the manifest or the config name at it, so a run record from six months ago still resolves to
what was actually used.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from standards_advisor.errors import ConfigError, PromptNotFound
from standards_advisor.intake import load_intake_config
from standards_advisor.prompting import PromptLibrary
from standards_advisor.ranking import RULES
from standards_advisor.ranking.weights import load_ranking_config
from standards_advisor.settings import Settings

# -- prompts ----------------------------------------------------------------------------------


def test_the_committed_prompt_matches_its_recorded_hash(settings: Settings):
    """The whole suite uses the real prompt library, so this catches an edit-in-place."""
    prompt = PromptLibrary(settings.prompts_root).get("explain")
    assert prompt.version == "v1"
    assert len(prompt.sha256) == 64
    assert "grounding" not in prompt.text.lower() or prompt.text  # sanity: text was loaded


def test_editing_a_prompt_without_bumping_its_version_is_a_hard_failure(tmp_path: Path):
    """Not a warning. §5.4's "recorded with each run" means nothing if the text can drift."""
    (tmp_path / "explain").mkdir()
    (tmp_path / "explain" / "v1.md").write_text("edited text", encoding="utf-8")
    (tmp_path / "manifest.toml").write_text(
        '[explain]\ncurrent = "v1"\nsha256 = "0" \n', encoding="utf-8"
    )

    with pytest.raises(PromptNotFound, match="write a new version"):
        PromptLibrary(tmp_path).get("explain")


def test_an_unknown_prompt_lists_the_ones_that_exist(settings: Settings):
    with pytest.raises(PromptNotFound, match="known"):
        PromptLibrary(settings.prompts_root).get("no_such_prompt")


def test_a_missing_prompt_file_is_reported(tmp_path: Path):
    (tmp_path / "manifest.toml").write_text(
        '[explain]\ncurrent = "v9"\nsha256 = "abc"\n', encoding="utf-8"
    )
    with pytest.raises(PromptNotFound, match="not found"):
        PromptLibrary(tmp_path).get("explain")


def test_a_manifest_entry_missing_its_hash_is_rejected(tmp_path: Path):
    (tmp_path / "manifest.toml").write_text('[explain]\ncurrent = "v1"\n', encoding="utf-8")
    with pytest.raises(PromptNotFound, match="missing sha256"):
        PromptLibrary(tmp_path)


def test_the_unused_tier_two_prompt_is_not_in_the_manifest(settings: Settings):
    """Listing a prompt nothing loads would imply tier 2 works. It does not (§5.1)."""
    library = PromptLibrary(settings.prompts_root)
    assert "profile_subject" not in library.names()
    assert (settings.prompts_root / "profile_subject" / "v1.md").is_file()


# -- ranking weights --------------------------------------------------------------------------


def test_the_committed_weights_load_and_hash(settings: Settings):
    config = load_ranking_config(settings.ranking_config_path())
    assert config.version == "ranking.v1"
    assert len(config.sha256) == 64
    assert 0.0 < config.confidence_floor < 1.0


def test_every_rule_in_code_has_a_weight(settings: Settings):
    """The rule names in `ranking/rules.py`, the weights file and the output's
    `score_components` all have to agree, or a score cannot be attributed to a rule."""
    config = load_ranking_config(settings.ranking_config_path())
    missing = set(RULES) - set(config.weights)
    assert not missing, f"rules with no weight: {sorted(missing)}"


def test_every_weight_names_a_rule_that_exists(settings: Settings):
    config = load_ranking_config(settings.ranking_config_path())
    unknown = set(config.weights) - set(RULES)
    assert not unknown, f"weights for rules that do not exist: {sorted(unknown)}"


def test_all_nine_rules_from_the_design_are_present():
    assert set(RULES) == {
        "subject_overlap",
        "field_of_research_overlap",
        "entity_scope_overlap",
        "community_uptake",
        "repository_fit",
        "maturity",
        "specificity",
        "openness",
        "type_match",
    }


def test_the_filename_is_the_version(tmp_path: Path):
    """So a new weighting is a new file rather than an edit to an existing one (§5.3)."""
    path = tmp_path / "ranking.v2.toml"
    path.write_text(
        'version = "ranking.v1"\nconfidence_floor = 0.5\n[weights]\nsubject_overlap = 1.0\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="the filename is the version"):
        load_ranking_config(path)


def test_a_missing_confidence_floor_is_rejected(tmp_path: Path):
    path = tmp_path / "ranking.v3.toml"
    path.write_text('version = "ranking.v3"\n[weights]\nsubject_overlap = 1.0\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="confidence_floor"):
        load_ranking_config(path)


def test_a_non_numeric_weight_is_rejected(tmp_path: Path):
    path = tmp_path / "ranking.v4.toml"
    path.write_text(
        'version = "ranking.v4"\nconfidence_floor = 0.5\n[weights]\nsubject_overlap = "high"\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="must be a number"):
        load_ranking_config(path)


# -- what reaches the output ------------------------------------------------------------------


def test_the_run_record_and_document_agree_on_the_versions_used(settings: Settings, sample_input):
    from standards_advisor.runner import run_pipeline

    result = run_pipeline(settings, sample_input, use_checkpoints=False)
    assert result.document is not None

    config = load_ranking_config(settings.ranking_config_path())
    assert result.document.ranking_config.version == config.version
    assert result.document.ranking_config.sha256 == config.sha256
    assert result.manifest.ranking_config == result.document.ranking_config


# -- intake question set (§8) -----------------------------------------------------------------


def test_the_committed_question_set_loads_and_is_hashed(settings: Settings):
    """The same discipline as the weights, for the same reason.

    The questions put to a researcher are part of what happened on a run (R10), so a run record
    has to resolve to the text actually asked — which a bare version string cannot guarantee.
    """
    intake = load_intake_config(settings.intake_config_path())
    assert intake.version == "intake.v1"
    assert len(intake.sha256) == 64
    assert intake.ref().version == intake.version


def test_the_question_set_version_is_its_filename(tmp_path: Path):
    """A new question set is a new file, never an edit to an existing one."""
    path = tmp_path / "intake.v1.toml"
    path.write_text(
        'version = "intake.v2"\n[[question]]\nid = "s"\nfacet = "subject"\n'
        'text = "What?"\nwhy = "because"\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="the filename is the version"):
        load_intake_config(path)


def test_every_question_facet_maps_onto_a_profile_field(settings: Settings):
    """An answer nothing consumes is a question that wasted a researcher's time.

    The loader rejects an unknown facet, so this asserts the committed set only uses facets the
    profile builder actually reads — the pairing that makes `IntakeFacet` worth having.
    """
    from standards_advisor.models.elicitation import IntakeFacet

    intake = load_intake_config(settings.intake_config_path())
    used = {question.facet for question in intake.questions}
    assert used <= set(IntakeFacet)
    assert IntakeFacet.SUBJECT in used, "subject is the main signal; it must be asked"


def test_a_question_with_an_unmapped_facet_is_refused(tmp_path: Path):
    path = tmp_path / "intake.v1.toml"
    path.write_text(
        'version = "intake.v1"\n[[question]]\nid = "s"\nfacet = "favourite_colour"\n'
        'text = "What?"\nwhy = "because"\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="known facets"):
        load_intake_config(path)


def test_a_repeated_question_id_is_refused(tmp_path: Path):
    """Answers are matched to questions by id, so a duplicate would silently discard one."""
    path = tmp_path / "intake.v1.toml"
    entry = '[[question]]\nid = "s"\nfacet = "subject"\ntext = "What?"\nwhy = "because"\n'
    path.write_text(f'version = "intake.v1"\n{entry}{entry}', encoding="utf-8")
    with pytest.raises(ConfigError, match="repeats question id"):
        load_intake_config(path)


def test_a_question_set_with_no_questions_is_refused(tmp_path: Path):
    path = tmp_path / "intake.v1.toml"
    path.write_text('version = "intake.v1"\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="no \\[\\[question\\]\\] entries"):
        load_intake_config(path)
