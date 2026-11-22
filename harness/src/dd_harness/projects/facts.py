"""A project's facts: what a check agent proposes and a person decides (docs/specs/projects.md).

An agent that checks a project (its policies, its files, its sensitive data, its licence) may
propose facts about it in its payload's `proposed_facts` (`ProjectFact`, `ProposesFacts`). A
succeeded run's proposals are `fact_proposed` events, one for each fact, named by the event's
identifier (`propose_facts`). A proposal is never a fact. A person's decision is a
`fact_decided` event (`decide_fact`): `confirmed` takes the proposal as it is, `changed` takes
the person's own value for the same kind and subject, and `rejected` takes neither. A person may
also state a fact nobody proposed, as a `changed` decision that names no proposal. A decision on
a proposal the project does not hold, on one a later proposal or decision on its kind and subject
has followed, or a changed value of another kind or subject than the proposal's, is refused, and
the refusal is a `document_change_refused` event.

Which attached document is the project's data management plan is a fact too
(`data_management_plan`, invariant 32): its subject is always the same, so the last decision on
it is the one current plan, and a decision or a proposal naming a document the project does not
hold is refused or left out (`current_plan`).

`decisions` gives the facts that stand, the last decision on each kind and subject: a rejection
removes the fact. The conductor puts them into a `DraftRequest` and a `Message` as
`project_decisions`, without the agent's `proposed_because` or a person's reason, which are for
the person deciding (`dd_harness.project_facts`). `proposals` gives the proposals no decision on
their kind and subject has followed, the latest for each, which the app offers a person to decide.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final

from dd_harness.projects.rules import (
    DOCUMENTATION_ADDED,
    FACT_DECIDED,
    FACT_PROPOSED,
    PROJECT_ID,
    ProjectError,
    ProjectRules,
    Refusal,
    Refused,
)
from dd_sdk.contract.facts import PLAN_SUBJECT, FactKind
from dd_sdk.contract.models import Principal, ProjectFact

if TYPE_CHECKING:
    from dd_harness.storage import ProjectSection

# What a person's reason for a decision may be at most, as for a document decision.
FACT_REASON_MAX_LENGTH: Final = 2000
# What only the person deciding is shown, never an agent.
FOR_THE_PERSON: Final = ("proposed_because",)


class FactVerdict(StrEnum):
    """A person's decision on a proposed fact, or on one they state themselves."""

    CONFIRMED = "confirmed"
    CHANGED = "changed"
    REJECTED = "rejected"


def fact_key(fact: Mapping[str, Any]) -> tuple[str, str]:
    """What a decision counts by: the fact's kind and subject."""
    return str(fact["fact_kind"]), str(fact["fact_subject"])


def checked_fact(fact: Mapping[str, Any]) -> dict[str, Any]:
    """`fact` as a `ProjectFact` document, its empty slots left out. Raises `ProjectError` for
    one that is not a `ProjectFact`."""
    try:
        model = ProjectFact.model_validate(dict(fact))
    except ValueError as exc:  # pydantic's ValidationError is a ValueError
        raise ProjectError(f"not a ProjectFact: {exc}") from exc
    document: dict[str, Any] = model.model_dump(
        mode="json", exclude_none=True, exclude_defaults=True
    )
    return document


def for_agents(fact: Mapping[str, Any]) -> dict[str, Any]:
    """`fact` without what only the person deciding is shown."""
    return {k: v for k, v in fact.items() if k not in FOR_THE_PERSON}


PLAN_KEY: Final = (FactKind.DATA_MANAGEMENT_PLAN.value, PLAN_SUBJECT)


def current_plan(events: Iterable[Mapping[str, Any]]) -> str | None:
    """The digest of the attached document a person decided is the project's data management
    plan, from its log's `events`; None while none is decided, or after a rejection."""
    plan = _standing(events).get(PLAN_KEY)
    return None if plan is None else str(plan["plan_document"])


def _unattached(fact: Mapping[str, Any], events: Iterable[Mapping[str, Any]]) -> bool:
    """Whether `fact` names as the plan a document the project does not hold."""
    if fact.get("fact_kind") != FactKind.DATA_MANAGEMENT_PLAN.value:
        return False
    held = {e["digest"] for e in events if e["event"] == DOCUMENTATION_ADDED}
    return fact.get("plan_document") not in held


