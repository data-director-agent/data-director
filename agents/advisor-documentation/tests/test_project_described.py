"""Before the data exist, the README that plans the documentation and the Data Management Plan
place what people decided at "Describe your project" (`setup.project`): what the project is for,
its field and period, as supplied facts (docs/specs/drafting.md, invariant 2); and nothing when
none is decided."""

from __future__ import annotations

from pathlib import Path

from test_dmp_draft import asked as dmp_asked
from test_dmp_draft import draft as draft_plan
from test_dmp_draft import redrafted
from test_documentation_agent import draft, sample

from dd_agent_advisor_documentation.drafted import project
from dd_sdk.contract.facts import PLAN_SUBJECT, FactKind, ProjectFact
from dd_sdk.contract.models import Document, OutcomeStatus

SUMMARY = ProjectFact(
    fact_kind=FactKind.PROJECT_SUMMARY,
    fact_subject=PLAN_SUBJECT,
    summary_text="The project studies how upland peat bogs respond to summer drought.",
)
FIELD = ProjectFact(
    fact_kind=FactKind.FIELD_OF_STUDY, fact_subject=PLAN_SUBJECT, field_name="Ecohydrology"
)
PERIOD = ProjectFact(
    fact_kind=FactKind.PROJECT_PERIOD,
    fact_subject=PLAN_SUBJECT,
    period_start="2027-01",
    period_end="2029-12",
)
LICENCE = ProjectFact(fact_kind=FactKind.LICENCE, fact_subject="licence", licence_id="CC-BY-4.0")


def planning_readme(runs_dir: Path, decisions: list[ProjectFact]) -> str:
    given = sample("soil-survey.readme.draft.json").model_copy(
        update={"inventory": None, "project_decisions": decisions}
    )
    env, _ = draft(runs_dir, given)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    return env.payload_as(Document).document_text


def test_the_readme_plan_places_what_the_project_is(runs_dir: Path) -> None:
    text = planning_readme(runs_dir, [SUMMARY, FIELD, PERIOD])
    assert SUMMARY.summary_text is not None and SUMMARY.summary_text in text
    assert "Ecohydrology" in text


def test_without_the_project_described_the_readme_plan_is_as_it_was(runs_dir: Path) -> None:
    assert planning_readme(runs_dir, [LICENCE]) == planning_readme(runs_dir, [])


def test_the_plan_places_what_the_project_is_and_when_it_runs(runs_dir: Path) -> None:
    given = dmp_asked(project_decisions=[SUMMARY, PERIOD])
    _, plan = draft_plan(runs_dir, redrafted(given))
    assert plan.document_stage == "draft"
    assert SUMMARY.summary_text is not None and SUMMARY.summary_text in plan.document_text
    assert "2027-01 to 2029-12" in plan.document_text


def test_only_the_project_kinds_are_drafted_from() -> None:
    assert project([LICENCE]) is None
    described = project([SUMMARY, LICENCE])
    assert described is not None and "CC-BY-4.0" not in described
