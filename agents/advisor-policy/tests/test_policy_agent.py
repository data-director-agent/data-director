"""The policy advisor through the conductor, with an in-memory registry, as the workbench
calls it."""

from __future__ import annotations

from pathlib import Path

import pytest

import dd_agent_advisor_policy
from dd_agent_advisor_policy import assess
from dd_agent_advisor_policy.agent import PolicyAgent
from dd_agent_advisor_policy.classes import (
    Actor,
    ActorRole,
    ObligationKind,
    PolicyChecks,
    PolicyContext,
    Strength,
)
from dd_agent_advisor_policy.records import Clause, PolicyRecord, Relation
from dd_agent_advisor_policy.retrieve import Query, RegistryUnavailable, SnapshotRef
from dd_agent_advisor_policy.snapshot import PolicySnapshot
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.agent import describe
from dd_sdk.contract.models import Envelope, OutcomeStatus, ReasonCode
from dd_sdk.evidence import verify
from dd_sdk.process_flow import STEPS
from dd_sdk.schema import gen

SCHEMA = Path(dd_agent_advisor_policy.__file__).parent / "schema" / "policy.yaml"

FUNDER = PolicyRecord(
    fairsharing_id="FAIRsharing.test-funder",
    numeric_id="1",
    name="Social Research Council data policy",
    abbreviation="SRC data policy",
    policy_type="funder",
    status="ready",
    subjects=["Social Science"],
    year_creation="2015",
    clauses={
        "sharing_data": Clause(
            values={"mandated_data_sharing": "required", "exceptions_to_data_sharing": "yes"},
            notes="Data shall be made openly available.",
        ),
        "data_availability_statement": Clause(values={"required": "no"}),
        "dmp_development": Clause(
            values={"mandated_dmp_creation": "required", "timing_of_dmp": "pre-award"}
        ),
    },
    relations=[
        Relation(relation="requires", registry="Database", name="Social Survey Archive"),
        Relation(relation="recommends", registry="Standard", name="DDI"),
    ],
)
UNIVERSITY = PolicyRecord(
    fairsharing_id="FAIRsharing.test-university",
    name="University of Testing - Research Data Policy",
    policy_type="institution",
    subjects=["Subject Agnostic"],
    year_creation="2024",
    clauses={
        "sharing_data": Clause(values={"mandated_data_sharing": "suggested"}),
        "data_availability_statement": Clause(values={"required": "yes"}),
    },
)
PUBLISHER = PolicyRecord(
    fairsharing_id="FAIRsharing.test-publisher",
    name="Acme - Data Availability",
    policy_type="journal_publisher",
    subjects=["Life Science"],
    clauses={"licences_for_outputs": Clause(values={"required": "yes"})},
)
JOURNAL = PolicyRecord(
    fairsharing_id="FAIRsharing.test-journal",
    name="Acme - Acme Letters - Data Availability",
    policy_type="journal",
    subjects=["Life Science"],
)
# Names the university, but as a funder: never matched to the institution.
NAMESAKE = PolicyRecord(
    fairsharing_id="FAIRsharing.test-namesake",
    name="University of Testing Foundation grants policy",
    policy_type="funder",
)
ALL = [FUNDER, UNIVERSITY, PUBLISHER, JOURNAL, NAMESAKE]

SRC = Actor(role=ActorRole.FUNDER, name="Social Research Council")
TESTING = Actor(role=ActorRole.INSTITUTION, name="University of Testing")
CONTEXT = PolicyContext(actors=[SRC, TESTING], disciplines=["social science"])


class FakePolicies:
    """Word matching over a fixed record list."""

    def __init__(self, records: list[PolicyRecord] | None = None, down: bool = False) -> None:
        self.records = ALL if records is None else records
        self.down = down

    def snapshot_ref(self) -> SnapshotRef:
        return SnapshotRef(label="fake-fairsharing-policy")

    def _check(self) -> None:
        if self.down:
            raise RegistryUnavailable("fake FAIRsharing is down")

    def search(self, query: Query) -> list[PolicyRecord]:
        self._check()
        words = query.text.lower().split()
        return [r for r in self.records if any(w in r.search_text().lower() for w in words)]

    def fetch(self, fairsharing_id: str) -> PolicyRecord | None:
        self._check()
        return next((r for r in self.records if r.fairsharing_id == fairsharing_id), None)


