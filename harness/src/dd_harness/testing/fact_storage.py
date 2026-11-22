"""`ProjectStorage` checks of the facts a project gives agents (docs/specs/projects.md): the
records researchers keep from their own ORCID records (`dd_harness.projects.researchers`), and the
facts people decide (`dd_harness.projects.facts`), where what an agent proposes is never a fact
until a person decides it, the last decision on a kind and subject stands, and a decision on a
proposal the project does not hold is refused and recorded. `dd_harness.testing.storage` runs
them with every other check."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from dd_harness.projects import (
    DOCUMENT_CHANGE_REFUSED,
    FACT_DECIDED,
    PROJECT_CREATED,
    RESEARCHER_ADDED,
    RESEARCHER_WITHDRAWN,
    ChangeRefusedError,
    FactVerdict,
    ProjectDeletedError,
    ProjectError,
    Refusal,
)
from dd_harness.storage import ProjectStorage
from dd_harness.testing.fixtures import TEST_PRINCIPAL
from dd_harness.testing.plan_storage import PLAN_STORAGE_CHECKS

type MakeProjectStorage = Callable[[str], ProjectStorage]


@contextmanager
def _raises(kind: type[Exception], what: str) -> Iterator[None]:
    """Fails unless the block raises `kind`; `what` says what should have been refused."""
    try:
        yield
    except kind:
        return
    raise AssertionError(f"{what}: expected {kind.__name__}")


DUPLICATE: dict[str, Any] = {
    "fact_kind": "file_inclusion",
    "fact_subject": "data/old/readings (copy).csv",
    "fact_file_path": "data/old/readings (copy).csv",
    "file_decision": "exclude",
    "fact_check_kind": "duplicate",
    "proposed_because": "It is byte for byte the same as data/readings.csv.",
}
SITES: dict[str, Any] = {
    "fact_kind": "sensitivity",
    "fact_subject": "calibration/sites.csv",
    "sensitive_subject": "calibration/sites.csv",
    "sensitivity_decision": "undecided",
    "proposed_because": "It holds coordinates.",
}
FUNDER: dict[str, Any] = {
    "fact_kind": "funder",
    "fact_subject": "https://ror.org/02b5d8509",
    "fact_funder_name": "Natural Environment Research Council",
    "fact_funder_ror": "https://ror.org/02b5d8509",
}


def _propose(store: ProjectStorage, project_id: str, *facts: dict[str, Any]) -> list[str]:
    return store.propose_facts(
        project_id, facts, agent_id="advisor.check", acted_for=TEST_PRINCIPAL, caused_by="check"
    )


def _decide(
    store: ProjectStorage, project_id: str, verdict: FactVerdict, **given: Any
) -> dict[str, Any] | None:
    return store.decide_fact(
        project_id, verdict, acted_for=TEST_PRINCIPAL, caused_by="check", **given
    )


def check_a_proposal_is_not_a_fact(make: MakeProjectStorage) -> None:
    """A proposal is offered to a person, never given to an agent, until a person confirms it;
    the fact given holds no one's words about why. A malformed proposal records nothing."""
    store = make("projects")
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="check")
    assert store.decisions(project_id) is None
    assert store.proposals(project_id) == []
    before = len(store.events(project_id))
    try:
        _propose(store, project_id, {"fact_kind": "funder", "fact_subject": "x"})
    except ProjectError:
        pass
    else:
        raise AssertionError("a funder fact without the funder's name was recorded")
    assert len(store.events(project_id)) == before

    duplicate, sites = _propose(store, project_id, DUPLICATE, SITES)
    assert store.decisions(project_id) is None
    offered = store.proposals(project_id)
    assert [p["proposal"] for p in offered] == [duplicate, sites]
    assert offered[0]["fact"]["proposed_because"]
    assert offered[0]["agent_id"] == "advisor.check"

    confirmed = _decide(store, project_id, FactVerdict.CONFIRMED, proposal=duplicate)
    assert confirmed is not None
    assert "proposed_because" not in confirmed
    (fact,) = make("projects").decisions(project_id) or []
    assert fact["file_decision"] == "exclude"
    assert "proposed_because" not in fact
    assert [p["proposal"] for p in store.proposals(project_id)] == [sites]


