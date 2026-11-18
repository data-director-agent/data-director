"""A project's facts: what a check agent proposes and a person decides (docs/specs/projects.md).

An agent that checks a project (its policies, its files, its sensitive data, its licence) may
propose facts about it in its payload's `proposed_facts` (`ProjectFact`, `ProposesFacts`). A
succeeded run's proposals are `fact_proposed` events, one for each fact, named by the event's
identifier (`propose_facts`). A proposal is never a fact. A person's decision is a
`fact_decided` event (`decide_fact`): `confirmed` takes the proposal as it is, `changed` takes
the person's own value for the same kind and subject, and `rejected` takes neither. A person may
also state a fact nobody proposed, as a `changed` decision that names no proposal. A decision on
a proposal the project does not hold, or a changed value of another kind or subject than the
proposal's, is refused, and the refusal is a `document_change_refused` event.

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
    FACT_DECIDED,
    FACT_PROPOSED,
    PROJECT_ID,
    ProjectError,
    ProjectRules,
    Refusal,
    Refused,
)
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


class Facts(ProjectRules):
    """The rules of the facts a project holds."""

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
        project or a fact that is not a `ProjectFact`, which records nothing."""
        documents = [checked_fact(f) for f in facts]
        if not documents:
            return []
        events = [
            self._event(
                project_id,
                FACT_PROPOSED,
                acted_for,
                caused_by,
                {"agent_id": agent_id, "fact": document},
            )
            for document in documents
        ]
        with self._section(project_id) as section:
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
        `ChangeRefusedError` for a proposal the project does not hold, or a changed fact of
        another kind or subject, which records the refusal."""
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
            decided = _decided(verdict, proposed, given)
            if isinstance(decided, Refused):
                return decided
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
        open_: dict[tuple[str, str], dict[str, Any]] = {}
        for event in self.events(project_id):
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
        return list(open_.values())


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
