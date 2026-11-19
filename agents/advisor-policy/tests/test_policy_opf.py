"""The policy advisor with Open Policy Finder and Crossref, through the conductor, without a model:
the cases the pilot workshop found nothing for (NERC, #750; an Elsevier journal, #905)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from opf_fixture import (
    ELSEVIER_OPF,
    NERC_OPF,
    STOTEN_CROSSREF,
    STOTEN_OPF,
    crossref,
    crossref_handler,
    opf,
    opf_handler,
)
from ror_fixture import NERC, build_fixture
from test_policy_agent import ALL, TESTING, FakeOrganisations, FakePolicies, invoke

from dd_agent_advisor_policy.agent import PolicyAgent
from dd_agent_advisor_policy.classes import (
    Actor,
    ActorRole,
    PolicyChecks,
    PolicyContext,
    PolicyRegistry,
)
from dd_agent_advisor_policy.records import PolicyRecord
from dd_agent_advisor_policy.ror import RorDump
from dd_sdk.contract.models import Derivation, OutcomeStatus
from dd_sdk.evidence import verify

ELSEVIER_POLICY = PolicyRecord(
    fairsharing_id="FAIRsharing.test-elsevier",
    name="Elsevier - Research Data Policy",
    policy_type="journal_publisher",
    subjects=["Subject Agnostic"],
)
NERC_ACTOR = Actor(role=ActorRole.FUNDER, name="NERC")
STOTEN_ACTOR = Actor(role=ActorRole.JOURNAL, name="Science of the Total Environment")


@pytest.fixture(scope="module")
def dump(tmp_path_factory: pytest.TempPathFactory) -> RorDump:
    return build_fixture(tmp_path_factory.mktemp("ror"))


def nerc_only(dump: RorDump) -> FakeOrganisations:
    org = dump.get(NERC)
    assert org is not None
    return FakeOrganisations([org])


@pytest.mark.requirement("DD-GROUNDED-PAYLOAD", "DD-EVIDENCE")
def test_nerc_with_no_fairsharing_record_is_found_in_open_policy_finder(
    runs_dir: Path, dump: RorDump
) -> None:
    advisor = PolicyAgent(FakePolicies(), organisations=nerc_only(dump), opf=opf())
    env = invoke(runs_dir, PolicyContext(actors=[NERC_ACTOR]), advisor)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    checks = env.payload_as(PolicyChecks)
    [policy] = checks.policies
    assert (policy.actor, policy.registry, policy.match_derivation) == (
        "NERC",
        PolicyRegistry.OPEN_POLICY_FINDER,
        Derivation.REGISTRY,
    )
    assert policy.grounded_on[0].source_id == NERC_OPF
    assert checks.no_record == []
    # Without a model, nothing is read from the record's text: it says so, and states nothing.
    assert policy.obligations == []
    assert "no obligation was read from it by rule" in policy.rationale
    evidence = {e.source_id: e for e in env.evidence}
    assert (evidence[NERC_OPF].snapshot_ref or "").startswith("open-policy-finder:live:")
    content = evidence[NERC_OPF].content
    assert content is not None
    assert verify(content, evidence[NERC_OPF].canonicalisation, evidence[NERC_OPF].content_hash)
    assert "Open Policy Finder" in env.outcome.statement


@pytest.mark.requirement("DD-GROUNDED-PAYLOAD")
def test_an_elsevier_journal_reaches_its_publishers_policy(runs_dir: Path) -> None:
    advisor = PolicyAgent(FakePolicies([*ALL, ELSEVIER_POLICY]), opf=opf(), crossref=crossref())
    env = invoke(runs_dir, PolicyContext(actors=[STOTEN_ACTOR]), advisor)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    checks = env.payload_as(PolicyChecks)
    assert sorted(p.grounded_on[0].source_id for p in checks.policies) == sorted(
        ["FAIRsharing.test-elsevier", STOTEN_OPF]
    )
    [journal] = checks.journals
    assert (journal.actor, journal.publisher, journal.issn) == (
        STOTEN_ACTOR.name,
        "Elsevier",
        "0048-9697",
    )
    assert [g.source_id for g in journal.grounded_on] == [STOTEN_OPF]
    assert checks.no_record == []
    assert "published by Elsevier" in env.outcome.statement


def test_without_open_policy_finder_crossref_still_reaches_the_publisher(runs_dir: Path) -> None:
    advisor = PolicyAgent(FakePolicies([*ALL, ELSEVIER_POLICY]), crossref=crossref())
    env = invoke(runs_dir, PolicyContext(actors=[STOTEN_ACTOR]), advisor)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    checks = env.payload_as(PolicyChecks)
    assert [p.grounded_on[0].source_id for p in checks.policies] == ["FAIRsharing.test-elsevier"]
    assert [g.source_id for g in checks.journals[0].grounded_on] == [STOTEN_CROSSREF]
    assert checks.journals[0].publisher == "Elsevier BV"
    assert "no OPEN_POLICY_FINDER_API_KEY" in env.outcome.statement


def test_a_journal_given_by_issn_is_read_by_it(runs_dir: Path) -> None:
    seen: list[httpx.Request] = []
    advisor = PolicyAgent(FakePolicies(), opf=opf(opf_handler(seen)))
    actor = Actor(role=ActorRole.JOURNAL, name="STOTEN", issn="0048-9697")
    checks = invoke(runs_dir, PolicyContext(actors=[actor]), advisor).payload_as(PolicyChecks)
    assert [p.grounded_on[0].source_id for p in checks.policies] == [STOTEN_OPF]
    assert seen[0].url.params["identifier"] == "0048-9697"


@pytest.mark.requirement("DD-OUTCOME")
def test_an_ambiguous_journal_title_asks_which_and_is_not_searched(runs_dir: Path) -> None:
    twin = {
        "items": [
            {"id": 1, "title": [{"title": "Journal of Ecology"}], "issns": [{"issn": "0022-0477"}]},
            {"id": 2, "title": [{"title": "Journal of Ecology"}], "issns": [{"issn": "1234-5679"}]},
        ]
    }
    policies = FakePolicies()
    advisor = PolicyAgent(
        policies, opf=opf(opf_handler(extra={("publication", "journal of ecology"): twin}))
    )
    ecology = Actor(role=ActorRole.JOURNAL, name="Journal of Ecology")
    env = invoke(runs_dir, PolicyContext(actors=[ecology, TESTING]), advisor)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    checks = env.payload_as(PolicyChecks)
    [question] = checks.ambiguous
    assert (question.actor, question.role) == ("Journal of Ecology", ActorRole.JOURNAL)
    assert len(question.grounded_on) == 2
    assert "Journal of Ecology" not in checks.no_record
    assert [p.actor for p in checks.policies] == [TESTING.name]
    assert "giving its ISSN" in env.outcome.statement


@pytest.mark.requirement("DD-OUTCOME")
def test_an_unknown_journal_title_stays_without_a_record(runs_dir: Path) -> None:
    advisor = PolicyAgent(FakePolicies(), opf=opf(), crossref=crossref())
    nothing = Actor(role=ActorRole.JOURNAL, name="Journal of Nothing")
    checks = invoke(runs_dir, PolicyContext(actors=[nothing, TESTING]), advisor).payload_as(
        PolicyChecks
    )
    assert checks.no_record == ["Journal of Nothing"]
    assert checks.journals == []


def test_open_policy_finder_down_is_noted_and_fairsharing_still_answers(runs_dir: Path) -> None:
    advisor = PolicyAgent(
        FakePolicies([*ALL, ELSEVIER_POLICY]),
        opf=opf(opf_handler(status=500)),
        crossref=crossref(crossref_handler()),
    )
    env = invoke(runs_dir, PolicyContext(actors=[STOTEN_ACTOR]), advisor)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    checks = env.payload_as(PolicyChecks)
    assert [p.grounded_on[0].source_id for p in checks.policies] == ["FAIRsharing.test-elsevier"]
    assert "Not every registry could be asked" in env.outcome.statement
    assert "HTTP 500" in env.outcome.statement
    assert ELSEVIER_OPF not in {e.source_id for e in env.evidence}


def test_without_a_key_the_statement_says_open_policy_finder_was_not_searched(
    runs_dir: Path,
) -> None:
    env = invoke(runs_dir, PolicyContext(actors=[TESTING, NERC_ACTOR]))
    assert "Open Policy Finder was not searched" in env.outcome.statement
    env = invoke(runs_dir, PolicyContext(actors=[TESTING]))
    assert "Open Policy Finder" not in env.outcome.statement
