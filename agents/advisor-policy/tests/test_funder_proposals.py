"""Each funder identified in ROR is proposed as a funder project fact (`propose.py`,
docs/specs/projects.md): with its ROR identifier and Crossref Funder ID from the record cited in
the run, never for a name ROR gives to more than one organisation, and never again for a funder
already decided with a ROR identifier."""

from __future__ import annotations

from pathlib import Path

import pytest
from opf_fixture import opf_finding_nothing
from ror_fixture import NERC, build_fixture
from test_policy_agent import FakePolicies, RecordingPolicies, invoke, nerc_only

from dd_agent_advisor_policy import propose
from dd_agent_advisor_policy.agent import PolicyAgent
from dd_agent_advisor_policy.classes import Actor, ActorRole, PolicyChecks, PolicyContext
from dd_agent_advisor_policy.ror import RorDump
from dd_agent_advisor_policy.search import Sources
from dd_sdk.contract.facts import FactKind, ProjectFact
from dd_sdk.contract.models import OutcomeStatus

NERC_FUNDER_ID = "https://doi.org/10.13039/501100000270"


@pytest.fixture(scope="module")
def dump(tmp_path_factory: pytest.TempPathFactory) -> RorDump:
    return build_fixture(tmp_path_factory.mktemp("ror"))


def checks(runs_dir: Path, advisor: PolicyAgent, context: PolicyContext) -> PolicyChecks:
    env = invoke(runs_dir, context, advisor)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    return env.payload_as(PolicyChecks)


def nerc(name: str = "NERC") -> Actor:
    return Actor(role=ActorRole.FUNDER, name=name)


def decided(name: str, ror: str | None = None) -> ProjectFact:
    return ProjectFact(
        fact_kind=FactKind.FUNDER, fact_subject=name, fact_funder_name=name, fact_funder_ror=ror
    )


def test_a_funder_resolved_in_ror_is_proposed_with_both_identifiers(
    runs_dir: Path, dump: RorDump
) -> None:
    advisor = PolicyAgent(Sources(RecordingPolicies(), organisations=nerc_only(dump)))
    payload = checks(runs_dir, advisor, PolicyContext(actors=[nerc()]))
    (fact,) = payload.proposed_facts
    assert fact.fact_kind == FactKind.FUNDER
    assert fact.fact_subject == "NERC"
    assert (str(fact.fact_funder_ror), str(fact.fact_crossref_funder_id)) == (
        NERC,
        NERC_FUNDER_ID,
    )
    assert fact.fact_funder_name and fact.proposed_because
    # The identifiers come from a ROR record the payload cites.
    assert NERC in {g.source_id for g in payload.grounded_on}


def test_a_funder_with_no_policy_record_is_still_proposed(runs_dir: Path, dump: RorDump) -> None:
    advisor = PolicyAgent(
        Sources(FakePolicies(), organisations=nerc_only(dump), opf=opf_finding_nothing())
    )
    payload = checks(runs_dir, advisor, PolicyContext(actors=[nerc()]))
    assert [str(f.fact_funder_ror) for f in payload.proposed_facts] == [NERC]


def test_an_ambiguous_name_is_not_proposed(runs_dir: Path, dump: RorDump) -> None:
    advisor = PolicyAgent(Sources(RecordingPolicies(), organisations=dump))
    payload = checks(runs_dir, advisor, PolicyContext(actors=[nerc()]))
    assert payload.ambiguous and payload.proposed_facts == []


def test_a_funder_decided_with_a_ror_identifier_is_not_proposed_again(
    runs_dir: Path, dump: RorDump
) -> None:
    advisor = PolicyAgent(Sources(RecordingPolicies(), organisations=dump))
    context = PolicyContext(project_decisions=[decided("NERC", ror=NERC)])
    payload = checks(runs_dir, advisor, context)
    assert payload.funders and payload.proposed_facts == []


def test_a_funder_decided_by_name_alone_is_proposed_under_its_subject(
    runs_dir: Path, dump: RorDump
) -> None:
    advisor = PolicyAgent(Sources(RecordingPolicies(), organisations=dump))
    name = "Natural Environment Research Council"
    payload = checks(runs_dir, advisor, PolicyContext(project_decisions=[decided(name)]))
    (fact,) = payload.proposed_facts
    assert (fact.fact_subject, str(fact.fact_funder_ror)) == (name, NERC)


def test_one_funder_named_twice_is_proposed_once(dump: RorDump) -> None:
    org = dump.get(NERC)
    assert org is not None
    resolved = [(nerc(), org), (nerc("Natural Environment Research Council"), org)]
    assert len(propose.proposals(resolved, [], "ror")) == 1


def test_a_crossref_funder_id_is_written_as_a_doi_url(dump: RorDump) -> None:
    org = dump.get(NERC)
    assert org is not None
    assert propose.crossref_funder_id(org) == NERC_FUNDER_ID
    assert (
        propose.crossref_funder_id(org.model_copy(update={"crossref_funder_preferred": None}))
        is None
    )
