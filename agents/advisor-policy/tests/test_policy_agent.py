"""The policy advisor through the conductor, with an in-memory registry, as the workbench
calls it."""

from __future__ import annotations

from pathlib import Path

import pytest
from ror_fixture import NERC, NERC_JO, NERC_SD, build_fixture

import dd_agent_advisor_policy
from dd_agent_advisor_policy import assess
from dd_agent_advisor_policy.agent import PolicyAgent
from dd_agent_advisor_policy.classes import (
    Actor,
    ActorRole,
    ObligationKind,
    PolicyChecks,
    PolicyContext,
    ReadingStatus,
    Strength,
)
from dd_agent_advisor_policy.extract import Extraction, ModelExtractor, Read, found
from dd_agent_advisor_policy.policy_text import PolicyText, html_text
from dd_agent_advisor_policy.records import Clause, PolicyRecord, Relation
from dd_agent_advisor_policy.retrieve import Query, RegistryUnavailable, SnapshotRef
from dd_agent_advisor_policy.ror import Organisation, RorDump
from dd_agent_advisor_policy.snapshot import PolicySnapshot
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.agent import describe
from dd_sdk.contract.models import Envelope, OutcomeStatus, ReasonCode
from dd_sdk.evidence import verify
from dd_sdk.process_flow import STEPS
from dd_sdk.schema import gen
from dd_sdk.testing import FakeModel

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
        # What the reader is shown is what the hash covers (E1, docs/specs/grounding.md).
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
    assert any("exceptions" in n for n in funder.notes)
    assert any("data management plan" in n and "pre-award" in n for n in funder.notes)
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
    assert "Social Survey Archive" in env.outcome.statement


def test_no_relation_is_not_evidence_of_no_mandate(runs_dir: Path) -> None:
    env = invoke(runs_dir, PolicyContext(actors=[TESTING]))
    assert env.payload_as(PolicyChecks).mandated_repositories == []
    assert "not evidence" in env.outcome.statement


UNRECORDED_FUNDER = Actor(role=ActorRole.FUNDER, name="Nowhere Research Council")


@pytest.mark.parametrize("advisor", [PolicyAgent(FakePolicies()), PolicyAgent(PolicySnapshot())])
def test_a_funder_with_no_record_is_not_said_to_mandate_nothing(
    runs_dir: Path, advisor: PolicyAgent
) -> None:
    # #439: a funder with no policy record may still require a repository. The statement must
    # not read as "this funder requires no repository".
    funder = UNRECORDED_FUNDER
    sheffield = Actor(role=ActorRole.INSTITUTION, name="University of Sheffield")
    other = TESTING if isinstance(advisor.policies, FakePolicies) else sheffield
    env = invoke(runs_dir, PolicyContext(actors=[funder, other]), advisor)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.payload_as(PolicyChecks).no_record == [funder.name]
    assert (
        f"No policy record for: {funder.name}; what they require, including any required "
        "repository, was not checked." in env.outcome.statement
    )
    assert "not evidence that none is required" in env.outcome.statement

    env = invoke(runs_dir, PolicyContext(actors=[funder]), advisor)
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert "require a particular repository" in env.outcome.statement


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
    assert "Nowhere College" in env.outcome.statement
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


# --- funders identified in ROR ----------------------------------------------------------------

NERC_POLICY = PolicyRecord(
    fairsharing_id="FAIRsharing.test-nerc",
    name="Natural Environment Research Council data policy",
    policy_type="funder",
    clauses={"sharing_data": Clause(values={"mandated_data_sharing": "required"})},
)


class RecordingPolicies(FakePolicies):
    def __init__(self) -> None:
        super().__init__([*ALL, NERC_POLICY])
        self.searched: list[str] = []

    def search(self, query: Query) -> list[PolicyRecord]:
        self.searched.append(query.text)
        return super().search(query)


class FakeOrganisations:
    """Some of the fixture's organisations, or none when `down`."""

    def __init__(self, orgs: list[Organisation], down: bool = False) -> None:
        self.orgs = orgs
        self.down = down

    def snapshot_ref(self) -> SnapshotRef:
        return SnapshotRef(label="fake-ror")

    def find(self, name: str) -> list[Organisation]:
        if self.down:
            raise RegistryUnavailable("fake ROR is down")
        return [o for o in self.orgs if o.active and o.matches(name)]

    def get(self, ror_id: str) -> Organisation | None:
        return next((o for o in self.orgs if o.id.endswith(ror_id.rsplit("/", 1)[-1])), None)


