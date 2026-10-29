"""The repository advisor through the conductor, with in-memory registries, served over A2A as
the workbench calls it."""

from __future__ import annotations

from pathlib import Path

import pytest

import dd_agent_repository
from dd_agent_repository.agent import RepositoryAgent
from dd_agent_repository.classes import (
    AccessNeed,
    Affiliation,
    Answer,
    CandidateBasis,
    RepositoryNeeds,
    RepositoryOptions,
    RepositoryRef,
)
from dd_agent_repository.records import DatabaseRecord, Institution, Re3dataRecord
from dd_agent_repository.retrieve import Hit, Query, RegistryUnavailable, SnapshotRef
from dd_agent_repository.snapshot import FairsharingSnapshot, Re3dataSnapshot
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.agent import describe
from dd_sdk.contract.models import Envelope, OutcomeStatus, ReasonCode
from dd_sdk.evidence import verify
from dd_sdk.process_flow import STEPS
from dd_sdk.schema import gen

SCHEMA = Path(dd_agent_repository.__file__).parent / "schema" / "repository.yaml"

UNIVERSITY = Institution(
    name="University of Testing",
    type="non-profit",
    responsibilities=["general"],
    ror="0abcd1234",
)
SURVEYS = Re3dataRecord(
    re3data_id="r3d100000001",
    name="Social Survey Archive",
    subjects=["Social Sciences"],
    keywords=["social survey", "interview transcripts"],
    institutions=[Institution(name="Survey Council", type="non-profit")],
    data_access_types=["open", "restricted"],
    data_upload_types=["restricted"],
    data_upload_restrictions=["registration"],
    pid_systems=["DOI"],
    fairsharing_id="FAIRsharing.test-surveys",
)
SURVEYS_DB = DatabaseRecord(
    fairsharing_id="FAIRsharing.test-surveys",
    doi="10.25504/FAIRsharing.test-surveys",
    name="Social Survey Archive",
    status="ready",
    deposition_notes="Intended primarily for funded social scientists.",
    re3data_ids=["r3d100000001"],
)
OPEN_ONLY = Re3dataRecord(
    re3data_id="r3d100000002",
    name="Open Social Data",
    keywords=["social survey"],
    institutions=[Institution(name="Open Data Trust", type="non-profit")],
    data_access_types=["open"],
    data_upload_types=["restricted"],
    data_upload_restrictions=["feeRequired"],
    pid_systems=["none"],
)
COMMERCIAL = Re3dataRecord(
    re3data_id="r3d100000003",
    name="Acme Data Cloud",
    keywords=["social survey"],
    institutions=[Institution(name="Acme Ltd", type="commercial", responsibilities=["general"])],
    data_access_types=["restricted"],
    data_upload_types=["restricted"],
    pid_systems=["DOI"],
)
CLOSED = Re3dataRecord(
    re3data_id="r3d100000004",
    name="Closed Survey Collection",
    keywords=["social survey"],
    institutions=[Institution(name="Survey Council", type="non-profit")],
    data_access_types=["restricted"],
    data_upload_types=["closed"],
)
INSTITUTIONAL = Re3dataRecord(
    re3data_id="r3d100000005",
    name="Testing University Research Data",
    institutions=[
        UNIVERSITY,
        Institution(name="figshare", type="commercial", responsibilities=["technical"]),
    ],
    data_access_types=["embargoed", "open", "restricted"],
    data_upload_types=["restricted"],
    data_upload_restrictions=["institutional membership"],
    pid_systems=["DOI"],
)
ALL = [SURVEYS, OPEN_ONLY, COMMERCIAL, CLOSED, INSTITUTIONAL]

NEEDS = RepositoryNeeds(
    themes=["social survey"], data_kinds=["interview transcripts"], access=AccessNeed.RESTRICTED
)


