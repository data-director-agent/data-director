"""Helpers for tests of the deposit check: clearing the pause before packaging
(`dd_harness.deposit_review`, docs/specs/deposit.md)."""

from __future__ import annotations

from dd_harness.deposit_review import CONFIRMATIONS, ItemDecision, confirm, decide_item, review
from dd_harness.storage import DepositSource
from dd_sdk.contract.models import Principal


def clear_review(projects: DepositSource, project_id: str, *, acted_for: Principal) -> None:
    """Decide every item the deposit check lists for the project as kept, and confirm the checks
    before deposit, as `acted_for`."""
    for item in review(projects, project_id).open_items:
        decide_item(
            projects,
            project_id,
            item.item_id,
            ItemDecision.KEEP,
            None,
            acted_for=acted_for,
            caused_by="test",
        )
    confirm(projects, project_id, CONFIRMATIONS, acted_for=acted_for, caused_by="test")