@pytest.fixture(scope="module")
def dump(tmp_path_factory: pytest.TempPathFactory) -> RorDump:
    return build_fixture(tmp_path_factory.mktemp("ror"))


def nerc_only(dump: RorDump) -> FakeOrganisations:
    org = dump.get(NERC)
    assert org is not None
    return FakeOrganisations([org])


def test_an_acronym_resolved_in_ror_matches_by_the_funders_full_name(
    runs_dir: Path, dump: RorDump
) -> None:
    advisor = PolicyAgent(RecordingPolicies(), organisations=nerc_only(dump))
    env = invoke(
        runs_dir, PolicyContext(actors=[Actor(role=ActorRole.FUNDER, name="NERC")]), advisor
    )
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    checks = env.payload_as(PolicyChecks)
    assert [p.grounded_on[0].source_id for p in checks.policies] == ["FAIRsharing.test-nerc"]
    assert [(f.actor, f.grounded_on[0].source_id) for f in checks.funders] == [("NERC", NERC)]
    assert checks.funders[0].crossref_funder_id == "501100000270"
    assert checks.no_record == [] and checks.ambiguous == []
    # The ROR record is evidence like the policy record, and what the reader is shown is hashed.
    ror_evidence = [e for e in env.evidence if e.source_id == NERC]
    assert len(ror_evidence) == 1 and ror_evidence[0].snapshot_ref == "fake-ror"
    assert ror_evidence[0].content is not None
    assert verify(
        ror_evidence[0].content, ror_evidence[0].canonicalisation, ror_evidence[0].content_hash
    )
    assert {(g.source_id, g.content_hash) for g in checks.grounded_on} >= {
        (g.source_id, g.content_hash) for g in checks.funders[0].grounded_on
    }


@pytest.mark.requirement("DD-OUTCOME")
def test_an_ambiguous_acronym_asks_which_organisation_and_searches_nothing_for_it(
    runs_dir: Path, dump: RorDump
) -> None:
    policies = RecordingPolicies()
    advisor = PolicyAgent(policies, organisations=dump)
    nerc = Actor(role=ActorRole.FUNDER, name="NERC")
    env = invoke(runs_dir, PolicyContext(actors=[nerc, TESTING]), advisor)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    checks = env.payload_as(PolicyChecks)
    assert [(a.actor, a.role) for a in checks.ambiguous] == [("NERC", ActorRole.FUNDER)]
    candidates = [g.source_id for g in checks.ambiguous[0].grounded_on]
    assert candidates[0] == NERC and set(candidates) == {NERC, NERC_JO, NERC_SD}
    assert "NERC" not in checks.no_record
    assert "NERC" not in policies.searched
    assert [p.actor for p in checks.policies] == ["University of Testing"]
    for ror_id in candidates:
        assert ror_id in env.outcome.statement

    # With no other actor, the candidates are still returned, grounded on their ROR records.
    env = invoke(runs_dir, PolicyContext(actors=[nerc]), advisor)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    checks = env.payload_as(PolicyChecks)
    assert checks.policies == [] and len(checks.ambiguous) == 1
    assert {g.source_id for g in checks.grounded_on} == {NERC, NERC_JO, NERC_SD}


def test_the_researchers_choice_of_ror_identifier_settles_the_question(
    runs_dir: Path, dump: RorDump
) -> None:
    advisor = PolicyAgent(RecordingPolicies(), organisations=dump)
    nerc = Actor(role=ActorRole.FUNDER, name="NERC", ror_id="https://ror.org/02b5d8509")
    env = invoke(runs_dir, PolicyContext(actors=[nerc]), advisor)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    checks = env.payload_as(PolicyChecks)
    assert checks.ambiguous == []
    assert [f.grounded_on[0].source_id for f in checks.funders] == [NERC]
    assert [p.grounded_on[0].source_id for p in checks.policies] == ["FAIRsharing.test-nerc"]


@pytest.mark.requirement("DD-OUTCOME")
def test_a_name_unknown_to_ror_and_fairsharing_stays_without_a_record(
    runs_dir: Path, dump: RorDump
) -> None:
    advisor = PolicyAgent(RecordingPolicies(), organisations=dump)
    nowhere = Actor(role=ActorRole.FUNDER, name="Ministry of Nowhere")
    env = invoke(runs_dir, PolicyContext(actors=[nowhere, TESTING]), advisor)
    checks = env.payload_as(PolicyChecks)
    assert checks.no_record == ["Ministry of Nowhere"]
    assert checks.funders == [] and checks.ambiguous == []
    env = invoke(runs_dir, PolicyContext(actors=[nowhere]), advisor)
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.NO_CANDIDATES_RETRIEVED


