"""Each recommendation is proposed as a `standard` project fact for the researcher to choose
(docs/specs/projects.md, #1391): named as the record it cites names it, for what it was
recommended, and chosen only by a person."""

from __future__ import annotations

from pathlib import Path

from dd_agent_advisor_standards import testing as fakes
from dd_agent_advisor_standards.classes import Recommendations
from dd_agent_advisor_standards.propose import STANDARD_KINDS, subject
from dd_harness.testing import TEST_PRINCIPAL
from dd_sdk.contract.facts import FactKind
from dd_sdk.contract.models import OutcomeStatus


def recommended(runs_dir: Path) -> Recommendations:
    conductor = fakes.make_conductor(runs_dir, crate=False)
    env = conductor.invoke(fakes.request("advisor.standards"), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    payload: Recommendations = env.payload_as(Recommendations)
    return payload


def test_each_recommendation_is_proposed_once_for_what_it_was_recommended(
    runs_dir: Path,
) -> None:
    payload = recommended(runs_dir)
    proposals = payload.proposed_facts
    assert proposals
    assert all(p.fact_kind == FactKind.STANDARD for p in proposals)
    assert len({p.fact_subject for p in proposals}) == len(proposals)
    proposed = {(p.standard_target, p.standard_kind) for p in proposals}
    assert {(i.target, STANDARD_KINDS[i.kind]) for i in payload.items} == proposed


def test_a_proposal_says_why_and_names_an_identifier(runs_dir: Path) -> None:
    for proposal in recommended(runs_dir).proposed_facts:
        assert proposal.proposed_because
        assert proposal.standard_id and proposal.standard_id.startswith("https://")


def test_a_standard_for_one_field_is_decided_apart_from_the_dataset() -> None:
    assert subject("ISO 8601", "dataset") != subject("ISO 8601", "field:sampled_at")
    assert subject("AGROVOC", "dataset") == "AGROVOC"