class FakeRepositories:
    """Word matching over a fixed record list; enough to drive ranking and the linter."""

    def __init__(self, records: list[Re3dataRecord] | None = None, down: bool = False) -> None:
        self.records = ALL if records is None else records
        self.down = down

    def snapshot_ref(self) -> SnapshotRef:
        return SnapshotRef(label="fake-re3data")

    def _check(self) -> None:
        if self.down:
            raise RegistryUnavailable("fake re3data is down")

    def search(self, query: Query) -> list[Hit]:
        self._check()
        words = query.text.lower().split()
        hits = []
        for r in self.records:
            text = r.search_text().lower()
            score = sum(1.0 for w in words if w in text)
            institutional = any(i.name.lower() == query.text.lower() for i in r.institutions)
            if score or institutional:
                hits.append(Hit(record=r, lexical_score=score))
        return hits[: query.limit]

    def fetch(self, re3data_id: str) -> Re3dataRecord | None:
        self._check()
        return next((r for r in self.records if r.re3data_id == re3data_id), None)

    def find(self, name: str) -> Re3dataRecord | None:
        self._check()
        return next((r for r in self.records if name.casefold() in r.names()), None)


class FakeDatabases:
    def __init__(self, records: list[DatabaseRecord] | None = None, down: bool = False) -> None:
        self.records = {r.fairsharing_id: r for r in ([SURVEYS_DB] if records is None else records)}
        self.down = down

    def snapshot_ref(self) -> SnapshotRef:
        return SnapshotRef(label="fake-fairsharing")

    def fetch(self, fairsharing_id: str) -> DatabaseRecord | None:
        if self.down:
            raise RegistryUnavailable("fake FAIRsharing is down")
        return self.records.get(fairsharing_id)


def agent(**kwargs: object) -> RepositoryAgent:
    kwargs.setdefault("repositories", FakeRepositories())
    kwargs.setdefault("databases", FakeDatabases())
    return RepositoryAgent(**kwargs)  # type: ignore[arg-type]


def invoke(
    runs_dir: Path, needs: RepositoryNeeds, advisor: RepositoryAgent | None = None
) -> Envelope:
    conductor = make_conductor(runs_dir, advisor or agent())
    env = conductor.invoke(request("repository.advisor", needs), acting_for=TEST_PRINCIPAL)
    if env.outcome.status == OutcomeStatus.SUCCEEDED:
        assert conductor.grounding_reports[env.invocation_id].passed
    return env


def named(env: Envelope, options: RepositoryOptions) -> list[str]:
    """The candidates' names, read from the evidence their first grounding names."""
    by_id = {e.source_id: e.content for e in env.evidence}
    out = []
    for c in options.candidates:
        content = by_id[c.grounded_on[0].source_id]
        assert content is not None
        out.append(str(content["name"]))
    return out


# --- shortlisting ---------------------------------------------------------------------------


@pytest.mark.requirement("R1", "DD-GROUNDED-PAYLOAD", "DD-EVIDENCE")
def test_shortlist_is_grounded_and_every_fact_is_evidence(runs_dir: Path) -> None:
    env = invoke(runs_dir, NEEDS)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    options = env.payload_as(RepositoryOptions)
    assert named(env, options)[0] == "Social Survey Archive"
    assert all(c.basis == CandidateBasis.RECOMMENDED and c.rationale for c in options.candidates)
    evidenced = {(e.source_id, e.content_hash) for e in env.evidence}
    for ev in env.evidence:
        # What the reader is shown is what the hash covers (E1, ADR-0015).
        assert ev.content is not None and verify(ev.content, ev.canonicalisation, ev.content_hash)
    for c in options.candidates:
        assert {(g.source_id, g.content_hash) for g in c.grounded_on} <= evidenced
    # The FAIRsharing record re3data cross-references is evidence too.
    first = options.candidates[0]
    assert [g.source_id for g in first.grounded_on] == ["r3d100000001", "FAIRsharing.test-surveys"]
    assert (
        "FAIRsharing on deposits: Intended primarily for funded social scientists." in first.notes
    )
    assert options.searched is not None and options.searched.candidates_qualifying == len(
        options.candidates
    )


@pytest.mark.requirement("R1")
def test_a_repository_that_takes_no_deposits_is_never_recommended(runs_dir: Path) -> None:
    options = invoke(runs_dir, NEEDS).payload_as(RepositoryOptions)
    assert "r3d100000004" not in {c.grounded_on[0].source_id for c in options.candidates}


