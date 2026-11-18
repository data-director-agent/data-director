"""The first search, one step per source (`search.py`): ROR, the journal registries, FAIRsharing
and Open Policy Finder, each on its own, then composed. The registries are fixtures or fakes; the
network is blocked."""

from __future__ import annotations

import copy
from pathlib import Path

import httpx
from opf_fixture import CROSSREF_STOTEN, ELSEVIER_OPF, STOTEN_OPF, crossref, opf, opf_handler
from ror_fixture import NERC, build_fixture

from dd_agent_advisor_policy import discover, search
from dd_agent_advisor_policy.classes import Actor, ActorRole
from dd_agent_advisor_policy.records import PolicyRecord
from dd_agent_advisor_policy.resolve import Ambiguous, Resolved, Unknown
from dd_agent_advisor_policy.ror_records import Organisation
from dd_sdk.agent import AgentResult
from dd_sdk.contract.models import OutcomeStatus, ReasonCode
from dd_sdk.registry import Query, RegistryUnavailable, SnapshotRef

NERC_ACTOR = Actor(role=ActorRole.FUNDER, name="Natural Environment Research Council")
NERC_ACRONYM = Actor(role=ActorRole.FUNDER, name="NERC")
TESTING = Actor(role=ActorRole.INSTITUTION, name="University of Testing")
STOTEN = Actor(role=ActorRole.JOURNAL, name="Science of the Total Environment")
POLICY = PolicyRecord(
    fairsharing_id="FAIRsharing.test-university",
    name="University of Testing - Research Data Policy",
    policy_type="institution",
)


class Records:
    """FAIRsharing's policy records, or a copy of them, which may be down."""

    def __init__(self, label: str, down: bool = False) -> None:
        self.label, self.down = label, down

    def snapshot_ref(self) -> SnapshotRef:
        return SnapshotRef(label=self.label)

    def search(self, query: Query) -> list[PolicyRecord]:
        if self.down:
            raise RegistryUnavailable(f"{self.label} is down")
        return [POLICY] if "testing" in query.text.casefold() else []

    def fetch(self, fairsharing_id: str) -> PolicyRecord | None:
        return None


class DownRor:
    """A copy of ROR that cannot be asked."""

    def snapshot_ref(self) -> SnapshotRef:
        return SnapshotRef(label="down-ror")

    def find(self, name: str) -> list[Organisation]:
        raise RegistryUnavailable("ROR is down")

    def get(self, ror_id: str) -> Organisation | None:
        raise RegistryUnavailable("ROR is down")


# --- ROR --------------------------------------------------------------------------------------


def test_ror_is_not_asked_without_a_funder() -> None:
    step = search.resolve_funders([TESTING], DownRor())
    assert isinstance(step.resolutions[0], Unknown)
    assert step.where is None and step.unavailable is None and step.note == ""


def test_a_funder_is_resolved_or_its_candidates_returned(tmp_path: Path) -> None:
    step = search.resolve_funders([NERC_ACTOR, NERC_ACRONYM, TESTING], build_fixture(tmp_path))
    resolved, ambiguous, other = step.resolutions
    assert isinstance(resolved, Resolved) and resolved.organisation.id == NERC
    assert isinstance(ambiguous, Ambiguous) and NERC in {o.id for o in ambiguous.candidates}
    assert isinstance(other, Unknown)
    assert step.where is not None and step.unavailable is None


def test_without_ror_funders_are_searched_by_the_name_given() -> None:
    for organisations in (None, DownRor()):
        step = search.resolve_funders([NERC_ACTOR], organisations)
        assert isinstance(step.resolutions[0], Unknown)
        assert step.where is None and step.unavailable and step.note


def test_rors_copy_stands_in_when_it_is_down(tmp_path: Path) -> None:
    copy_of_ror = build_fixture(tmp_path)
    step = search.resolve_funders([NERC_ACTOR], DownRor(), copy_of_ror)
    assert isinstance(step.resolutions[0], Resolved)
    assert step.where == SnapshotRef(label=copy_of_ror.snapshot_ref().label, stale=True).as_string()
    assert step.unavailable is None
    both = search.resolve_funders([NERC_ACTOR], DownRor(), DownRor())
    assert isinstance(both.resolutions[0], Unknown) and both.unavailable


