"""A project's members, as the members page shows them (docs/specs/projects.md, Roles; #391).

What the page offers the person viewing it is said here, from what the harness decides
(`dd_harness.project_access`), so that the shell decides nothing: whether they may manage
members, whom they may remove, and whether they may leave. Every change is checked again by the
route guard and by the rules (`dd_harness.projects.Membership`), whatever the shell offered.

A member is named by their principal identifier alone: the project keeps no name for them. Where
a member has kept facts from their own ORCID record in the project (invariant 27), the name they
kept is shown beside their iD.
"""

from __future__ import annotations

from typing import Any

from dd_app.project_service._area import Area
from dd_harness import project_access
from dd_harness.project_access import Action
from dd_harness.projects import MemberRole, is_last_owner, member_roles, principal_identifier
from dd_harness.storage import ProjectMembership
from dd_sdk.contract.models import Principal


class Members(Area):
    def members(self, project_id: str, viewer: Principal) -> dict[str, Any]:
        """Each member, with the name they kept from ORCID if any, and what `viewer` may do."""
        store = self._store
        roles = member_roles(store.events(project_id))
        names = {
            r["orcid_id"]: r["researcher_name"]
            for r in store.researchers(project_id) or []
            if r.get("researcher_name")
        }
        your_role = project_access.role_of(store, project_id, viewer)
        may_manage = project_access.allowed(your_role, Action.MANAGE)
        listed = []
        for member in store.members(project_id):
            member_id = member["member_id"]
            is_you = member_id == viewer.principal_id
            last = is_last_owner(roles, member_id)
            listed.append(
                {
                    **member,
                    **({"researcher_name": names[member_id]} if member_id in names else {}),
                    "is_you": is_you,
                    "removable": (may_manage or is_you) and not last,
                    "role_changeable": may_manage and not last,
                }
            )
        return {
            "members": listed,
            "your_role": your_role.value if your_role else None,
            "may_manage": may_manage,
            "may_leave": your_role is not None and not is_last_owner(roles, viewer.principal_id),
        }

    def add(
        self,
        project_id: str,
        member: str,
        role: MemberRole,
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> dict[str, Any]:
        """Add the person `member` names (an ORCID iD or a principal identifier)."""
        store: ProjectMembership = self._store
        store.add_member(
            project_id,
            principal_identifier(member),
            role,
            acted_for=acted_for,
            caused_by=caused_by,
        )
        return self.members(project_id, acted_for)

    def change_role(
        self,
        project_id: str,
        member_id: str,
        role: MemberRole,
        *,
        acted_for: Principal,
        caused_by: str,
    ) -> dict[str, Any]:
        store: ProjectMembership = self._store
        store.change_role(project_id, member_id, role, acted_for=acted_for, caused_by=caused_by)
        return self.members(project_id, acted_for)

    def may_remove(self, project_id: str, viewer: Principal, member_id: str) -> bool:
        """Whether `viewer` may ask to remove `member_id`: an owner anyone, a member themselves."""
        return project_access.may_remove_member(self._store, project_id, viewer, member_id)

    def remove(
        self, project_id: str, member_id: str, *, acted_for: Principal, caused_by: str
    ) -> dict[str, Any] | None:
        """Remove the member; answers with the members as the remover now sees them, or None if
        they removed themselves and so may no longer read the project."""
        store: ProjectMembership = self._store
        store.remove_member(project_id, member_id, acted_for=acted_for, caused_by=caused_by)
        if member_id == acted_for.principal_id:
            return None
        return self.members(project_id, acted_for)
