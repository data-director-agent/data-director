"""The Standards Librarian fills what its profile leaves empty from the facts people in the
project decided (#1529, docs/specs/projects.md): the field of study becomes the subject it searches
on, and the description of the data, or else the summary of the project, the description its model
reads. A value the input gives stands, nothing is inferred, and the result says what came from the
record."""

from __future__ import annotations

from pathlib import Path

from dd_agent_advisor_standards import testing as fakes
from dd_agent_advisor_standards.agent import StandardsAgent
from dd_agent_advisor_standards.classes import DatasetProfile, Recommendations
from dd_agent_advisor_standards.decided import filled
from dd_agent_advisor_standards.explain import TemplateExplainer
from dd_harness.projects import FactVerdict, ProjectStore
from dd_harness.testing import TEST_PRINCIPAL
from dd_sdk.contract.facts import PLAN_SUBJECT, FactKind, ProjectFact
from dd_sdk.contract.models import OutcomeStatus, ReasonCode

FIELD = ProjectFact(
    fact_kind=FactKind.FIELD_OF_STUDY, fact_subject=PLAN_SUBJECT, field_name="Soil science"
)
DATA = ProjectFact(
    fact_kind=FactKind.DATA_DESCRIPTION,
    fact_subject=PLAN_SUBJECT,
    data_collected="Soil cores analysed for carbon and nitrogen.",
    data_formats="CSV tables",
)
SUMMARY = ProjectFact(
    fact_kind=FactKind.PROJECT_SUMMARY,
    fact_subject=PLAN_SUBJECT,
    summary_text="How land use changes soil carbon.",
)
LICENCE = ProjectFact(fact_kind=FactKind.LICENCE, fact_subject="licence", licence_id="CC-BY-4.0")


def test_a_decided_field_of_study_is_the_subject_when_none_is_given() -> None:
    profile, taken = filled(DatasetProfile(project_decisions=[FIELD]))
    assert profile.themes == ["Soil science"]
    assert len(taken) == 1 and "Soil science" in taken[0]


def test_a_subject_the_input_gives_stands() -> None:
    given = DatasetProfile(keywords=["peat"], project_decisions=[FIELD])
    profile, taken = filled(given)
    assert profile.themes == [] and profile.keywords == ["peat"]
    assert taken == []


def test_the_description_of_the_data_comes_before_the_summary_and_infers_no_format() -> None:
    profile, taken = filled(DatasetProfile(project_decisions=[SUMMARY, DATA]))
    assert profile.description is not None
    assert DATA.data_collected is not None and DATA.data_collected in profile.description
    assert profile.media_types == []
    assert len(taken) == 1
    alone, _ = filled(DatasetProfile(project_decisions=[SUMMARY]))
    assert alone.description == SUMMARY.summary_text


def test_other_decided_facts_fill_nothing() -> None:
    profile = DatasetProfile(project_decisions=[LICENCE])
    assert filled(profile) == (profile, [])


def test_with_no_subject_and_no_decided_field_it_still_abstains(runs_dir: Path) -> None:
    conductor = fakes.make_conductor(runs_dir, crate=False)
    env = conductor.invoke(
        fakes.request("advisor.standards", DatasetProfile(project_decisions=[LICENCE])),
        acting_for=TEST_PRINCIPAL,
    )
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.INSUFFICIENT_INPUT


def test_in_a_project_the_decided_field_of_study_is_searched_on(
    runs_dir: Path, tmp_path: Path
) -> None:
    """The conductor gives the profile the project's decisions by its mixin's slot, so a profile
    with no subject searches on the field people decided, and the result says so."""
    retrieval = fakes.FakeRetrieval()
    agent = StandardsAgent(retrieval=retrieval, explainer=TemplateExplainer())
    conductor = fakes.make_conductor(runs_dir, agent, crate=False)
    projects = ProjectStore(tmp_path / "projects")
    conductor.projects = projects
    project = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    projects.decide_fact(
        project,
        FactVerdict.CHANGED,
        fact=FIELD.model_dump(mode="json", exclude_none=True),
        acted_for=TEST_PRINCIPAL,
        caused_by="test",
    )
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    req = fakes.request("advisor.standards", DatasetProfile()).model_copy(
        update={"conversation_id": conversation}
    )
    env = conductor.invoke(req, acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert any("Soil science" in q.text for q in retrieval.queries)
    searched = env.payload_as(Recommendations).searched
    assert searched is not None and searched.from_project_record
    assert "From the project record" in env.outcome.statement
