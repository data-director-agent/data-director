"""The base of every Pydantic mirror of a contract class (`dd_sdk.contract.models`)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict

SHA256_PATTERN = r"^[0-9a-f]{64}$"
# A repository is identified in the registry that lists it (docs/specs/deposit.md): by its re3data
# identifier, or, for one re3data does not list, by its DataCite repository identifier, which
# always holds a dot and so is never mistaken for the other. Nothing invents an identifier.
RE3DATA_ID_PATTERN = r"^r3d[0-9]{9}$"
REPOSITORY_ID_PATTERN = r"^(r3d[0-9]{9}|[a-z0-9]+\.[a-z0-9.-]+)$"


class Frozen(BaseModel):
    """A contract document: immutable, and refusing any member its class does not have."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def backfill_repository_id(repository_slot: str, re3data_slot: str) -> Callable[[Any], Any]:
    """A `mode="before"` validator that gives a document recorded before repositories had an
    identifier of their own its re3data identifier as that identifier, so old project logs and
    blobs still read (docs/specs/deposit.md)."""

    def fill(cls: type, data: Any) -> Any:
        if isinstance(data, dict) and not data.get(repository_slot) and data.get(re3data_slot):
            return {**data, repository_slot: data[re3data_slot]}
        return data

    return classmethod(fill)  # type: ignore[return-value]
