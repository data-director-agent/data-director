"""advisor.dmp describes a project before its data are collected (`setup.project`): it proposes
what the researcher said, and with a model what an attached proposal says, as project facts for a
person to confirm, each read from a document quoting its passage; it proposes nothing already
decided, and says what is still needed (docs/specs/projects.md, invariant 28). Every model here is
a `FakeModel`; no key is needed."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from dd_agent_advisor_dmp.agent import DmpChecker
from dd_agent_advisor_dmp.classes import DmpDiscrepancies, ProjectDescriptionRequest
from dd_agent_advisor_dmp.describe import ModelDescriber
from dd_harness.conductor import Conductor
from dd_harness.projects import ProjectStore
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.contract.facts import PLAN_SUBJECT, FactKind, ProjectDocument, ProjectFact
from dd_sdk.contract.models import Envelope, OutcomeStatus
from dd_sdk.model import declared
from dd_sdk.testing import FakeModel

PROPOSAL = (
    "Case for support. This project asks how upland peat bogs respond to summer drought. It sits "
    "in ecohydrology. The project will run from 2027-01 to 2029-12. We will log water-table depth "
    "every 15 minutes with pressure transducers at 12 sites, saved as CSV files."
)


def proposal(text: str = PROPOSAL, name: str = "proposal.md") -> ProjectDocument:
    return ProjectDocument(
        documentation_name=name,
        documentation_digest=hashlib.sha256(text.encode()).hexdigest(),
        documentation_media_type="text/markdown",
        documentation_size=len(text.encode()),
        documentation_added_at=datetime(2026, 11, 1, tzinfo=UTC),
        documentation_text=text,
    )


def reply(**found: Any) -> str:
    return json.dumps(
        {"summary": None, "field_of_study": None, "period": None, "data": None, **found}
    )


READ = reply(
    summary={
        "text": "The project studies how upland peat bogs respond to summer drought.",
        "document": 1,
        "quote": "This project asks how upland peat bogs respond to summer drought.",
    },
    field_of_study={"name": "Ecohydrology", "document": 1, "quote": "It sits in ecohydrology."},
    period={
        "start": "2027-01",
        "end": "2029-12",
        "document": 1,
        "quote": "The project will run from 2027-01 to 2029-12.",
    },
    data={
        "collected": "Water-table depth every 15 minutes at 12 sites.",
        "collection_method": "Pressure transducers",
        "formats": "CSV",
        "volume": None,
        "reused": None,
        "document": 1,
        "quote": "We will log water-table depth every 15 minutes with pressure transducers",
    },
)


def planner(model: FakeModel) -> DmpChecker:
    """Built as the factory builds it with a model."""
    agent = DmpChecker(describer=ModelDescriber(model))
    agent.spec = replace(agent.spec, models=(declared(model),))
    return agent


def run(runs_dir: Path, agent: DmpChecker, asked: ProjectDescriptionRequest) -> Envelope:
    return make_conductor(runs_dir, agent).invoke(
        request("advisor.dmp", asked), acting_for=TEST_PRINCIPAL
    )


def kinds(payload: DmpDiscrepancies) -> dict[FactKind, list[ProjectFact]]:
    found: dict[FactKind, list[ProjectFact]] = {}
    for fact in payload.proposed_facts:
        found.setdefault(fact.fact_kind, []).append(fact)
    return found


def test_the_card_serves_describing_the_project_and_accepts_its_request() -> None:
    spec = DmpChecker.spec
    assert "setup.project" in spec.serves
    assert "ProjectDescriptionRequest" in {c.name for c in spec.accepts}


@pytest.mark.requirement("DD-GROUNDING-MODE", "DD-GROUNDED-PAYLOAD")
def test_a_proposal_is_read_into_facts_each_quoting_its_passage(runs_dir: Path) -> None:
    asked = ProjectDescriptionRequest(project_documents=[proposal()])
    env = run(runs_dir, planner(FakeModel(READ)), asked)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    payload = env.payload_as(DmpDiscrepancies)
    found = kinds(payload)
    assert set(found) == {
        FactKind.PROJECT_SUMMARY,
        FactKind.FIELD_OF_STUDY,
        FactKind.PROJECT_PERIOD,
        FactKind.DATA_DESCRIPTION,
    }
    for fact in payload.proposed_facts:
        assert fact.proposed_because is not None and "proposal.md" in fact.proposed_because
    assert found[FactKind.PROJECT_SUMMARY][0].fact_subject == PLAN_SUBJECT
    assert found[FactKind.DATA_DESCRIPTION][0].data_collection_method == "Pressure transducers"
    assert payload.still_needed == []


def test_a_reading_whose_quote_is_not_in_the_document_is_dropped(runs_dir: Path) -> None:
    invented = reply(
        field_of_study={"name": "Glaciology", "document": 1, "quote": "It sits in glaciology."},
        period={"start": "next spring", "end": None, "document": 1, "quote": PROPOSAL[:40]},
    )
    asked = ProjectDescriptionRequest(project_documents=[proposal()])
    payload = run(runs_dir, planner(FakeModel(invented)), asked).payload_as(DmpDiscrepancies)
    assert payload.proposed_facts == []
    assert len(payload.dropped) == 2
    assert FactKind.FIELD_OF_STUDY not in kinds(payload)


def test_what_the_researcher_said_is_proposed_first_and_the_rest_is_asked(
    runs_dir: Path,
) -> None:
    """Without a model nothing is read; what they said is proposed, and the gaps are named."""
    asked = ProjectDescriptionRequest(
        research_summary="How peat bogs respond to drought.",
        field_of_study="Ecohydrology",
        project_documents=[proposal()],
    )
    env = run(runs_dir, DmpChecker(), asked)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED
    payload = env.payload_as(DmpDiscrepancies)
    assert set(kinds(payload)) == {FactKind.PROJECT_SUMMARY, FactKind.FIELD_OF_STUDY}
    assert len(payload.still_needed) == 2  # the data and the period
    assert env.telemetry.model_calls == []


def test_the_researchers_words_outrank_a_reading_of_the_same_thing(runs_dir: Path) -> None:
    asked = ProjectDescriptionRequest(
        research_summary="In my words.", project_documents=[proposal()]
    )
    payload = run(runs_dir, planner(FakeModel(READ)), asked).payload_as(DmpDiscrepancies)
    summaries = kinds(payload)[FactKind.PROJECT_SUMMARY]
    assert [f.summary_text for f in summaries] == ["In my words."]


def test_nothing_already_decided_is_proposed_again(runs_dir: Path) -> None:
    decided = [
        ProjectFact(
            fact_kind=FactKind.PROJECT_SUMMARY, fact_subject=PLAN_SUBJECT, summary_text="Decided."
        ),
        ProjectFact(
            fact_kind=FactKind.DATA_DESCRIPTION,
            fact_subject=PLAN_SUBJECT,
            data_collected="Decided.",
        ),
    ]
    asked = ProjectDescriptionRequest(project_documents=[proposal()], project_decisions=decided)
    payload = run(runs_dir, planner(FakeModel(READ)), asked).payload_as(DmpDiscrepancies)
    assert set(kinds(payload)) == {FactKind.FIELD_OF_STUDY, FactKind.PROJECT_PERIOD}


def in_project(runs_dir: Path, tmp_path: Path, agent: DmpChecker) -> tuple[Conductor, str, str]:
    conductor = make_conductor(runs_dir, agent)
    projects = ProjectStore(tmp_path / "projects")
    conductor.projects = projects
    project = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    projects.add_documentation(
        project, "proposal.md", "text/markdown", PROPOSAL, acted_for=TEST_PRINCIPAL, caused_by="t"
    )
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    return conductor, project, conversation


def test_in_a_project_the_proposals_wait_for_a_person_and_start_the_step(
    runs_dir: Path, tmp_path: Path
) -> None:
    model = FakeModel(READ, hosting="local")
    conductor, project, conversation = in_project(runs_dir, tmp_path, planner(model))
    req = request("advisor.dmp", ProjectDescriptionRequest()).model_copy(
        update={"conversation_id": conversation}
    )
    env = conductor.invoke(req, acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert PROPOSAL in str(model.sent[0].messages)  # given the proposal by its slot
    projects = conductor.projects
    assert isinstance(projects, ProjectStore)
    proposed = {p["fact"]["fact_kind"] for p in projects.proposals(project)}
    assert FactKind.PROJECT_SUMMARY in proposed
    assert projects.progress(project)["steps"].get("setup.project") == "started"