def test_a_funder_identified_in_ror_with_no_policy_record_still_carries_its_identifier(
    runs_dir: Path, dump: RorDump
) -> None:
    advisor = PolicyAgent(FakePolicies(), organisations=nerc_only(dump))
    nerc = Actor(role=ActorRole.FUNDER, name="NERC")
    env = invoke(runs_dir, PolicyContext(actors=[nerc]), advisor)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    checks = env.payload_as(PolicyChecks)
    assert checks.policies == [] and checks.no_record == ["NERC"]
    assert [f.grounded_on[0].source_id for f in checks.funders] == [NERC]
    assert "require a particular repository" in env.outcome.statement


def test_without_ror_funders_are_searched_by_the_name_given_and_the_statement_says_so(
    runs_dir: Path, dump: RorDump, tmp_path: Path
) -> None:
    unbuilt = RorDump(tmp_path / "registry.jsonl", tmp_path / "manifest.json")
    for advisor in (
        PolicyAgent(FakePolicies(), organisations=unbuilt),
        PolicyAgent(FakePolicies(), organisations=FakeOrganisations([], down=True)),
    ):
        env = invoke(runs_dir, CONTEXT, advisor)
        assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
        checks = env.payload_as(PolicyChecks)
        assert [p.actor for p in checks.policies] == [SRC.name, TESTING.name]
        assert checks.funders == []
        assert "ROR was not consulted" in env.outcome.statement


def test_a_failed_live_ror_route_falls_back_to_the_dump_marked_stale(
    runs_dir: Path, dump: RorDump
) -> None:
    advisor = PolicyAgent(
        RecordingPolicies(),
        organisations=FakeOrganisations([], down=True),
        organisations_fallback=nerc_only(dump),
    )
    env = invoke(
        runs_dir, PolicyContext(actors=[Actor(role=ActorRole.FUNDER, name="NERC")]), advisor
    )
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    refs = {e.source_id: e.snapshot_ref for e in env.evidence}
    assert refs[NERC] == "fake-ror (stale)"


def test_its_classes_are_generated_from_its_linkml() -> None:
    assert gen.stale(SCHEMA) == [], f"run `uv run dd-gen-schema {SCHEMA}`"


# --- reading the policy's own text (#904) -----------------------------------------------------

PAGE_URL = "https://src.example/data-policy"
PAGE = (Path(__file__).parent / "data" / "policy-example.html").read_bytes()
FUNDER_WITH_PAGE = FUNDER.model_copy(update={"homepage": PAGE_URL})
QUOTED = Read(
    kind="repository",
    strength="required",
    value="Social Survey Archive",
    quote="must offer their data for deposit with the Social Survey Archive",
)
INVENTED = Read(
    kind="embargo",
    strength="required",
    value="24 months",
    quote="Data may be withheld for no longer than 24 months after collection.",
)
SRC_DEPOSIT_DIFFERS = Read(
    kind="deposit",
    strength="recommended",
    value="offer the data for deposit",
    quote="Grant holders must offer their data for deposit",
)


class FakePages:
    def __init__(self, served: dict[str, bytes] | None = None) -> None:
        self.served = {PAGE_URL: PAGE} if served is None else served
        self.fetched: list[str] = []

    def snapshot_ref(self) -> SnapshotRef:
        return SnapshotRef(label="fake-policy-text")

    def fetch(self, url: str) -> PolicyText:
        self.fetched.append(url)
        if url not in self.served:
            raise RegistryUnavailable(f"{url}: HTTP 404")
        return PolicyText(
            url=url,
            media_type="text/html",
            sha256="0" * 64,
            text=html_text(self.served[url].decode()),
        )


def reader(*reads: Read) -> ModelExtractor:
    return ModelExtractor(FakeModel(Extraction(obligations=list(reads)).model_dump_json()))