def invoke(runs_dir: Path, context: PolicyContext, advisor: PolicyAgent | None = None) -> Envelope:
    conductor = make_conductor(runs_dir, advisor or PolicyAgent(FakePolicies()))
    env = conductor.invoke(request("advisor.policy", context), acting_for=TEST_PRINCIPAL)
    if env.outcome.status == OutcomeStatus.SUCCEEDED:
        assert conductor.grounding_reports[env.invocation_id].passed
    return env


def strengths(checks: PolicyChecks, index: int) -> dict[ObligationKind, Strength]:
    return {o.kind: o.strength for o in checks.policies[index].obligations}


# --- matching and obligations ---------------------------------------------------------------


@pytest.mark.requirement("DD-GROUNDED-PAYLOAD", "DD-EVIDENCE")
def test_each_actor_is_matched_and_every_record_is_evidence(runs_dir: Path) -> None:
    env = invoke(runs_dir, CONTEXT)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    checks = env.payload_as(PolicyChecks)
    assert [(p.actor, p.grounded_on[0].source_id) for p in checks.policies] == [
        ("Social Research Council", "FAIRsharing.test-funder"),
        ("University of Testing", "FAIRsharing.test-university"),
    ]
    for ev in env.evidence:
        # What the reader is shown is what the hash covers (E1, ADR-0015).
        assert ev.content is not None and verify(ev.content, ev.canonicalisation, ev.content_hash)
    evidenced = {(e.source_id, e.content_hash) for e in env.evidence}
    for p in checks.policies:
        assert {(g.source_id, g.content_hash) for g in p.grounded_on} <= evidenced
    assert all(p.rationale for p in checks.policies)
    assert checks.no_record == []


def test_obligations_are_read_from_the_curated_fields() -> None:
    stated = {o.kind: o for o in assess.obligations(FUNDER)}
    assert stated[ObligationKind.DEPOSIT].strength == Strength.REQUIRED
    # "no" is not a strength; it is kept beside `unstated` so that it is not hidden.
    das = stated[ObligationKind.DATA_AVAILABILITY_STATEMENT]
    assert (das.strength, das.recorded_as) == (Strength.UNSTATED, "no")
    assert stated[ObligationKind.REPOSITORY].strength == Strength.REQUIRED
    assert stated[ObligationKind.STANDARD].strength == Strength.RECOMMENDED
    assert stated[ObligationKind.EMBARGO].strength == Strength.UNSTATED
    assert stated[ObligationKind.LICENCE].strength == Strength.UNSTATED
    assert [o.kind for o in assess.obligations(FUNDER)] == list(ObligationKind)


def test_a_name_is_matched_only_for_its_role(runs_dir: Path) -> None:
    checks = invoke(runs_dir, PolicyContext(actors=[TESTING])).payload_as(PolicyChecks)
    assert [p.grounded_on[0].source_id for p in checks.policies] == ["FAIRsharing.test-university"]


def test_a_publishers_own_policy_comes_before_its_journals(runs_dir: Path) -> None:
    acme = Actor(role=ActorRole.JOURNAL, name="Acme")
    checks = invoke(runs_dir, PolicyContext(actors=[acme])).payload_as(PolicyChecks)
    assert [p.grounded_on[0].source_id for p in checks.policies] == [
        "FAIRsharing.test-publisher",
        "FAIRsharing.test-journal",
    ]


def test_an_actor_given_by_identifier_is_fetched_not_searched(runs_dir: Path) -> None:
    actor = Actor(role=ActorRole.JOURNAL, name="x", fairsharing_id="FAIRsharing.test-journal")
    checks = invoke(runs_dir, PolicyContext(actors=[actor])).payload_as(PolicyChecks)
    assert [p.grounded_on[0].source_id for p in checks.policies] == ["FAIRsharing.test-journal"]


def test_notes_flag_subject_date_exceptions_and_the_plan(runs_dir: Path) -> None:
    context = CONTEXT.model_copy(update={"publication_date": "2020-06"})
    checks = invoke(runs_dir, context).payload_as(PolicyChecks)
    funder, university = checks.policies
    assert "The record says the policy allows exceptions to sharing." in funder.notes
    assert "The record says a data management plan is required, pre-award." in funder.notes
    assert any("after the publication date given (2020-06)" in n for n in university.notes)
    # Subject Agnostic is no mismatch; Life Science against social science is.
    assert not any("subjects" in n for n in university.notes)
    acme = invoke(
        runs_dir,
        PolicyContext(actors=[Actor(role=ActorRole.JOURNAL, name="Acme")], disciplines=["law"]),
    ).payload_as(PolicyChecks)
    assert any("Life Science" in n for n in acme.policies[0].notes)


