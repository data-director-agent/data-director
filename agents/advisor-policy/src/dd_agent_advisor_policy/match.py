"""Which policy records belong to which actor. A fixed rule, never a guess.

An actor given with a FAIRsharing identifier is fetched by it. Otherwise each of its names is
searched: the name given, and, for a funder identified in ROR, every English name, acronym and
alias ROR records for it (`resolve.py`). A record is kept only when FAIRsharing types it for the
actor's role and its name or abbreviation contains one of those names as whole words. Shorter
names come first, since a publisher's general policy has a shorter name than its journals'
("PLOS - Data Availability" before "PLOS - PLOS ONE - Data Availability"), and at most
`PER_ACTOR` are kept.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from dd_agent_advisor_policy.classes import Actor, ActorRole
from dd_agent_advisor_policy.records import PolicyRecord
from dd_agent_advisor_policy.retrieve import Policies
from dd_sdk.registry import Query

# FAIRsharing's policy types that answer for each role.
TYPES = {
    ActorRole.FUNDER: frozenset({"funder"}),
    ActorRole.JOURNAL: frozenset({"journal", "journal_publisher"}),
    ActorRole.INSTITUTION: frozenset({"institution"}),
}
# Policies kept for one actor: a funder may have a general policy and a data policy, but a
# publisher's name matches each of its journals.
PER_ACTOR = 3
# Search results read per actor before the rule is applied.
SEARCH_LIMIT = 10


def queries(actor: Actor, names: Sequence[str]) -> list[Query]:
    """One search per name. `names` defaults, in `match`, to the name given."""
    return [Query(text=n, limit=SEARCH_LIMIT, label=actor.role.value) for n in names]


def names_actor(record: PolicyRecord, names: Sequence[str]) -> bool:
    """Whether the record's name or abbreviation contains one of `names` as whole words."""
    for name in names:
        wanted = re.compile(rf"(?<!\w){re.escape(name.casefold().strip())}(?!\w)")
        if any(wanted.search(n) for n in record.names()):
            return True
    return False


def fits(record: PolicyRecord, actor: Actor, names: Sequence[str]) -> bool:
    return record.policy_type in TYPES[actor.role] and names_actor(record, names)


def match(actor: Actor, source: Policies, names: Sequence[str] | None = None) -> list[PolicyRecord]:
    """The policy records for one actor, searched by each of `names` (the name given, by
    default). Raises RegistryUnavailable from `source`."""
    if actor.fairsharing_id:
        record = source.fetch(actor.fairsharing_id)
        return [record] if record is not None else []
    names = list(names) if names else [actor.name]
    found: dict[str, PolicyRecord] = {}
    for q in queries(actor, names):
        for record in source.search(q):
            if fits(record, actor, names):
                found.setdefault(record.fairsharing_id, record)
    kept = sorted(found.values(), key=lambda r: (len(r.name), r.fairsharing_id))
    return kept[:PER_ACTOR]