def check_the_last_decision_on_a_subject_counts(make: MakeProjectStorage) -> None:
    """A changed fact replaces the proposal's value for the same kind and subject; a person may
    state a fact nobody proposed; a rejection removes the fact; a later decision replaces an
    earlier one."""
    store = make("projects")
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="check")
    (sites,) = _propose(store, project_id, SITES)
    generalised = {
        **SITES,
        "sensitivity_decision": "generalise",
        "location_precision": "region",
    }
    _decide(store, project_id, FactVerdict.CHANGED, proposal=sites, fact=generalised, reason="Nest")
    decided = store.events(project_id)[-1]
    assert decided["event"] == FACT_DECIDED
    assert decided["proposal"] == sites
    _decide(store, project_id, FactVerdict.CHANGED, fact=FUNDER)
    facts = store.decisions(project_id) or []
    assert [(f["fact_kind"], f.get("location_precision")) for f in facts] == [
        ("sensitivity", "region"),
        ("funder", None),
    ]
    withheld = {**SITES, "sensitivity_decision": "withhold"}
    _decide(store, project_id, FactVerdict.CHANGED, fact=withheld)
    _decide(store, project_id, FactVerdict.REJECTED, fact=FUNDER)
    (fact,) = store.decisions(project_id) or []
    assert fact["sensitivity_decision"] == "withhold"


def check_a_decision_not_on_the_proposal_is_refused(make: MakeProjectStorage) -> None:
    """A decision on a proposal the project does not hold, or a changed fact of another kind or
    subject than its proposal's, is refused and recorded; a malformed decision records nothing;
    a deleted project takes none."""
    store = make("projects")
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="check")
    other = store.create(acted_for=TEST_PRINCIPAL, caused_by="check")
    (elsewhere,) = _propose(store, other, DUPLICATE)
    (sites,) = _propose(store, project_id, SITES)
    for proposal, fact, refusal in (
        (elsewhere, None, Refusal.NO_PROPOSAL),
        (sites, FUNDER, Refusal.NOT_PROPOSED),
    ):
        verdict = FactVerdict.CONFIRMED if fact is None else FactVerdict.CHANGED
        try:
            _decide(store, project_id, verdict, proposal=proposal, fact=fact)
        except ChangeRefusedError as refused:
            assert refused.refusal == refusal
        else:
            raise AssertionError(f"a decision refused as {refusal} was recorded")
        assert store.events(project_id)[-1]["event"] == DOCUMENT_CHANGE_REFUSED
    assert store.decisions(project_id) is None

    before = len(store.events(project_id))
    for verdict, given in (
        (FactVerdict.CONFIRMED, {}),
        (FactVerdict.CONFIRMED, {"proposal": sites, "fact": SITES}),
        (FactVerdict.CHANGED, {"proposal": sites}),
        (FactVerdict.REJECTED, {}),
        (FactVerdict.CONFIRMED, {"proposal": "not-a-uuid"}),
    ):
        try:
            _decide(store, project_id, verdict, **given)
        except ProjectError as exc:
            assert not isinstance(exc, ChangeRefusedError)
        else:
            raise AssertionError(f"a malformed {verdict} decision was recorded")
    assert len(store.events(project_id)) == before

    store.delete(project_id, acted_for=TEST_PRINCIPAL, caused_by="check")
    try:
        _decide(store, project_id, FactVerdict.CONFIRMED, proposal=sites)
    except ProjectDeletedError:
        pass
    else:
        raise AssertionError("a deleted project took a decision")