# --- conflicts and the mandate --------------------------------------------------------------


@pytest.mark.requirement("DD-GROUNDED-PAYLOAD")
def test_policies_that_differ_are_flagged_and_grounded_on_each(runs_dir: Path) -> None:
    env = invoke(runs_dir, CONTEXT)
    checks = env.payload_as(PolicyChecks)
    by_kind = {c.kind: c for c in checks.conflicts}
    deposit = by_kind[ObligationKind.DEPOSIT]
    assert {g.source_id for g in deposit.grounded_on} == {
        "FAIRsharing.test-funder",
        "FAIRsharing.test-university",
    }
    assert "a person should" in deposit.description
    # Required by one and "no" in another is not a difference: "no" is unstated.
    assert ObligationKind.DATA_AVAILABILITY_STATEMENT not in by_kind
    assert "state differently: 1" in env.outcome.statement


def test_a_required_repository_is_passed_on_in_the_repository_advisors_form(
    runs_dir: Path,
) -> None:
    env = invoke(runs_dir, CONTEXT)
    checks = env.payload_as(PolicyChecks)
    assert [r.name for r in checks.mandated_repositories] == ["Social Survey Archive"]
    assert "Repositories required: Social Survey Archive." in env.outcome.statement


def test_no_relation_is_not_evidence_of_no_mandate(runs_dir: Path) -> None:
    env = invoke(runs_dir, PolicyContext(actors=[TESTING]))
    assert env.payload_as(PolicyChecks).mandated_repositories == []
    assert "No matched record names a required repository." in env.outcome.statement


# --- outcomes and fallbacks -------------------------------------------------------------------


@pytest.mark.requirement("DD-OUTCOME")
def test_a_context_with_no_actor_abstains(runs_dir: Path) -> None:
    env = invoke(runs_dir, PolicyContext(disciplines=["social science"]))
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.INSUFFICIENT_INPUT


@pytest.mark.requirement("DD-OUTCOME")
def test_actors_with_no_record_are_listed_or_abstain_when_none_has_one(runs_dir: Path) -> None:
    nowhere = Actor(role=ActorRole.INSTITUTION, name="Nowhere College")
    env = invoke(runs_dir, PolicyContext(actors=[SRC, nowhere]))
    assert env.payload_as(PolicyChecks).no_record == ["Nowhere College"]
    assert "No policy record for: Nowhere College." in env.outcome.statement
    env = invoke(runs_dir, PolicyContext(actors=[nowhere]))
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.NO_CANDIDATES_RETRIEVED


@pytest.mark.requirement("DD-OUTCOME")
def test_an_unreachable_registry_is_not_an_empty_result(runs_dir: Path) -> None:
    env = invoke(runs_dir, CONTEXT, PolicyAgent(FakePolicies(down=True)))
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.REGISTRY_UNAVAILABLE


def test_a_failed_live_route_falls_back_to_the_snapshot_marked_stale(runs_dir: Path) -> None:
    advisor = PolicyAgent(FakePolicies(down=True), fallback=PolicySnapshot())
    context = PolicyContext(
        actors=[
            Actor(role=ActorRole.FUNDER, name="Economic and Social Research Council"),
            Actor(role=ActorRole.INSTITUTION, name="University of Sheffield"),
        ]
    )
    env = invoke(runs_dir, context, advisor)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    refs = {e.source_id: e.snapshot_ref for e in env.evidence}
    assert set(refs) == {"FAIRsharing.636kdn", "FAIRsharing.e081af"}
    assert all(ref is not None and ref.endswith("(stale)") for ref in refs.values())


# --- the spec ---------------------------------------------------------------------------------


@pytest.mark.requirement("DD-REGISTRY")
def test_it_serves_the_policy_check_and_the_mandate() -> None:
    entry = describe(PolicyAgent.spec)
    assert set(PolicyAgent.spec.serves) == {"governance.policies", "repository.mandated"}
    assert set(PolicyAgent.spec.serves) <= STEPS
    assert entry["accepts"] == ["PolicyContext"]
    assert entry["grounding_mode"] == "retrieval"


def test_its_classes_are_generated_from_its_linkml() -> None:
    assert gen.stale(SCHEMA) == [], f"run `uv run dd-gen-schema {SCHEMA}`"
