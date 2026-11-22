"""advisor.dmp reads an attached data management plan's sharing commitments, proposes each as a
project fact quoting the passage it rests on, and compares only what a person confirmed (#962;
docs/specs/projects.md, invariant 28), reading only the document marked as the plan and proposing
which document is the plan when none is (#1447, invariant 32). Every model here is a `FakeModel`;
no key is needed."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dd_agent_advisor_dmp.agent import DmpChecker
from dd_agent_advisor_dmp.classes import DmpCommitments, DmpDiscrepancies, SharingCommitment
from dd_agent_advisor_dmp.match import ModelMatcher
from dd_agent_advisor_dmp.read_plan import MAX_PLAN, ModelReader, confirmed, fitted
from dd_harness.conductor import Conductor
from dd_harness.projects import FactVerdict, ProjectStore
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.contract.facts import PLAN_SUBJECT, FactKind, ProjectDocument, ProjectFact
from dd_sdk.contract.models import Envelope, GroundingMode, OutcomeStatus, ReasonCode
from dd_sdk.model import declared
from dd_sdk.testing import FakeModel

PLAN = (
    "Data sharing. The anonymised interview transcripts will be deposited in the UK Data Service "
    "under safeguarded access at the end of the project. Survey responses will be shared openly "
    "in ORDA under CC BY 4.0. Consent forms will not be shared."
)


def plan(text: str = PLAN, name: str = "dmp.md") -> ProjectDocument:
    return ProjectDocument(
        documentation_name=name,
        documentation_digest=hashlib.sha256(text.encode()).hexdigest(),
        documentation_media_type="text/plain",
        documentation_size=len(text.encode()),
        documentation_added_at=datetime(2026, 11, 1, tzinfo=UTC),
        documentation_text=text,
    )


def reply(commitments: list[dict[str, object]], *, vague: bool = False) -> str:
    return json.dumps({"commitments": commitments, "vague": vague})


def commitment(output: str, quote: str, **aspects: str | None) -> dict[str, object]:
    found = {"repository": None, "access": None, "licence": None, **aspects}
    return {"output": output, "document": 1, "quote": quote, **found}


READ = reply(
    [
        commitment(
            "Anonymised interview transcripts",
            "The anonymised interview transcripts will be deposited in the UK Data Service under "
            "safeguarded access",
            repository="UK Data Service",
            access="safeguarded",
        ),
        commitment(
            "Survey responses",
            "Survey responses will be shared openly in ORDA under CC BY 4.0.",
            repository="ORDA",
            access="open",
            licence="CC BY 4.0",
        ),
    ]
)


def commitments_of(payload: DmpDiscrepancies) -> list[ProjectFact]:
    """The sharing commitments proposed, without the proposal of which document is the plan."""
    return [f for f in payload.proposed_facts if f.fact_kind == FactKind.SHARING_COMMITMENT]


def checker(model: FakeModel) -> DmpChecker:
    """Built as the factory builds it with a model."""
    agent = DmpChecker(ModelMatcher(model), ModelReader(model))
    agent.spec = replace(agent.spec, models=(declared(model),))
    return agent


def run(runs_dir: Path, agent: DmpChecker, asked: DmpCommitments) -> Envelope:
    return make_conductor(runs_dir, agent).invoke(
        request("advisor.dmp", asked), acting_for=TEST_PRINCIPAL
    )


@pytest.mark.requirement("DD-GROUNDING-MODE", "DD-GROUNDED-PAYLOAD")
def test_a_plans_commitments_are_proposed_with_their_passages_and_nothing_is_compared(
    runs_dir: Path,
) -> None:
    asked = DmpCommitments(project_documents=[plan()])
    env = run(runs_dir, checker(FakeModel(READ)), asked)

    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.grounding_mode == GroundingMode.INPUT_ONLY
    payload = env.payload_as(DmpDiscrepancies)
    assert payload.discrepancies == []
    proposed = commitments_of(payload)
    assert {f.fact_subject for f in proposed} == {
        "Anonymised interview transcripts",
        "Survey responses",
    }
    for fact in proposed:
        assert fact.fact_kind == FactKind.SHARING_COMMITMENT
        assert fact.commitment_document == plan().documentation_digest
        assert fact.commitment_quote and fact.commitment_quote.split()[0] in PLAN
    survey = next(f for f in proposed if f.fact_subject == "Survey responses")
    assert (survey.commitment_repository, survey.commitment_licence) == ("ORDA", "CC BY 4.0")


def test_a_commitment_whose_quote_is_not_in_the_plan_is_not_proposed(runs_dir: Path) -> None:
    invented = reply(
        [
            commitment("Survey responses", "Survey responses will be shared openly in ORDA"),
            commitment("Code", "All analysis code will be released on GitHub under MIT."),
        ]
    )
    env = run(runs_dir, checker(FakeModel(invented)), DmpCommitments(project_documents=[plan()]))

    payload = env.payload_as(DmpDiscrepancies)
    assert [f.fact_subject for f in commitments_of(payload)] == ["Survey responses"]
    assert len(payload.dropped) == 1 and "Code" in payload.dropped[0]


def test_a_commitment_to_several_repositories_is_one_for_each(runs_dir: Path) -> None:
    """A plan that deposits an output in one repository and offers a copy to another gives a
    commitment for each, kept apart by repository; only a repeat of both is named twice (#1334).
    What a person confirms is compared as the output the plan names."""
    text = (
        "Audio masters will be deposited in the Wharfedale Research Data Repository and a copy "
        "offered to the Netherbrook Local Studies Archive."
    )
    both = ["Wharfedale Research Data Repository", "Netherbrook Local Studies Archive"]
    read = reply([commitment("Audio masters", text, repository=name) for name in [*both, both[0]]])
    env = run(runs_dir, checker(FakeModel(read)), DmpCommitments(project_documents=[plan(text)]))

    payload = env.payload_as(DmpDiscrepancies)
    facts = commitments_of(payload)
    assert [f.commitment_repository for f in facts] == both
    assert len({f.fact_subject for f in facts}) == len(both)
    assert len(payload.dropped) == 1
    decided = confirmed(DmpCommitments(project_decisions=facts))
    assert [(c.output, c.repository) for c in decided] == [("Audio masters", r) for r in both]


@pytest.mark.parametrize("vague", [False, True], ids=["none-found", "too-vague"])
def test_a_plan_with_no_commitment_is_a_result_not_a_failure(runs_dir: Path, vague: bool) -> None:
    env = run(
        runs_dir,
        checker(FakeModel(reply([], vague=vague))),
        DmpCommitments(project_documents=[plan("We will consider sharing where appropriate.")]),
    )
    assert env.outcome.status == OutcomeStatus.SUCCEEDED
    assert env.payload_as(DmpDiscrepancies).proposed_facts == []


def test_without_a_model_a_plan_is_not_read(runs_dir: Path) -> None:
    env = run(runs_dir, DmpChecker(), DmpCommitments(project_documents=[plan()]))
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.CAPABILITY_NOT_IMPLEMENTED


def test_a_model_that_declines_proposes_nothing(runs_dir: Path) -> None:
    env = run(runs_dir, checker(FakeModel(refuse=True)), DmpCommitments(project_documents=[plan()]))
    assert env.outcome.status == OutcomeStatus.SUCCEEDED
    assert env.payload_as(DmpDiscrepancies).proposed_facts == []


def test_long_plans_are_given_latest_first_and_cut_to_fit() -> None:
    older, newer = plan("o" * MAX_PLAN, "old.md"), plan("n" * (MAX_PLAN // 2), "new.md")
    given, cut = fitted([older, newer])
    assert [d.documentation_name for d in given] == ["new.md", "old.md"]
    assert cut == {"old.md"}
    assert sum(len(d.documentation_text) for d in given) == MAX_PLAN


# --- In a project: proposed, decided, then compared ----------------------------------------------


def in_project(runs_dir: Path, tmp_path: Path, agent: DmpChecker) -> tuple[Conductor, str, str]:
    conductor = make_conductor(runs_dir, agent)
    projects = ProjectStore(tmp_path / "projects")
    conductor.projects = projects
    project = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    projects.add_documentation(
        project, "dmp.md", "text/markdown", PLAN, acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    return conductor, project, conversation


def ask(conductor: Conductor, conversation: str, asked: DmpCommitments) -> Envelope:
    req = request("advisor.dmp", asked).model_copy(update={"conversation_id": conversation})
    return conductor.invoke(req, acting_for=TEST_PRINCIPAL)


def test_in_a_project_only_the_commitments_a_person_confirmed_are_compared(
    runs_dir: Path, tmp_path: Path
) -> None:
    """The conductor gives the checker the attached plan by its mixin's slot; the checker's
    proposals wait for a person; what they confirm, as they corrected it, is compared."""
    model = FakeModel(READ, hosting="local")
    conductor, project, conversation = in_project(runs_dir, tmp_path, checker(model))
    planned = [
        SharingCommitment(
            output="Survey responses", repository="Zenodo", access="open", licence="CC0"
        )
    ]

    first = ask(conductor, conversation, DmpCommitments(planned_outputs=planned))
    assert first.outcome.status == OutcomeStatus.SUCCEEDED, first.outcome.statement
    assert PLAN in str(model.sent[0].messages)  # given the plan by its slot
    projects = conductor.projects
    assert isinstance(projects, ProjectStore)
    proposals = {
        p["fact"]["fact_subject"]: p["proposal"]
        for p in projects.proposals(project)
        if p["fact"]["fact_kind"] == FactKind.SHARING_COMMITMENT
    }
    assert set(proposals) == {"Anonymised interview transcripts", "Survey responses"}

    # Nothing is compared until a person decides: the next run proposes again.
    again = ask(conductor, conversation, DmpCommitments(planned_outputs=planned))
    assert again.payload_as(DmpDiscrepancies).discrepancies == []
    proposals = {p["fact"]["fact_subject"]: p["proposal"] for p in projects.proposals(project)}

    # The researcher corrects one commitment's repository and rejects the other.
    survey = projects.proposal(project, proposals["Survey responses"])
    assert survey is not None
    projects.decide_fact(
        project,
        FactVerdict.CHANGED,
        proposal=proposals["Survey responses"],
        fact={**survey, "commitment_repository": "Zenodo"},
        acted_for=TEST_PRINCIPAL,
        caused_by="test",
    )
    projects.decide_fact(
        project,
        FactVerdict.REJECTED,
        proposal=proposals["Anonymised interview transcripts"],
        acted_for=TEST_PRINCIPAL,
        caused_by="test",
    )

    checked = ask(conductor, conversation, DmpCommitments(planned_outputs=planned))
    payload = checked.payload_as(DmpDiscrepancies)
    assert payload.proposed_facts == []
    # The corrected repository matches, the licence does not, and the rejected output is not a
    # commitment at all.
    assert {(d.output, d.aspect) for d in payload.discrepancies} == {
        ("Survey responses", "licence")
    }


def test_a_hosted_model_is_not_given_the_plan_by_default(runs_dir: Path, tmp_path: Path) -> None:
    """The plan's text is `documentation`, which the default `hosted_models` keeps from a hosted
    model: it is left out, so the checker asks for the commitments instead."""
    model = FakeModel(READ, hosting="hosted")
    conductor, _, conversation = in_project(runs_dir, tmp_path, checker(model))
    env = ask(conductor, conversation, DmpCommitments())
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert model.sent == []


NOTES = "Field notes. Survey responses will be shared openly in Zenodo under CC0 at some point."


def test_only_the_document_marked_as_the_plan_is_read(runs_dir: Path) -> None:
    """When a person has marked one attached document as the project's plan (#1447), the
    reader is given that document alone, and no other is proposed as the plan."""
    model = FakeModel(READ)
    marked = plan().model_copy(update={"documentation_is_plan": True})
    asked = DmpCommitments(project_documents=[marked, plan(NOTES, name="notes.md")])

    env = run(runs_dir, checker(model), asked)

    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    sent = str(model.sent[0].messages)
    assert PLAN in sent and NOTES not in sent
    kinds = {f.fact_kind for f in env.payload_as(DmpDiscrepancies).proposed_facts}
    assert FactKind.DATA_MANAGEMENT_PLAN not in kinds


def test_with_no_plan_marked_the_document_read_is_proposed_as_the_plan(runs_dir: Path) -> None:
    """With no plan marked, the checker proposes the document the commitments were quoted from
    as the project's plan, for a person to confirm."""
    # Given the latest first, so the plan, attached last, is the reader's document 1.
    asked = DmpCommitments(project_documents=[plan(NOTES, name="notes.md"), plan()])
    env = run(runs_dir, checker(FakeModel(READ)), asked)

    proposed = env.payload_as(DmpDiscrepancies).proposed_facts
    (marked,) = [f for f in proposed if f.fact_kind == FactKind.DATA_MANAGEMENT_PLAN]
    assert marked.fact_subject == PLAN_SUBJECT
    assert marked.plan_document == plan().documentation_digest
    assert marked.proposed_because


def test_in_a_project_a_confirmed_plan_proposal_marks_the_plan(
    runs_dir: Path, tmp_path: Path
) -> None:
    """The checker's proposal of the plan waits for a person; once they confirm it, the
    conductor gives the checker that document as the plan."""
    model = FakeModel(READ, hosting="local")
    conductor, project, conversation = in_project(runs_dir, tmp_path, checker(model))
    ask(conductor, conversation, DmpCommitments())
    projects = conductor.projects
    assert isinstance(projects, ProjectStore)
    (offered,) = [
        p
        for p in projects.proposals(project)
        if p["fact"]["fact_kind"] == FactKind.DATA_MANAGEMENT_PLAN
    ]
    projects.decide_fact(
        project,
        FactVerdict.CONFIRMED,
        proposal=offered["proposal"],
        acted_for=TEST_PRINCIPAL,
        caused_by="test",
    )
    (listed,) = projects.documentation(project)
    assert listed.get("documentation_is_plan") is True

    again = ask(conductor, conversation, DmpCommitments())
    kinds = {f.fact_kind for f in again.payload_as(DmpDiscrepancies).proposed_facts}
    assert FactKind.DATA_MANAGEMENT_PLAN not in kinds