def check_a_decision_on_a_superseded_proposal_is_refused(make: MakeProjectStorage) -> None:
    """A decision on a proposal that a later decision, or a later proposal, on its kind and
    subject has followed is refused and recorded, and what stands is unchanged: a person deciding
    from what they saw earlier never overwrites what someone decided since."""
    store = make("projects")
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="check")
    (first,) = _propose(store, project_id, DUPLICATE)
    included = {**DUPLICATE, "file_decision": "include"}
    _decide(store, project_id, FactVerdict.CHANGED, proposal=first, fact=included)
    (older,) = _propose(store, project_id, SITES)
    (newer,) = _propose(store, project_id, {**SITES, "sensitivity_decision": "withhold"})
    for stale in (first, older):
        try:
            _decide(store, project_id, FactVerdict.CONFIRMED, proposal=stale)
        except ChangeRefusedError as refused:
            assert refused.refusal == Refusal.SUPERSEDED
        else:
            raise AssertionError("a decision on a superseded proposal was recorded")
        assert store.events(project_id)[-1]["event"] == DOCUMENT_CHANGE_REFUSED
    (fact,) = store.decisions(project_id) or []
    assert fact["file_decision"] == "include"
    assert [p["proposal"] for p in store.proposals(project_id)] == [newer]


def _researcher_record(orcid_id: str, **sections: Any) -> dict[str, Any]:
    return {
        "orcid_id": orcid_id,
        "record_retrieved_at": "2026-11-10T12:00:00+00:00",
        "record_source": f"https://pub.orcid.org/v3.0/{orcid_id.rsplit('/', 1)[-1]}/record",
        **sections,
    }


def check_a_researchers_own_record_stands_until_withdrawn(make: MakeProjectStorage) -> None:
    store = make("projects")
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="check")
    assert store.researchers(project_id) is None
    me = TEST_PRINCIPAL.principal_id

    def keep(**sections: Any) -> str:
        record = _researcher_record(me, **sections)
        return store.add_researcher(project_id, record, acted_for=TEST_PRINCIPAL, caused_by="check")

    keep(researcher_name="Josiah Carberry")
    keep(researcher_name="Josiah Carberry", keywords=["psychoceramics"])
    held = store.researchers(project_id)
    assert held is not None and len(held) == 1
    assert held[0]["keywords"] == ["psychoceramics"]
    assert make("projects").researchers(project_id) == held
    store.withdraw_researcher(project_id, me, acted_for=TEST_PRINCIPAL, caused_by="check")
    assert store.researchers(project_id) is None
    kinds = [e["event"] for e in store.events(project_id)]
    assert kinds == [PROJECT_CREATED, RESEARCHER_ADDED, RESEARCHER_ADDED, RESEARCHER_WITHDRAWN]


def check_a_person_keeps_only_their_own_record(make: MakeProjectStorage) -> None:
    store = make("projects")
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="check")
    someone = "https://orcid.org/0000-0002-1694-233X"
    refused = [
        _researcher_record(someone, researcher_name="Someone Else"),
        {"orcid_id": TEST_PRINCIPAL.principal_id},
        _researcher_record(TEST_PRINCIPAL.principal_id, works=[{"work_title": "No put-code"}]),
    ]
    for record in refused:
        with _raises(ProjectError, f"keeping {record}"):
            store.add_researcher(project_id, record, acted_for=TEST_PRINCIPAL, caused_by="check")
    with _raises(ProjectError, "withdrawing another person's record"):
        store.withdraw_researcher(project_id, someone, acted_for=TEST_PRINCIPAL, caused_by="check")
    with _raises(ProjectError, "withdrawing a record the project does not hold"):
        store.withdraw_researcher(
            project_id, TEST_PRINCIPAL.principal_id, acted_for=TEST_PRINCIPAL, caused_by="check"
        )
    assert [e["event"] for e in store.events(project_id)] == [PROJECT_CREATED]


FACT_STORAGE_CHECKS: dict[str, Callable[[MakeProjectStorage], None]] = {
    "a researcher's own record stands until withdrawn": (
        check_a_researchers_own_record_stands_until_withdrawn
    ),
    "a person keeps only their own record": check_a_person_keeps_only_their_own_record,
    "a proposal is not a fact": check_a_proposal_is_not_a_fact,
    "the last decision on a subject counts": check_the_last_decision_on_a_subject_counts,
    "a decision not on the proposal is refused": check_a_decision_not_on_the_proposal_is_refused,
    "a decision on a superseded proposal is refused": (
        check_a_decision_on_a_superseded_proposal_is_refused
    ),
    **PLAN_STORAGE_CHECKS,
}
