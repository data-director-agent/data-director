"""The repository advisor through the conductor, with in-memory registries, served over A2A as
the workbench calls it."""

from __future__ import annotations

from pathlib import Path

import pytest
from re3data_fixture import session_registry

import dd_agent_advisor_repository
from dd_agent_advisor_repository import dfg, rank
from dd_agent_advisor_repository.agent import RepositoryAgent
from dd_agent_advisor_repository.classes import (
    AccessNeed,
    Affiliation,
    Answer,
    CandidateBasis,
    RepositoryNeeds,
    RepositoryOptions,
    RepositoryRef,
)
from dd_agent_advisor_repository.records import DatabaseRecord, Institution, Re3dataRecord
from dd_agent_advisor_repository.retrieve import (
    Hit,
    Query,
    RegistryUnavailable,
    SnapshotRef,
    find_by_name,
)
from dd_agent_advisor_repository.snapshot import FairsharingSnapshot, Re3dataRegistry
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.agent import describe
from dd_sdk.contract.models import Envelope, OutcomeStatus, ReasonCode
from dd_sdk.evidence import verify
from dd_sdk.process_flow import STEPS
from dd_sdk.schema import gen

SCHEMA = Path(dd_agent_advisor_repository.__file__).parent / "schema" / "repository.yaml"

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


@pytest.fixture(scope="session")
def re3data(tmp_path_factory: pytest.TempPathFactory) -> Re3dataRegistry:
    return session_registry(tmp_path_factory)


class FakeRepositories:
    """Word matching over a fixed record list; enough to drive ranking and the linter."""

    def __init__(self, records: list[Re3dataRecord] | None = None, down: bool = False) -> None:
        self.records = ALL if records is None else records
        self.down = down

    def snapshot_ref(self) -> SnapshotRef:
        return SnapshotRef(label="fake-re3data")

    def credit(self) -> str:
        return "Credit to the fake registry."

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

    def find(self, name: str) -> list[Re3dataRecord]:
        self._check()
        return find_by_name(self.records, name)

    def subjects(self) -> dict[str, str]:
        self._check()
        return dfg.vocabulary(s for r in self.records for s in r.subjects)

    def with_subject(self, code: str) -> list[Re3dataRecord]:
        self._check()
        return [r for r in self.records if code in dfg.codes(r.subjects)]


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
    env = conductor.invoke(request("advisor.repository", needs), acting_for=TEST_PRINCIPAL)
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
        # What the reader is shown is what the hash covers (E1, docs/specs/grounding.md).
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
    assert any("CoreTrustSeal" in note for note in options.candidates[1].notes)


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
    # As many others as the cap allows, then the institution's own.
    assert len(options.candidates) == min(len(many), rank.config()["max_candidates"]) + 1
    home = options.candidates[-1]
    assert named(env, options)[-1] == "Testing University Research Data"
    assert any("University of Testing" in meets for meets in home.meets)
    assert any("members" in meets for meets in home.meets)
    assert any("figshare" in note for note in home.notes)
    assert home.commercial == Answer.NO  # the supplier does not operate it


AFFILIATED = NEEDS.model_copy(
    update={"affiliation": Affiliation(name="Testing", ror="https://ror.org/0abcd1234")}
)


def offered_as_fallback(ranked_by: list[str]) -> bool:
    return any("University of Testing" in r and "fallback" in r for r in ranked_by)


@pytest.mark.requirement("R1")
def test_the_institutional_repository_never_displaces_another_candidate(runs_dir: Path) -> None:
    # #441: the cap still offers as many other repositories as it would without the affiliation.
    many = [
        SURVEYS.model_copy(update={"re3data_id": f"r3d10000010{n}", "name": f"Archive {n}"})
        for n in range(6)
    ]
    on_theme = INSTITUTIONAL.model_copy(update={"keywords": ["social survey"]})
    advisor = agent(repositories=FakeRepositories([*many, on_theme]))
    without = named(*_with_options(invoke(runs_dir / "without", NEEDS, advisor)))
    names = named(*_with_options(invoke(runs_dir / "named", AFFILIATED, advisor)))
    assert names == [*without, "Testing University Research Data"]


@pytest.mark.requirement("R1")
def test_an_institutional_repository_that_matches_the_discipline_gets_no_bonus(
    runs_dir: Path,
) -> None:
    # #441: belonging to the institution does not make its repository a better discipline fit.
    on_theme = INSTITUTIONAL.model_copy(update={"keywords": ["social survey"]})
    other = SURVEYS.model_copy(
        update={"name": "Zeta Survey Archive", "keywords": ["social survey"]}
    )
    env = invoke(runs_dir, AFFILIATED, agent(repositories=FakeRepositories([other, on_theme])))
    options = env.payload_as(RepositoryOptions)
    assert named(env, options) == ["Testing University Research Data", "Zeta Survey Archive"]
    home, rival = options.candidates
    assert home.score == rival.score  # in order of name, not of affiliation
    assert any("University of Testing" in r for r in home.ranked_by)
    assert not offered_as_fallback(home.ranked_by)


