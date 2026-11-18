"""The base of every Pydantic mirror of the contract's LinkML classes (`dd_sdk.contract.models`)."""

from pydantic import BaseModel, ConfigDict


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
