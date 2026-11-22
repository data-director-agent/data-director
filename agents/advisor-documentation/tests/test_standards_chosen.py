"""The README names the standards, vocabularies and formats people in the project chose
(`standard` project facts, docs/specs/projects.md, #1391), and nothing when none was chosen."""

from __future__ import annotations

from pathlib import Path

from test_documentation_agent import draft, sample

from dd_agent_advisor_documentation.drafted import standards
from dd_sdk.contract.facts import FactKind, ProjectFact
from dd_sdk.contract.models import Document, OutcomeStatus

README = "soil-survey.readme.draft.json"
AGROVOC = ProjectFact(
    fact_kind=FactKind.STANDARD,
    fact_subject="AGROVOC",
    standard_name="AGROVOC",
    standard_id="https://doi.org/10.25504/FAIRsharing.anpj91",
    standard_target="dataset",
)
ISO_8601 = ProjectFact(
    fact_kind=FactKind.STANDARD,
    fact_subject="ISO 8601 (field:sampled_on)",
    standard_name="ISO 8601",
    standard_target="field:sampled_on",
)
LICENCE = ProjectFact(fact_kind=FactKind.LICENCE, fact_subject="licence", licence_id="CC-BY-4.0")


def readme(runs_dir: Path, decisions: list[ProjectFact]) -> str:
    env, grounded = draft(
        runs_dir, sample(README).model_copy(update={"project_decisions": decisions})
    )
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert grounded
    return env.payload_as(Document).document_text


def test_the_readme_names_each_standard_chosen_and_what_for(runs_dir: Path) -> None:
    text = readme(runs_dir, [AGROVOC, ISO_8601, LICENCE])
    assert f"[AGROVOC]({AGROVOC.standard_id})" in text
    assert "`sampled_on`" in text


def test_without_a_standard_chosen_the_readme_is_as_it_was(runs_dir: Path) -> None:
    assert readme(runs_dir, [LICENCE]) == readme(runs_dir, [])


def test_only_standard_facts_are_listed() -> None:
    assert standards([LICENCE]) is None
    listed = standards([AGROVOC, LICENCE])
    assert listed is not None
    assert "CC-BY-4.0" not in listed
