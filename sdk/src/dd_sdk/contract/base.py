"""What every Pydantic mirror of the core contract shares (docs/specs/contract.md)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

SHA256_PATTERN = r"^[0-9a-f]{64}$"


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
