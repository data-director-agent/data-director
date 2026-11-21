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
  the entries the profile holds (`resolvers`): the profile is pinned by its digest, recorded with
  every run;
- the app offers them first among a project's suggested repositories (`ids`).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import ValidationError

from dd_sdk.agent import AgentSpec
from dd_sdk.contract.models import REPOSITORY_ID_PATTERN, InstitutionRepository

KEY = "institution_repositories"
SLOT = "institution_repositories"
# The evidence identifier an agent cites what the profile vouches for about a repository under.
SOURCE_PREFIX = "institution:"
# What an entry may say: everything an `InstitutionRepository` holds but the profile's reference,
# which the harness fills.
KEYS = frozenset(InstitutionRepository.model_fields) - {"profile_ref"}
_REPOSITORY_ID = re.compile(REPOSITORY_ID_PATTERN)


def parse(value: Any, profile_ref: str) -> tuple[InstitutionRepository, ...]:
    """The profile's entries. Raises `TypeError` or `ValueError`, which the profile reports as
    malformed, for anything else: a key outside `KEYS`, an identifier in neither registry's
    form, or one named twice."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise TypeError(f"{KEY} must list repositories, each with a repository_id")
    entries: dict[str, InstitutionRepository] = {}
    for entry in value:
        if not isinstance(entry, dict):
            raise TypeError(f"each of {KEY} must be a mapping with a repository_id")
        if unknown := sorted(set(entry) - KEYS):
            raise ValueError(f"{KEY} names keys nothing reads: {', '.join(unknown)}")
        rid = entry.get("repository_id")
        if not isinstance(rid, str) or not _REPOSITORY_ID.fullmatch(rid):
            raise ValueError(
                f"{KEY}: {rid!r} is neither a re3data identifier (r3d followed by nine digits) "
                "nor a DataCite repository identifier (such as bl.york)"
            )
        if rid in entries:
            raise ValueError(f"{KEY} names {rid} twice")
        try:
            found = InstitutionRepository.model_validate({**entry, "profile_ref": profile_ref})
        except ValidationError as exc:
            raise ValueError(f"{KEY}: {rid}: {exc}") from None
        entries[rid] = found
    return tuple(entries.values())


def source_id(entry: InstitutionRepository) -> str:
    return f"{SOURCE_PREFIX}{entry.repository_id}"


def documents(entries: Sequence[InstitutionRepository]) -> list[dict[str, Any]]:
    """The entries as an agent is given them, which is also what it cites and the source check
    hashes."""
    return [e.model_dump(mode="json") for e in entries]


@dataclass(frozen=True)
class Vouched:
    """A resolver (`sources.Resolver`) over what one profile vouches for, by evidence identifier."""

    entries: Mapping[str, dict[str, Any]]

    def record(self, source_id: str) -> dict[str, Any] | None:
        return self.entries.get(source_id)


class _Profile(Protocol):
    @property
    def ref(self) -> str: ...

    @property
    def institution_repositories(self) -> tuple[InstitutionRepository, ...]: ...


def resolvers(profile: _Profile) -> dict[str, Vouched]:
    """The resolver the source check reads the profile's own evidence through, by its reference;
    none when the profile names no repository."""
    entries = profile.institution_repositories
    if not entries:
        return {}
    by_source = {source_id(e): d for e, d in zip(entries, documents(entries), strict=True)}
    return {profile.ref: Vouched(by_source)}


def ids(profile: _Profile) -> list[str]:
    """The identifiers the profile names, in its order."""
    return [e.repository_id for e in profile.institution_repositories]


def fill(profile: _Profile, filled: dict[str, Any], spec: AgentSpec | None) -> dict[str, Any]:
    """`filled` with the profile's repositories, for an agent's own class that mixes in
    `GivenInstitutionRepositories`, in place of whatever was sent (`agent_input.give`)."""
    schema_class = filled.get("schema_class")
    accepted = spec.accepted(str(schema_class)) if spec is not None else None
    if accepted is None or SLOT not in accepted.json_schema.get("properties", {}):
        return filled
    filled = {k: v for k, v in filled.items() if k != SLOT}
    if profile.institution_repositories:
        filled[SLOT] = documents(profile.institution_repositories)
    return filled
