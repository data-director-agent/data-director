"""Which organisation a funder's name means, by ROR. A fixed rule, never a guess.

A funder given with a ROR identifier is looked up by it. Otherwise its name is matched exactly,
ignoring case and spacing, against every name, acronym and alias ROR records for an active
organisation:

- one organisation is **resolved**, and FAIRsharing is then searched by each of its names;
- more than one is **ambiguous**: the researcher is asked which they mean, and nothing is
  searched for that funder until they say. The candidates are ranked, funders first and then
  those with a Crossref Funder ID, so the likeliest is shown first, but the rank never chooses;
- none is **unknown**, and the name is searched as given, as it was before ROR was consulted.

A name of the form "Parent-Child" that ROR does not hold, such as "UKRI-NERC", is read as the
organisation named Child whose parent, in ROR's own relationships, is named Parent. That uses
ROR's records only; no alias table is kept.

Only funders are resolved: FAIRsharing's journal and institution policies are matched by name.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from dd_agent_advisor_policy.classes import Actor, ActorRole
from dd_agent_advisor_policy.ror import FUNDER, Organisation, Organisations

# Names of a resolved organisation searched in FAIRsharing, at most.
MAX_NAMES = 6
# A shorter acronym, such as "WT", would match too many unrelated records to search by.
MIN_NAME = 3
# A hyphen or an en dash, written as an escape.
_COMPOUND = re.compile(r"\s*[-\u2013]\s*")


@dataclass(frozen=True)
class Resolved:
    organisation: Organisation


@dataclass(frozen=True)
class Ambiguous:
    candidates: tuple[Organisation, ...]


@dataclass(frozen=True)
class Unknown:
    """ROR has no organisation by this name, or was not asked."""


Resolution = Resolved | Ambiguous | Unknown


def rank(candidates: list[Organisation]) -> tuple[Organisation, ...]:
    """Funders first, then organisations with a Crossref Funder ID, then by identifier."""
    return tuple(
        sorted(
            candidates,
            key=lambda o: (FUNDER not in o.types, not o.crossref_funder_ids, o.id),
        )
    )


def _compound(name: str, orgs: Organisations) -> list[Organisation]:
    """For "Parent-Child": the organisations named Child whose ROR parent is named Parent."""
    found: dict[str, Organisation] = {}
    for match in _COMPOUND.finditer(name):
        parent, child = name[: match.start()], name[match.end() :]
        if not parent.strip() or not child.strip():
            continue
        parents = {o.id for o in orgs.find(parent)}
        if not parents:
            continue
        for org in orgs.find(child):
            if parents.intersection(org.parents):
                found[org.id] = org
    return [found[k] for k in sorted(found)]


def resolve(actor: Actor, orgs: Organisations) -> Resolution:
    """Raises RegistryUnavailable from `orgs`."""
    if actor.role != ActorRole.FUNDER:
        return Unknown()
    if actor.ror_id:
        org = orgs.get(actor.ror_id)
        return Resolved(org) if org is not None else Unknown()
    candidates = orgs.find(actor.name) or _compound(actor.name, orgs)
    if len(candidates) == 1:
        return Resolved(candidates[0])
    if candidates:
        return Ambiguous(rank(candidates))
    return Unknown()


def names(actor: Actor, resolution: Resolution) -> list[str]:
    """The names FAIRsharing is searched by: the one given, then the resolved organisation's in
    English or in no stated language (FAIRsharing's records are in English), each once and at
    most `MAX_NAMES`, leaving out names shorter than `MIN_NAME`."""
    out = [actor.name.strip()]
    if isinstance(resolution, Resolved):
        org = resolution.organisation
        english = {n.value for n in org.names if n.lang in (None, "en")}
        for name in org.all_names():
            seen = {n.casefold() for n in out}
            if name in english and len(name) >= MIN_NAME and name.casefold() not in seen:
                out.append(name)
    return out[:MAX_NAMES]