@pytest.mark.requirement("R1")
def test_commercial_repositories_are_flagged_and_listed_after_equals_not_dropped(
    runs_dir: Path,
) -> None:
    twin = SURVEYS.model_copy(
        update={
            "re3data_id": "r3d100000009",
            "name": "Aardvark Survey Archive",
            "fairsharing_id": None,
        }
    )
    commercial_twin = twin.model_copy(
        update={
            "re3data_id": "r3d100000010",
            "name": "Aardvark Commercial Archive",
            "institutions": COMMERCIAL.institutions,
        }
    )
    advisor = agent(repositories=FakeRepositories([commercial_twin, twin]))
    env = invoke(runs_dir, NEEDS, advisor)
    options = env.payload_as(RepositoryOptions)
    assert named(env, options) == ["Aardvark Survey Archive", "Aardvark Commercial Archive"]
    assert [c.commercial for c in options.candidates] == [Answer.NO, Answer.YES]
    assert options.candidates[0].score == options.candidates[1].score


@pytest.mark.requirement("R1")
def test_certification_carries_no_weight(runs_dir: Path) -> None:
    # Figure 3: paid certification must not be weighted above free evaluation.
    certified = SURVEYS.model_copy(
        update={
            "re3data_id": "r3d100000011",
            "name": "Zebra Archive",
            "certificates": ["CoreTrustSeal"],
        }
    )
    uncertified = SURVEYS.model_copy(update={"re3data_id": "r3d100000012", "name": "Yak Archive"})
    env = invoke(runs_dir, NEEDS, agent(repositories=FakeRepositories([certified, uncertified])))
    options = env.payload_as(RepositoryOptions)
    assert named(env, options) == ["Yak Archive", "Zebra Archive"]  # by name, at an equal score
    assert options.candidates[0].score == options.candidates[1].score
    assert "Certification listed: CoreTrustSeal." in options.candidates[1].notes


@pytest.mark.requirement("R1")
def test_the_researchers_institutional_repository_is_offered_beyond_the_cap(
    runs_dir: Path,
) -> None:
    many = [
        SURVEYS.model_copy(update={"re3data_id": f"r3d10000010{n}", "name": f"Archive {n}"})
        for n in range(6)
    ]
    needs = NEEDS.model_copy(
        update={"affiliation": Affiliation(name="Testing", ror="https://ror.org/0abcd1234")}
    )
    env = invoke(runs_dir, needs, agent(repositories=FakeRepositories([*many, INSTITUTIONAL])))
    options = env.payload_as(RepositoryOptions)
    assert len(options.candidates) == 6
    home = options.candidates[-1]
    assert named(env, options)[-1] == "Testing University Research Data"
    assert "Operated by University of Testing, the researcher's institution." in home.meets
    assert "Deposit is open to members of the researcher's institution." in home.meets
    assert "A commercial organisation, figshare, supplies the platform." in home.notes
    assert home.commercial == Answer.NO  # the supplier does not operate it


# --- the mandated branch --------------------------------------------------------------------


@pytest.mark.requirement("R1")
def test_mandated_repositories_are_described_with_the_needs_they_miss(runs_dir: Path) -> None:
    needs = RepositoryNeeds(
        access=AccessNeed.RESTRICTED,
        mandated=[RepositoryRef(name="open social data"), RepositoryRef(name="Nowhere Archive")],
    )
    env = invoke(runs_dir, needs)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    options = env.payload_as(RepositoryOptions)
    (only,) = options.candidates
    assert only.basis == CandidateBasis.MANDATED and only.score is None
    assert "Restricted access is not listed." in only.misses
    assert "re3data lists no persistent identifier system." in only.misses
    assert only.assigns_pids == Answer.NO
    assert only.fee_required == Answer.YES
    assert options.not_found == ["Nowhere Archive"]
    assert "Nowhere Archive" in env.outcome.statement


@pytest.mark.requirement("R1")
def test_a_mandated_repository_is_found_by_identifier_and_never_shortlisted_around(
    runs_dir: Path,
) -> None:
    needs = NEEDS.model_copy(
        update={"mandated": [RepositoryRef(name="x", re3data_id="r3d100000003")]}
    )
    options = invoke(runs_dir, needs).payload_as(RepositoryOptions)
    assert [c.grounded_on[0].source_id for c in options.candidates] == ["r3d100000003"]


