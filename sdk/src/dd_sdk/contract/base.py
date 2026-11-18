"""The base of every Pydantic mirror of a contract class (`dd_sdk.contract.models`)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Frozen(BaseModel):
    """A contract document: immutable, and refusing any member its class does not have."""

    model_config = ConfigDict(frozen=True, extra="forbid")