# --- FAIRsharing ------------------------------------------------------------------------------


def test_fairsharing_is_searched_live_first() -> None:
    found = search.search_fairsharing([(TESTING, [])], Records("live"), Records("copy"))
    assert not isinstance(found, AgentResult)
    matched, ref = found
    assert matched == [(TESTING, [POLICY])] and ref == SnapshotRef(label="live")


def test_fairsharings_copy_stands_in_and_is_marked_stale() -> None:
    found = search.search_fairsharing([(TESTING, [])], Records("live", down=True), Records("copy"))
    assert not isinstance(found, AgentResult)
    matched, ref = found
    assert matched == [(TESTING, [POLICY])]
    assert ref.label == "copy" and ref.stale and ref.notes


def test_fairsharing_down_is_an_outcome_not_an_empty_result() -> None:
    for fallback in (None, Records("copy", down=True)):
        found = search.search_fairsharing([(TESTING, [])], Records("live", down=True), fallback)
        assert isinstance(found, AgentResult)
        assert found.outcome.status == OutcomeStatus.ABSTAINED
        assert found.outcome.reason_code == ReasonCode.REGISTRY_UNAVAILABLE


# --- journals and Open Policy Finder ----------------------------------------------------------


def test_journals_are_identified_only_when_a_registry_is_configured() -> None:
    assert search.identify_journals([STOTEN], None, None) == {}
    journals = search.identify_journals([TESTING, STOTEN], opf(), crossref())
    assert list(journals) == [1]
    assert journals[1].record is not None and journals[1].record.source_id == STOTEN_OPF


def test_a_journals_own_record_comes_before_its_publishers() -> None:
    journals = search.identify_journals([STOTEN], opf(), None)
    step = search.search_opf([(STOTEN, [])], [STOTEN], journals, opf())
    [(actor, records)] = step.matched
    assert actor == STOTEN and [r.source_id for r in records] == [STOTEN_OPF]
    without_own = {0: discover.Journal(publishers=journals[0].publishers)}
    step = search.search_opf([(STOTEN, [])], [STOTEN], without_own, opf())
    assert [r.source_id for r in step.matched[0][1]] == [ELSEVIER_OPF]


def test_a_funder_open_policy_finder_cannot_find_is_noted() -> None:
    down = opf(opf_handler(status=500))
    step = search.search_opf([(NERC_ACTOR, [NERC_ACTOR.name])], [NERC_ACTOR], {}, down)
    assert step.matched == [] and step.problems
    assert search.search_opf([(NERC_ACTOR, [])], [NERC_ACTOR], {}, None) == search.OpfStep()


def test_journals_of_one_title_from_different_publishers_are_not_guessed_between() -> None:
    other = copy.deepcopy(CROSSREF_STOTEN["message"])
    other["publisher"] = "Another Publisher"
    other["ISSN"] = ["1234-5679"]
    other["issn-type"] = [{"value": "1234-5679", "type": "print"}]
    items = [CROSSREF_STOTEN["message"], other]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok", "message": {"items": items}})

    found = discover.journal(STOTEN, None, crossref(handler))
    assert len(found.candidates) == 2 and found.crossref is None
    assert found.publisher_names == []


# --- the search as a whole --------------------------------------------------------------------


def test_an_ambiguous_funder_is_not_searched_and_its_candidates_are_retrieved(
    tmp_path: Path,
) -> None:
    sources = search.Sources(policies=Records("live"), organisations=build_fixture(tmp_path))
    found = search.first_search([NERC_ACRONYM, TESTING], sources)
    assert isinstance(found, search.FirstSearch)
    assert found.blocked == {"NERC"}
    assert [actor for actor, _ in found.searched] == [TESTING]
    assert {o.id for _, cands in found.ambiguous for o in cands} == set(found.organisations)
    assert POLICY.source_id in found.records
    assert [u.actor for u in found.unresolved()] == ["NERC"]


def test_the_search_stops_when_fairsharing_cannot_be_asked() -> None:
    sources = search.Sources(policies=Records("live", down=True))
    found = search.first_search([TESTING], sources)
    assert isinstance(found, AgentResult)
    assert found.outcome.reason_code == ReasonCode.REGISTRY_UNAVAILABLE
