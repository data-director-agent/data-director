"""The repositories a deployment's profile names as its institution's: the profile key
`institution_repositories` (docs/specs/policy-and-identity.md, docs/specs/deposit.md).

Each entry names a repository by its identifier in the registry that lists it, re3data's or, for
one re3data does not list, DataCite's, and adds only what the deployment vouches for that no
registry holds: which institution it is, the access it offers, its licences, whether it charges a
fee, and the pages those facts were checked against. Nothing invents an identifier or describes a
repository by hand. The key is read once, with the profile, and is used three ways:

- the conductor gives the entries to an agent whose input class mixes in
  `GivenInstitutionRepositories` (`fill`, `agent_input.give`), replacing whatever a caller sent,
  so that the advisor offers them to a researcher of that institution, before anything is hashed;
- the source check resolves what an agent cites of them, under the profile's reference, against
  the entries the profile holds (`vouched`, `dd_harness.profile_vouched`): the profile is pinned
  by its digest, recorded with every run;
- the app offers them first among a project's suggested repositories (`ids`).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, Protocol

from dd_harness import profile_vouched
from dd_harness.profile_vouched import Vouched
from dd_sdk.agent import AgentSpec
from dd_sdk.contract.models import REPOSITORY_ID_PATTERN, InstitutionRepository

KEY = "institution_repositories"
SLOT = "institution_repositories"
# The evidence identifier an agent cites what the profile vouches for about a repository under.
SOURCE_PREFIX = "institution:"
# What an entry may say: everything an `InstitutionRepository` holds but the profile's reference,
# which the harness fills.
KEYS = profile_vouched.entry_keys(InstitutionRepository)
_REPOSITORY_ID = re.compile(REPOSITORY_ID_PATTERN)


def parse(value: Any, profile_ref: str) -> tuple[InstitutionRepository, ...]:
    """The profile's entries. Raises `TypeError` or `ValueError`, which the profile reports as
    malformed, for anything else: a key outside `KEYS`, an identifier in neither registry's
    form, or one named twice."""
    return profile_vouched.parse_entries(
        value,
        key=KEY,
        id_key="repository_id",
        model=InstitutionRepository,
        profile_ref=profile_ref,
        id_problem=_id_problem,
    )


def _id_problem(rid: str) -> str | None:
    if _REPOSITORY_ID.fullmatch(rid):
        return None
    return (
        "is neither a re3data identifier (r3d followed by nine digits) nor a DataCite repository "
        "identifier (such as bl.york)"
    )


def source_id(entry: InstitutionRepository) -> str:
    return f"{SOURCE_PREFIX}{entry.repository_id}"


def documents(entries: Sequence[InstitutionRepository]) -> list[dict[str, Any]]:
    """The entries as an agent is given them, which is also what it cites and the source check
    hashes."""
    return [e.model_dump(mode="json") for e in entries]


class _Profile(Protocol):
    @property
    def ref(self) -> str: ...

    @property
    def institution_repositories(self) -> tuple[InstitutionRepository, ...]: ...


def vouched(profile: _Profile) -> dict[str, dict[str, Any]]:
    """What the profile vouches for of its repositories, by the identifier an agent cites."""
    entries = profile.institution_repositories
    return {source_id(e): d for e, d in zip(entries, documents(entries), strict=True)}


def resolvers(profile: _Profile) -> dict[str, Vouched]:
    """The resolver the source check reads the profile's repositories through, by its reference;
    none when the profile names no repository."""
    return profile_vouched.resolvers(profile.ref, vouched(profile))


def ids(profile: _Profile) -> list[str]:
    """The identifiers the profile names, in its order: offered first among the suggestions, and
    each checked against the pinned registries at start-up (`settings.build_conductor`)."""
    return [e.repository_id for e in profile.institution_repositories]


def fill(profile: _Profile, filled: dict[str, Any], spec: AgentSpec | None) -> dict[str, Any]:
    """`filled` with the profile's repositories, for an agent's own class that mixes in
    `GivenInstitutionRepositories`, in place of whatever was sent (`agent_input.give`)."""
    return profile_vouched.fill(filled, spec, SLOT, documents(profile.institution_repositories))