class Facts(ProjectRules):
    """The rules of the facts a project holds."""

    def checked_facts(self, facts: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        """`facts` as `ProjectFact` documents, recording nothing. Raises `ProjectError` for one
        that is not a `ProjectFact`, so a run's proposals can be checked before any of its
        effects is written."""
        return [checked_fact(f) for f in facts]

    def propose_facts(
        self,
        project_id: str,
        facts: Iterable[Mapping[str, Any]],
        *,
        agent_id: str,
        acted_for: Principal,
        caused_by: str,
    ) -> list[str]:
        """Record what a run of `agent_id` proposed, one `fact_proposed` event each, written
        together. Returns the proposals' identifiers. Raises `ProjectError` for an unknown
        project or a fact that is not a `ProjectFact`, which records nothing. A plan naming a
        document the project does not hold is left out, as nothing a person could decide."""
        documents = self.checked_facts(facts)
        if not documents:
            return []
        with self._section(project_id) as section:
            held = section.events()
            events = [
                self._event(
                    project_id,
                    FACT_PROPOSED,
                    acted_for,
                    caused_by,
                    {"agent_id": agent_id, "fact": document},
                )
                for document in documents
                if not _unattached(document, held)
            ]
            if events:
                section.append(events)
        return [e["event_id"] for e in events]

    def decide_fact(
        self,
        project_id: str,
        verdict: FactVerdict,
        *,
        acted_for: Principal,
        caused_by: str,
        proposal: str | None = None,
        fact: Mapping[str, Any] | None = None,
        reason: str | None = None,
    ) -> dict[str, Any] | None:
        """Record `acted_for`'s decision on `proposal`, or the fact they state with no proposal.
        `confirmed` needs a proposal and takes its fact; `changed` needs `fact`, of the
        proposal's kind and subject where it names one; `rejected` needs a proposal or a `fact`
        naming the kind and subject to reject. Returns the fact that now stands, or None after a
        rejection.

        Raises `ProjectError` for a decision malformed in itself, which records nothing, and
        `ChangeRefusedError` for a proposal the project does not hold, one a later proposal or
        decision on its kind and subject has followed, or a changed fact of another kind or
        subject, which records the refusal."""
        verdict = FactVerdict(verdict)
        given = _given(verdict, proposal, fact, reason)

        def change(section: ProjectSection) -> dict[str, Any] | Refused | None:
            proposed = _proposal(section.events(), proposal) if proposal else None
            if proposal and proposed is None:
                return Refused(
                    Refusal.NO_PROPOSAL,
                    f"This project holds no proposal {proposal}.",
                    {"proposal": proposal},
                )
            if proposed is not None and (stale := _superseded(section.events(), proposed)):
                return stale
            decided = _decided(verdict, proposed, given)
            if isinstance(decided, Refused):
                return decided
            if verdict is not FactVerdict.REJECTED and _unattached(decided, section.events()):
                return Refused(
                    Refusal.NOT_ATTACHED,
                    "The plan must be a document attached to this project.",
                    {"plan_document": decided["plan_document"]},
                )
            detail: dict[str, Any] = {"verdict": verdict.value, "fact": decided}
            if proposal:
                detail["proposal"] = proposal
            if reason:
                detail["reason"] = reason
            section.append([self._event(project_id, FACT_DECIDED, acted_for, caused_by, detail)])
            return None if verdict is FactVerdict.REJECTED else decided

        return self._checked(project_id, acted_for, caused_by, change)

    def decisions(self, project_id: str) -> list[dict[str, Any]] | None:
        """The facts that stand, as `ProjectFact` documents for an agent: the last decision on
        each kind and subject, the one first decided first, without what only a person is shown.
        None while there are none."""
        held = _standing(self.events(project_id))
        return [for_agents(f) for f in held.values()] or None

    def proposal(self, project_id: str, proposal: str) -> dict[str, Any] | None:
        """The fact `proposal` proposed, decided or not, or None if the project holds no such
        proposal."""
        found = _proposal(self.events(project_id), proposal)
        return None if found is None else dict(found["fact"])

    def proposals(self, project_id: str) -> list[dict[str, Any]]:
        """The proposals no decision on their kind and subject has followed, the latest for
        each, in the order proposed: each with its `proposal` identifier, the `agent_id` that
        proposed it, when, and the `fact` as proposed."""
        return list(_open(self.events(project_id)).values())


def _given(
    verdict: FactVerdict,
    proposal: str | None,
    fact: Mapping[str, Any] | None,
    reason: str | None,
) -> dict[str, Any] | None:
    """The fact a decision gives, checked; raises `ProjectError` for a malformed decision."""
    if proposal is not None and not PROJECT_ID.fullmatch(proposal):
        raise ProjectError("a proposal is named by its UUIDv7")
    if reason is not None and len(reason) > FACT_REASON_MAX_LENGTH:
        raise ProjectError(f"a reason is at most {FACT_REASON_MAX_LENGTH} characters")
    if verdict is FactVerdict.CONFIRMED:
        if proposal is None or fact is not None:
            raise ProjectError("a confirmation names a proposal and gives no fact of its own")
        return None
    if verdict is FactVerdict.CHANGED:
        if fact is None:
            raise ProjectError("a changed fact gives the fact")
        return checked_fact(fact)
    if proposal is None and fact is None:
        raise ProjectError("a rejection names a proposal, or the fact's kind and subject")
    if fact is None:
        return None
    if "fact_kind" not in fact or "fact_subject" not in fact:
        raise ProjectError("a rejection names the fact's kind and subject")
    return {"fact_kind": str(fact["fact_kind"]), "fact_subject": str(fact["fact_subject"])}


def _decided(
    verdict: FactVerdict, proposed: Mapping[str, Any] | None, given: dict[str, Any] | None
) -> dict[str, Any] | Refused:
    """The fact a decision records, or a refusal of a fact that is not the proposal's."""
    if verdict is FactVerdict.CONFIRMED:
        assert proposed is not None  # `_given` required a proposal, and `change` found it
        return for_agents(proposed["fact"])
    if proposed is not None and given is not None and fact_key(given) != fact_key(proposed["fact"]):
        kind, subject = fact_key(proposed["fact"])
        return Refused(
            Refusal.NOT_PROPOSED,
            f"The proposal is about the {kind} {subject!r}; a decision on it keeps both.",
            {"proposal": proposed["event_id"]},
        )
    if given is None:
        assert proposed is not None
        kind, subject = fact_key(proposed["fact"])
        return {"fact_kind": kind, "fact_subject": subject}
    return for_agents(given)


def _proposal(events: Sequence[Mapping[str, Any]], proposal: str) -> Mapping[str, Any] | None:
    return next(
        (e for e in events if e["event"] == FACT_PROPOSED and e["event_id"] == proposal), None
    )


def _open(events: Iterable[Mapping[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    """The open proposals by kind and subject: the latest for each that no decision followed."""
    open_: dict[tuple[str, str], dict[str, Any]] = {}
    for event in events:
        if event["event"] == FACT_PROPOSED:
            key = fact_key(event["fact"])
            open_.pop(key, None)
            open_[key] = {
                "proposal": event["event_id"],
                "agent_id": event["agent_id"],
                "proposed_at": event["at"],
                "fact": event["fact"],
            }
        elif event["event"] == FACT_DECIDED:
            open_.pop(fact_key(event["fact"]), None)
    return open_


def _superseded(events: Sequence[Mapping[str, Any]], proposed: Mapping[str, Any]) -> Refused | None:
    """A refusal of a decision on `proposed` if a later proposal or decision on its kind and
    subject has followed it, so that a person deciding from what they saw earlier never
    overwrites what someone decided since."""
    key = fact_key(proposed["fact"])
    if _open(events).get(key, {}).get("proposal") == proposed["event_id"]:
        return None
    kind, subject = key
    return Refused(
        Refusal.SUPERSEDED,
        f"A later proposal or decision on the {kind} {subject!r} has followed this one; "
        "decide on what stands now.",
        {"proposal": proposed["event_id"]},
    )


def _standing(events: Iterable[Mapping[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    held: dict[tuple[str, str], dict[str, Any]] = {}
    for event in events:
        if event["event"] != FACT_DECIDED:
            continue
        key = fact_key(event["fact"])
        if event["verdict"] == FactVerdict.REJECTED:
            held.pop(key, None)
        else:
            held[key] = dict(event["fact"])
    return held