@pytest.mark.requirement("R1")
def test_the_institutional_fallback_comes_after_the_discipline_and_before_generalists(
    runs_dir: Path,
) -> None:
    general = SURVEYS.model_copy(
        update={
            "re3data_id": rank.generalists()[0],
            "name": "A Generalist",
            "keywords": [],
            "fairsharing_id": None,
        }
    )
    advisor = agent(repositories=FakeRepositories([general, INSTITUTIONAL, SURVEYS]))
    env = invoke(runs_dir, AFFILIATED, advisor)
    options = env.payload_as(RepositoryOptions)
    assert named(env, options) == [
        SURVEYS.name,
        "Testing University Research Data",
        "A Generalist",
    ]
    assert len(options.candidates[1].ranked_by) == 1
    assert offered_as_fallback(options.candidates[1].ranked_by)


@pytest.mark.requirement("R1")
def test_an_institutional_fallback_without_the_access_needed_is_left_out(runs_dir: Path) -> None:
    open_only = INSTITUTIONAL.model_copy(update={"data_access_types": ["open"]})
    env = invoke(runs_dir, AFFILIATED, agent(repositories=FakeRepositories([SURVEYS, open_only])))
    assert named(env, env.payload_as(RepositoryOptions)) == [SURVEYS.name]


def _with_options(env: Envelope) -> tuple[Envelope, RepositoryOptions]:
    return env, env.payload_as(RepositoryOptions)


@pytest.mark.requirement("R1")
def test_a_members_only_repository_is_left_out_unless_the_researcher_is_a_member(
    runs_dir: Path,
) -> None:
    members_only = INSTITUTIONAL.model_copy(update={"keywords": ["social survey"]})
    advisor = agent(repositories=FakeRepositories([SURVEYS, members_only]))
    ids = [
        c.grounded_on[0].source_id
        for c in invoke(runs_dir, NEEDS, advisor).payload_as(RepositoryOptions).candidates
    ]
    assert "r3d100000005" not in ids
    member = NEEDS.model_copy(
        update={"affiliation": Affiliation(name="Testing", ror="https://ror.org/0abcd1234")}
    )
    ids = [
        c.grounded_on[0].source_id
        for c in invoke(runs_dir, member, advisor).payload_as(RepositoryOptions).candidates
    ]
    assert "r3d100000005" in ids


@pytest.mark.requirement("R1")
def test_a_kind_of_data_alone_does_not_recommend_a_repository(runs_dir: Path) -> None:
    # #440: "X-ray diffraction" found a small-molecule crystal database for perovskite films.
    crystals = SURVEYS.model_copy(
        update={
            "re3data_id": "r3d100000013",
            "name": "Crystal Structures",
            "subjects": ["Chemistry"],
            "keywords": ["interview transcripts"],
            "fairsharing_id": None,
        }
    )
    env = invoke(runs_dir, NEEDS, agent(repositories=FakeRepositories([SURVEYS, crystals])))
    options = env.payload_as(RepositoryOptions)
    assert named(env, options) == ["Social Survey Archive"]
    assert options.candidates[0].ranked_by == [
        'Matches the theme "social survey" (1 of 1 given).',
        'Ranks 1 of 1 in a text search of re3data for "social survey".',
        'Matches the kind of data "interview transcripts".',
    ]


@pytest.mark.requirement("R1")
def test_a_repository_is_retrieved_and_recommended_for_its_dfg_subject(runs_dir: Path) -> None:
    """A repository whose record never names the theme is found where re3data files it."""
    filed = OPEN_ONLY.model_copy(
        update={
            "re3data_id": "r3d100000014",
            "name": "Water Archive",
            "subjects": [
                "3 Natural Sciences",
                "34 Geosciences",
                "346 Water Research",
                "34601 Hydrogeology, Hydrology, Limnology",
            ],
            "keywords": [],
            "data_upload_restrictions": [],
        }
    )
    needs = RepositoryNeeds(themes=["hydrology"], access=AccessNeed.OPEN)
    env = invoke(runs_dir, needs, agent(repositories=FakeRepositories([filed, SURVEYS])))
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    options = env.payload_as(RepositoryOptions)
    assert named(env, options) == ["Water Archive"]
    assert options.candidates[0].ranked_by[0].startswith("Matches the theme")
    assert "No discipline-specific repository" not in env.outcome.statement


