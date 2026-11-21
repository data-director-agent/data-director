"""The part of a project's storage that records deposits through a repository's API: a person's
approval and its outcome (`dd_harness.projects.deposits`, docs/specs/deposit.md, invariants 12 and
15). `dd_harness.storage.ProjectDeposits` includes it."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from dd_sdk.contract.models import Principal


class DepositApprovals(Protocol):
    def approve_deposit(
        self,
        project_id: str,
        approval: Mapping[str, Any],
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> dict[str, Any]:
        """Record a person's approval to deposit a package; refuses a second approval of a
        package already deposited, or being deposited, in the repository."""
        ...

    def record_deposit_outcome(
        self,
        project_id: str,
        outcome: Mapping[str, Any],
        *,
        recorded: bool,
        acted_for: Principal,
        caused_by: str,
    ) -> dict[str, Any]:
        """Record how an approved deposit ended: `deposit_recorded` or `deposit_failed`."""
        ...
