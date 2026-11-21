"""What the harness asks of a store for a project's members and their roles
(`dd_harness.projects.membership`, docs/specs/projects.md, invariant 16). `dd_harness.storage`
composes it into `ProjectStorage` with the other areas of the project rules."""

from __future__ import annotations

from typing import Any, Literal, Protocol

from dd_sdk.contract.models import Principal


class ProjectMembership(Protocol):
    """A project's members and their roles (`dd_harness.projects.membership`)."""

    def add_member(
        self,
        project_id: str,
        member_id: str,
        role: Literal["owner", "member"] = "member",
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> None:
        """Add a person, by principal identifier, as a member or owner."""
        ...

    def change_role(
        self,
        project_id: str,
        member_id: str,
        role: Literal["owner", "member"],
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> None:
        """Change a member's role; the last owner is never demoted."""
        ...

    def remove_member(
        self, project_id: str, member_id: str, *, acted_for: Principal, caused_by: str
    ) -> None:
        """Remove a member, or a member leaves; the last owner is never removed."""
        ...

    def members(self, project_id: str) -> list[dict[str, Any]]:
        """Each member, their role and since when, the creator first."""
        ...
