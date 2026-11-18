"""What the shell is told about a principal (docs/specs/app.md)."""

from __future__ import annotations

from typing import Any

from dd_sdk.contract.models import Principal


def principal_summary(principal: Principal) -> dict[str, Any]:
    """What the shell is told about a principal: whom runs act for, and who vouched for them."""
    summary: dict[str, Any] = {"name": principal.name, "assurance": principal.assurance.value}
    if principal.vouched_by is not None:
        summary["vouched_by"] = str(principal.vouched_by)
    return summary