@pytest.mark.requirement("DD-OUTCOME")
def test_no_mandated_repository_found_abstains(runs_dir: Path) -> None:
    env = invoke(runs_dir, RepositoryNeeds(mandated=[RepositoryRef(name="Nowhere Archive")]))
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.NO_CANDIDATES_RETRIEVED


# --- answers read from the registry ----------------------------------------------------------


@pytest.mark.parametrize(
    ("systems", "answer"),
    [(["DOI", "hdl"], Answer.YES), (["none"], Answer.NO), ([], Answer.UNSTATED)],
)
def test_pid_assignment_is_read_from_the_record_not_assumed(
    runs_dir: Path, systems: list[str], answer: Answer
) -> None:
    record = SURVEYS.model_copy(update={"pid_systems": systems, "fairsharing_id": None})
    needs = RepositoryNeeds(mandated=[RepositoryRef(name="Social Survey Archive")])
    env = invoke(runs_dir, needs, agent(repositories=FakeRepositories([record])))
    assert env.payload_as(RepositoryOptions).candidates[0].assigns_pids == answer


def test_a_record_silent_on_fees_does_not_say_there_are_none(runs_dir: Path) -> None:
    needs = RepositoryNeeds(mandated=[RepositoryRef(name="Social Survey Archive")])
    (only,) = invoke(runs_dir, needs).payload_as(RepositoryOptions).candidates
    assert only.fee_required == Answer.UNSTATED


# --- outcomes and fallbacks -------------------------------------------------------------------


@pytest.mark.requirement("DD-OUTCOME")
def test_needs_with_nothing_to_look_up_abstain(runs_dir: Path) -> None:
    env = invoke(runs_dir, RepositoryNeeds(access=AccessNeed.OPEN))
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.INSUFFICIENT_INPUT


@pytest.mark.requirement("DD-OUTCOME")
def test_nothing_fitting_abstains_rather_than_returning_an_empty_list(runs_dir: Path) -> None:
    env = invoke(runs_dir, RepositoryNeeds(themes=["volcanology"]))
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.NO_CANDIDATES_RETRIEVED


@pytest.mark.requirement("DD-OUTCOME")
def test_an_unreachable_registry_is_not_an_empty_result(runs_dir: Path) -> None:
    env = invoke(runs_dir, NEEDS, agent(repositories=FakeRepositories(down=True)))
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.REGISTRY_UNAVAILABLE


def test_a_failed_live_route_falls_back_to_the_snapshot_marked_stale(runs_dir: Path) -> None:
    advisor = agent(
        repositories=FakeRepositories(down=True),
        fallback=Re3dataSnapshot(),
        databases=FakeDatabases(down=True),
        databases_fallback=FairsharingSnapshot(),
    )
    env = invoke(
        runs_dir, RepositoryNeeds(mandated=[RepositoryRef(name="UK Data Service")]), advisor
    )
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    refs = {e.source_id: e.snapshot_ref for e in env.evidence}
    assert refs["r3d100010230"] is not None and refs["r3d100010230"].endswith("(stale)")
    assert refs["FAIRsharing.1ky0cs"] is not None and refs["FAIRsharing.1ky0cs"].endswith("(stale)")


def test_without_fairsharing_a_candidate_stands_on_re3data_alone(runs_dir: Path) -> None:
    env = invoke(runs_dir, NEEDS, agent(databases=FakeDatabases(down=True)))
    options = env.payload_as(RepositoryOptions)
    assert all(len(c.grounded_on) == 1 for c in options.candidates)
    assert {e.source_id for e in env.evidence} == {
        c.grounded_on[0].source_id for c in options.candidates
    }


# --- the spec ---------------------------------------------------------------------------------


@pytest.mark.requirement("DD-REGISTRY")
def test_it_serves_four_phase_3_steps_and_not_the_mandate() -> None:
    entry = describe(RepositoryAgent.spec)
    assert set(RepositoryAgent.spec.serves) <= STEPS
    assert "repository.mandated" not in RepositoryAgent.spec.serves
    assert entry["accepts"] == ["RepositoryNeeds"]
    assert entry["grounding_mode"] == "retrieval"


def test_its_classes_are_generated_from_its_linkml() -> None:
    assert gen.stale(SCHEMA) == [], f"run `uv run dd-gen-schema {SCHEMA}`"
