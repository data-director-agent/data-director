"""The storage services a deployment's profile names as its institution's, for keeping data while
a project runs: the profile key `institution_storage` (docs/specs/policy-and-identity.md).

Each entry names a service by the deployment's own label and says only what the deployment
vouches for: what kind of service it is, whether it is approved for sensitive data, whether people
outside the institution can be given access, the allowance a project has without charge, whether
it charges, what it does to keep copies, and the pages those facts were checked against. No
registry lists an institution's storage, so the profile is the only source. The key is read once,
with the profile, and is used two ways (`dd_harness.profile_vouched`):

- the conductor gives the entries to an agent whose input class mixes in
  `GivenInstitutionStorage` (`fill`, `agent_input.give`), replacing whatever a caller sent;
- the source check resolves what an agent cites of them, under the profile's reference, against
  the entries the profile holds (`vouched`).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, Protocol

from dd_harness import profile_vouched
from dd_sdk.agent import AgentSpec
from dd_sdk.contract.facts import STORAGE_ID_PATTERN, InstitutionStorage

KEY = "institution_storage"
SLOT = "institution_storage"
# The evidence identifier an agent cites what the profile vouches for about a service under.
SOURCE_PREFIX = "institution-storage:"
KEYS = profile_vouched.entry_keys(InstitutionStorage)
_STORAGE_ID = re.compile(STORAGE_ID_PATTERN)


def parse(value: Any, profile_ref: str) -> tuple[InstitutionStorage, ...]:
    """The profile's entries. Raises `TypeError` or `ValueError`, which the profile reports as
    malformed, for anything else: a key outside `KEYS`, a label not in lower case letters,
    digits and hyphens, or one named twice."""
    return profile_vouched.parse_entries(
        value,
        key=KEY,
        id_key="storage_id",
        model=InstitutionStorage,
        profile_ref=profile_ref,
        id_problem=_id_problem,
    )


def _id_problem(storage_id: str) -> str | None:
    if _STORAGE_ID.fullmatch(storage_id):
        return None
    return "is not a label of lower case letters, digits and hyphens (such as research-filestore)"


def source_id(entry: InstitutionStorage) -> str:
    return f"{SOURCE_PREFIX}{entry.storage_id}"


def documents(entries: Sequence[InstitutionStorage]) -> list[dict[str, Any]]:
    """The entries as an agent is given them, which is also what it cites and the source check
    hashes."""
    return [e.model_dump(mode="json") for e in entries]


class _Profile(Protocol):
    @property
    def institution_storage(self) -> tuple[InstitutionStorage, ...]: ...


def vouched(profile: _Profile) -> dict[str, dict[str, Any]]:
    """What the profile vouches for of its storage, by the identifier an agent cites."""
    entries = profile.institution_storage
    return {source_id(e): d for e, d in zip(entries, documents(entries), strict=True)}


def fill(profile: _Profile, filled: dict[str, Any], spec: AgentSpec | None) -> dict[str, Any]:
    """`filled` with the profile's storage, for an agent's own class that mixes in
    `GivenInstitutionStorage`, in place of whatever was sent (`agent_input.give`)."""
    return profile_vouched.fill(filled, spec, SLOT, documents(profile.institution_storage))
