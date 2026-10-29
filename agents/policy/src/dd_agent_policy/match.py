"""Which policy records belong to which actor. A fixed rule, never a guess.

An actor given with a FAIRsharing identifier is fetched by it. Otherwise its name is searched,
and a record is kept only when FAIRsharing types it for the actor's role and its name or
abbreviation contains the actor's name as whole words. Shorter names come first, since a
publisher's general policy has a shorter name than its journals' ("PLOS - Data Availability"
before "PLOS - PLOS ONE - Data Availability"), and at most `PER_ACTOR` are kept.
"""

from __future__ import annotations

import re

from dd_agent_policy.classes import Actor, ActorRole
from dd_agent_policy.records import PolicyRecord
from dd_agent_policy.retrieve import Policies, Query

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


def query(actor: Actor) -> Query:
    return Query(text=actor.name, limit=SEARCH_LIMIT, label=actor.role.value)


def names_actor(record: PolicyRecord, actor: Actor) -> bool:
    wanted = re.compile(rf"(?<!\w){re.escape(actor.name.casefold().strip())}(?!\w)")
    return any(wanted.search(name) for name in record.names())


def fits(record: PolicyRecord, actor: Actor) -> bool:
    return record.policy_type in TYPES[actor.role] and names_actor(record, actor)


def match(actor: Actor, source: Policies) -> list[PolicyRecord]:
    """The policy records for one actor. Raises RegistryUnavailable from `source`."""
    if actor.fairsharing_id:
        record = source.fetch(actor.fairsharing_id)
        return [record] if record is not None else []
    found = [r for r in source.search(query(actor)) if fits(r, actor)]
    found.sort(key=lambda r: (len(r.name), r.fairsharing_id))
    return found[:PER_ACTOR]
