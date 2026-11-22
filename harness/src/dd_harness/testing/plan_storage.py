"""`ProjectStorage` checks of a project's data management plan (docs/specs/projects.md,
invariant 32): which attached document is the plan is a fact a person decides, a project has at
most one current plan, and a plan naming a document the project does not hold is refused, or
left out when an agent proposes it. `dd_harness.testing.fact_storage` adds them to its checks,
which `dd_harness.testing.storage` runs with every other."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dd_harness.projects import DOCUMENT_CHANGE_REFUSED, ChangeRefusedError, FactVerdict, Refusal
from dd_harness.storage import ProjectStorage
from dd_harness.testing.fixtures import TEST_PRINCIPAL
from dd_sdk.contract.facts import PLAN_SUBJECT

type MakeProjectStorage = Callable[[str], ProjectStorage]


def plan_fact(digest: str, **more: Any) -> dict[str, Any]:
    """A `data_management_plan` fact naming the attached document whose text has `digest`."""
    return {
        "fact_kind": "data_management_plan",
        "fact_subject": PLAN_SUBJECT,
        "plan_document": digest,
        **more,
    }


def _attach(store: ProjectStorage, project_id: str, name: str, text: str) -> str:
    return store.add_documentation(
        project_id, name, "text/plain", text, acted_for=TEST_PRINCIPAL, caused_by="check"
    )


def _marked(store: ProjectStorage, project_id: str) -> list[str]:
    return [
        d["documentation_digest"]
        for d in store.documentation(project_id)
        if d.get("documentation_is_plan")
    ]


def _decide(store: ProjectStorage, project_id: str, verdict: FactVerdict, **given: Any) -> None:
    store.decide_fact(project_id, verdict, acted_for=TEST_PRINCIPAL, caused_by="check", **given)


def check_a_project_has_one_current_plan(make: MakeProjectStorage) -> None:
    """A document a person marks as the plan is listed as the plan; marking another replaces
    it, and a rejection leaves the project with none."""
    store = make("projects")
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="check")
    first = _attach(store, project_id, "dmp.txt", "Data will be shared in ORDA.")
    revised = _attach(store, project_id, "dmp-v2.txt", "Data will be shared in Zenodo.")
    assert _marked(store, project_id) == []

    _decide(store, project_id, FactVerdict.CHANGED, fact=plan_fact(first))
    assert _marked(store, project_id) == [first]
    _decide(store, project_id, FactVerdict.CHANGED, fact=plan_fact(revised))
    assert _marked(store, project_id) == [revised]
    plans = [
        f for f in store.decisions(project_id) or [] if f["fact_kind"] == "data_management_plan"
    ]
    assert [f["plan_document"] for f in plans] == [revised]

    _decide(store, project_id, FactVerdict.REJECTED, fact=plan_fact(revised))
    assert _marked(store, project_id) == []


def check_a_proposed_plan_is_decided_by_a_person(make: MakeProjectStorage) -> None:
    """An agent's proposal of the plan marks nothing until a person confirms it; a proposal
    naming a document the project does not hold is left out."""
    store = make("projects")
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="check")
    plan = _attach(store, project_id, "dmp.txt", "Data will be shared in ORDA.")
    proposed = store.propose_facts(
        project_id,
        [plan_fact(plan, proposed_because="It is a plan."), plan_fact("f" * 64)],
        agent_id="advisor.check",
        acted_for=TEST_PRINCIPAL,
        caused_by="check",
    )
    assert len(proposed) == 1
    assert _marked(store, project_id) == []
    _decide(store, project_id, FactVerdict.CONFIRMED, proposal=proposed[0])
    assert _marked(store, project_id) == [plan]


def check_a_plan_not_attached_is_refused(make: MakeProjectStorage) -> None:
    """Marking as the plan a document the project does not hold is refused and recorded, and
    the plan that stood still stands."""
    store = make("projects")
    project_id = store.create(acted_for=TEST_PRINCIPAL, caused_by="check")
    other = store.create(acted_for=TEST_PRINCIPAL, caused_by="check")
    plan = _attach(store, project_id, "dmp.txt", "Data will be shared in ORDA.")
    elsewhere = _attach(store, other, "dmp.txt", "Data will be shared in Zenodo.")
    _decide(store, project_id, FactVerdict.CHANGED, fact=plan_fact(plan))
    try:
        _decide(store, project_id, FactVerdict.CHANGED, fact=plan_fact(elsewhere))
    except ChangeRefusedError as refused:
        assert refused.refusal == Refusal.NOT_ATTACHED
    else:
        raise AssertionError("a plan the project does not hold was recorded")
    assert store.events(project_id)[-1]["event"] == DOCUMENT_CHANGE_REFUSED
    assert _marked(store, project_id) == [plan]


PLAN_STORAGE_CHECKS: dict[str, Callable[[MakeProjectStorage], None]] = {
    "a project has one current plan": check_a_project_has_one_current_plan,
    "a proposed plan is decided by a person": check_a_proposed_plan_is_decided_by_a_person,
    "a plan not attached is refused": check_a_plan_not_attached_is_refused,
}