@pytest.mark.requirement("R1")
def test_a_generalist_is_offered_after_a_repository_of_the_discipline(runs_dir: Path) -> None:
    generalist = OPEN_ONLY.model_copy(
        update={
            "re3data_id": rank.generalists()[0],
            "name": "Anything Archive",
            "keywords": [],
            "data_access_types": ["restricted"],
            "data_upload_restrictions": [],
        }
    )
    advisor = agent(repositories=FakeRepositories([generalist, SURVEYS]))
    env = invoke(runs_dir, NEEDS, advisor)
    options = env.payload_as(RepositoryOptions)
    assert named(env, options) == ["Social Survey Archive", "Anything Archive"]
    [why] = options.candidates[1].ranked_by
    assert "generalist" in why
    # With no repository of the discipline, the generalists are offered and the statement
    # says why.
    env = invoke(runs_dir, NEEDS, agent(repositories=FakeRepositories([generalist])))
    assert named(env, env.payload_as(RepositoryOptions)) == ["Anything Archive"]
    assert "discipline-specific" in env.outcome.statement


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
    assert any("restricted" in miss.lower() for miss in only.misses)
    assert any("persistent identifier" in miss for miss in only.misses)
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


def test_a_shortlist_says_a_policy_may_still_mandate_a_repository(runs_dir: Path) -> None:
    # #439: with no mandate passed in, the shortlist must not read as a free choice.
    caveat = "a funder, journal or institution may still require one"
    assert caveat in invoke(runs_dir, NEEDS).outcome.statement
    needs = NEEDS.model_copy(
        update={"mandated": [RepositoryRef(name="x", re3data_id="r3d100000003")]}
    )
    assert caveat not in invoke(runs_dir, needs).outcome.statement


@pytest.mark.requirement("DD-OUTCOME")
def test_no_mandated_repository_found_abstains(runs_dir: Path) -> None:
    env = invoke(runs_dir, RepositoryNeeds(mandated=[RepositoryRef(name="Nowhere Archive")]))
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.NO_CANDIDATES_RETRIEVED
    # It reports what re3data returned, so it credits re3data like any other statement.
    assert env.outcome.statement.endswith("Credit to the fake registry.")


def test_a_name_several_records_bear_is_not_guessed(runs_dir: Path) -> None:
    twin = SURVEYS.model_copy(update={"re3data_id": "r3d100000099", "fairsharing_id": None})
    needs = RepositoryNeeds(mandated=[RepositoryRef(name="Social Survey Archive")])
    env = invoke(runs_dir, needs, agent(repositories=FakeRepositories([twin, SURVEYS])))
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert "r3d100000001" in env.outcome.statement
    assert "r3d100000099" in env.outcome.statement


def test_a_name_beats_another_records_additional_name() -> None:
    alias = SURVEYS.model_copy(
        update={"re3data_id": "r3d100000000", "name": "Elsewhere", "additional_names": ["SSA"]}
    )
    named = SURVEYS.model_copy(update={"name": "SSA"})
    assert find_by_name([alias, named], "ssa") == [named]
    assert find_by_name([alias], "SSA") == [alias]
    assert find_by_name([alias, named], "nothing") == []


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


def test_a_failed_fairsharing_route_falls_back_to_its_snapshot_marked_stale(
    runs_dir: Path, re3data: Re3dataRegistry
) -> None:
    advisor = agent(
        repositories=re3data,
        databases=FakeDatabases(down=True),
        databases_fallback=FairsharingSnapshot(),
    )
    env = invoke(
        runs_dir, RepositoryNeeds(mandated=[RepositoryRef(name="UK Data Service")]), advisor
    )
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    refs = {e.source_id: e.snapshot_ref for e in env.evidence}
    assert refs["r3d100010230"] == "re3data:export:2026-11"
    assert refs["FAIRsharing.1ky0cs"] is not None and refs["FAIRsharing.1ky0cs"].endswith("(stale)")


def test_re3data_is_credited_and_each_record_cited_by_its_doi(
    runs_dir: Path, re3data: Re3dataRegistry
) -> None:
    advisor = agent(repositories=re3data, databases=FairsharingSnapshot())
    env = invoke(runs_dir, RepositoryNeeds(mandated=[RepositoryRef(name="EIDC")]), advisor)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.outcome.statement is not None
    assert env.outcome.statement.endswith(
        "Repository details are from re3data.org, the Registry of Research Data Repositories "
        "(export of 2026-11, CC0; https://doi.org/10.17616/R3D)."
    )
    uris = {e.source_id: e.source_uri for e in env.evidence}
    assert uris["r3d100010199"] == "https://doi.org/10.17616/R3XG68"


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
