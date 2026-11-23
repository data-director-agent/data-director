"""Each funder identified in ROR as a `funder` project fact for the researcher to confirm
(docs/specs/projects.md).

ROR is the registry of research organisations, and it holds the Crossref Funder Registry's
identifiers (its `fundref` external identifiers), so one record gives a funder both its ROR
identifier and its Crossref Funder ID. A funder whose name ROR gives to one organisation is
proposed with both, from the record cited in this run; a name ROR gives to more than one, or to
none, is not proposed, since the researcher is asked which they mean.

A proposal is advice: a funder becomes the project's only when a person confirms it. Its subject
is the name the funder was given by, as a person stating that funder is keyed by its name; where
a person already decided the funder without a ROR identifier, the proposal takes that decision's
subject, so confirming it adds the identifiers to the same fact. A funder already decided with a
ROR identifier is not proposed again.
"""

from __future__ import annotations

from collections.abc import Sequence

from dd_agent_advisor_policy.classes import Actor
from dd_mcp_pid.ror_records import Organisation
from dd_sdk.contract.facts import FactKind, ProjectFact

# The DOI prefix of the Crossref Funder Registry.
FUNDER_DOI = "https://doi.org/10.13039/"

BECAUSE = (
    "ROR identifies {given!r} as {name} ({where}). Confirm it if this is a funder of the "
    "project, or reject it if it is not."
)


def crossref_funder_id(org: Organisation) -> str | None:
    """The Crossref Funder ID ROR prefers for the organisation, as a DOI URL, or None."""
    preferred = org.crossref_funder_preferred
    if not preferred:
        return None
    return preferred if preferred.startswith("http") else FUNDER_DOI + preferred


def _ror_suffix(ror: str | None) -> str | None:
    return ror.rstrip("/").rsplit("/", 1)[-1] if ror else None


def _decided(
    actor: Actor, org: Organisation, decisions: Sequence[ProjectFact]
) -> ProjectFact | None:
    """The decided funder fact the actor stands for, by ROR identifier or by name."""
    for fact in decisions:
        if fact.fact_kind != FactKind.FUNDER:
            continue
        if fact.fact_funder_ror and _ror_suffix(str(fact.fact_funder_ror)) == _ror_suffix(org.id):
            return fact
        names = {str(fact.fact_subject).casefold(), str(fact.fact_funder_name or "").casefold()}
        if actor.name.strip().casefold() in names:
            return fact
    return None


def proposals(
    resolved: Sequence[tuple[Actor, Organisation]],
    decisions: Sequence[ProjectFact],
    where: str,
) -> list[ProjectFact]:
    """One proposal for each funder ROR resolved, in order, without repeats."""
    proposed: dict[str, ProjectFact] = {}
    for actor, org in resolved:
        decided = _decided(actor, org, decisions)
        if decided is not None and decided.fact_funder_ror:
            continue
        subject = str(decided.fact_subject) if decided is not None else actor.name.strip()
        if org.id in proposed or any(subject == str(p.fact_subject) for p in proposed.values()):
            continue
        proposed[org.id] = ProjectFact(
            fact_kind=FactKind.FUNDER,
            fact_subject=subject,
            fact_funder_name=org.label,
            fact_funder_ror=org.id,
            fact_crossref_funder_id=crossref_funder_id(org),
            proposed_because=BECAUSE.format(given=actor.name.strip(), name=org.label, where=where),
        )
    return list(proposed.values())
