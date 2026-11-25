"""What a deployment's profile vouches for, given to agents and checked when they cite it
(docs/specs/policy-and-identity.md). Shared by the keys that list such entries, the institution's
repositories (`institution_repositories`) and its storage (`institution_storage`):

- the conductor gives a key's entries to an agent whose input class has the key's slot, in place
  of whatever a caller sent there (`fill`);
- the source check resolves what an agent cites of them, under the profile's reference, against
  the entries the profile holds (`resolvers`): the profile is pinned by its digest, recorded with
  every run.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from dd_sdk.agent import AgentSpec

# The field the harness fills on every entry: the reference of the profile that vouches for it.
PROFILE_REF = "profile_ref"


def entry_keys(model: type[BaseModel]) -> frozenset[str]:
    """What an entry of `model` may say: every field but the profile's reference."""
    return frozenset(model.model_fields) - {PROFILE_REF}


def parse_entries[M: BaseModel](
    value: Any,
    *,
    key: str,
    id_key: str,
    model: type[M],
    profile_ref: str,
    id_problem: Callable[[str], str | None],
) -> tuple[M, ...]:
    """A profile key's entries, each a mapping read as `model`, in the profile's order. Raises
    `TypeError` or `ValueError`, which the profile reports as malformed, for anything else: a
    key the model does not hold, an identifier `id_problem` faults, or one named twice."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise TypeError(f"{key} must list its entries, each a mapping with a {id_key}")
    allowed = entry_keys(model)
    entries: dict[str, M] = {}
    for entry in value:
        if not isinstance(entry, dict):
            raise TypeError(f"each of {key} must be a mapping with a {id_key}")
        if unknown := sorted(set(entry) - allowed):
            raise ValueError(f"{key} names keys nothing reads: {', '.join(unknown)}")
        found_id = entry.get(id_key)
        if not isinstance(found_id, str):
            raise ValueError(f"{key}: each entry needs a {id_key}")
        if problem := id_problem(found_id):
            raise ValueError(f"{key}: {found_id!r} {problem}")
        if found_id in entries:
            raise ValueError(f"{key} names {found_id} twice")
        try:
            entries[found_id] = model.model_validate({**entry, PROFILE_REF: profile_ref})
        except ValidationError as exc:
            raise ValueError(f"{key}: {found_id}: {exc}") from None
    return tuple(entries.values())


@dataclass(frozen=True)
class Vouched:
    """A resolver (`sources.Resolver`) over what one profile vouches for, by evidence identifier."""

    entries: Mapping[str, dict[str, Any]]

    def record(self, source_id: str) -> dict[str, Any] | None:
        return self.entries.get(source_id)


def resolvers(profile_ref: str, by_source: Mapping[str, dict[str, Any]]) -> dict[str, Vouched]:
    """The resolver the source check reads the profile's own evidence through, by its reference;
    none when the profile vouches for nothing."""
    return {profile_ref: Vouched(dict(by_source))} if by_source else {}


def fill(
    filled: dict[str, Any], spec: AgentSpec | None, slot: str, documents: list[dict[str, Any]]
) -> dict[str, Any]:
    """`filled` with `documents` in `slot`, for an agent's own class that has that slot, in place
    of whatever was sent; unchanged for any other class."""
    schema_class = filled.get("schema_class")
    accepted = spec.accepted(str(schema_class)) if spec is not None else None
    if accepted is None or slot not in accepted.json_schema.get("properties", {}):
        return filled
    filled = {k: v for k, v in filled.items() if k != slot}
    if documents:
        filled[slot] = documents
    return filled