@pytest.mark.requirement("DD-GROUNDED-PAYLOAD", "DD-EVIDENCE")
def test_a_policys_own_text_is_read_and_only_quotes_found_in_it_are_kept(runs_dir: Path) -> None:
    pages = FakePages()
    advisor = PolicyAgent(
        FakePolicies([FUNDER_WITH_PAGE]), pages=pages, extractor=reader(QUOTED, INVENTED)
    )
    env = invoke(runs_dir, PolicyContext(actors=[SRC]), advisor)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    checks = env.payload_as(PolicyChecks)
    assert pages.fetched == [PAGE_URL]
    [reading] = checks.readings
    assert reading.status == ReadingStatus.READ and reading.actor == SRC.name
    assert [(o.kind, o.value) for o in reading.stated] == [
        (ObligationKind.REPOSITORY, "Social Survey Archive")
    ]
    assert [d.split(":")[0] for d in reading.dropped] == ["embargo"]
    # Grounded on the page's text and on the record it was reached from; the text is evidence,
    # hashed, so the reader can find the quote in it.
    cited = [g.source_id for g in reading.grounded_on]
    assert cited == [PAGE_URL, FUNDER.fairsharing_id]
    [text] = [e for e in env.evidence if e.source_id == PAGE_URL]
    assert text.snapshot_ref == "fake-policy-text" and text.content is not None
    assert verify(text.content, text.canonicalisation, text.content_hash)
    assert found(reading.stated[0].quote, text.content["text"])
    # The record's own obligations are as the curators recorded them; the reading adds to them.
    assert strengths(checks, 0)[ObligationKind.DEPOSIT] == Strength.REQUIRED
    assert "Social Survey Archive" in env.outcome.statement
    assert env.telemetry.model_id == "fake-model" and env.telemetry.model_calls


def test_where_the_text_and_the_record_differ_both_are_shown(runs_dir: Path) -> None:
    advisor = PolicyAgent(
        FakePolicies([FUNDER_WITH_PAGE]),
        pages=FakePages(),
        extractor=reader(SRC_DEPOSIT_DIFFERS),
    )
    env = invoke(runs_dir, PolicyContext(actors=[SRC]), advisor)
    checks = env.payload_as(PolicyChecks)
    assert strengths(checks, 0)[ObligationKind.DEPOSIT] == Strength.REQUIRED
    assert checks.readings[0].stated[0].strength == Strength.RECOMMENDED


def test_a_policy_url_is_read_for_an_actor_with_no_record(runs_dir: Path) -> None:
    unknown = Actor(role=ActorRole.FUNDER, name="Unlisted Council", policy_url=PAGE_URL)
    advisor = PolicyAgent(FakePolicies([]), pages=FakePages(), extractor=reader(QUOTED))
    env = invoke(runs_dir, PolicyContext(actors=[unknown]), advisor)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    checks = env.payload_as(PolicyChecks)
    assert checks.no_record == ["Unlisted Council"] and checks.policies == []
    assert [g.source_id for g in checks.readings[0].grounded_on] == [PAGE_URL]
    assert checks.readings[0].stated[0].value == "Social Survey Archive"


def test_a_page_that_cannot_be_fetched_is_reported_beside_its_record(runs_dir: Path) -> None:
    advisor = PolicyAgent(
        FakePolicies([FUNDER_WITH_PAGE]), pages=FakePages({}), extractor=reader(QUOTED)
    )
    env = invoke(runs_dir, PolicyContext(actors=[SRC]), advisor)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    [reading] = env.payload_as(PolicyChecks).readings
    assert reading.status == ReadingStatus.NOT_READ and reading.stated == [] and reading.reason
    assert [g.source_id for g in reading.grounded_on] == [FUNDER.fairsharing_id]


def test_without_a_model_no_page_is_fetched_and_the_statement_says_so(runs_dir: Path) -> None:
    pages = FakePages()
    env = invoke(
        runs_dir,
        PolicyContext(actors=[SRC]),
        PolicyAgent(FakePolicies([FUNDER_WITH_PAGE]), pages=pages),
    )
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert pages.fetched == [] and env.payload_as(PolicyChecks).readings == []


@pytest.mark.requirement("DD-POLICY")
def test_a_profile_can_turn_reading_the_text_off(runs_dir: Path, tmp_path: Path) -> None:
    profile = tmp_path / "profile.yaml"
    profile.write_text(
        "profile_id: no-reading\nagents:\n  advisor.policy: advise\n"
        'agent_settings:\n  advisor.policy:\n    policy_text: "off"\n',
        encoding="utf-8",
    )
    pages = FakePages()
    advisor = PolicyAgent(FakePolicies([FUNDER_WITH_PAGE]), pages=pages, extractor=reader(QUOTED))
    env = make_conductor(runs_dir, advisor, profile=profile).invoke(
        request("advisor.policy", PolicyContext(actors=[SRC])), acting_for=TEST_PRINCIPAL
    )
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert pages.fetched == [] and env.payload_as(PolicyChecks).readings == []
