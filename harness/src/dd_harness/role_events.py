"""Which principal a project event may give a role to (docs/specs/projects.md, invariant 16),
and which steward team it routes the project to (docs/specs/stewardship.md, invariant 4).

A backend indexes each event under the principal `names` returns, so that the projects a person
may read are found without reading every project's log (docs/specs/storage.md, "Listing"). The
index is a superset: it says whose role an event may have changed, never what the role is.
Deciding that is the access check's (`dd_harness.project_access.roles`), from the log.

It is a module of its own, imported by the backends and by the access check, because the backends
decide nothing and import none of the project rules.

A project's creator is named by `project_created`, and a member by each membership event
(`member_added`, `member_role_changed`, `member_removed`), whose `member_id` names them. A
removed member stays in the index, which is still a superset: the fold decides.

The same index finds a steward team's projects: `support_team_chosen`, `escalation_opened` and
`project_paused` name the team they route to, by its `team_key`, a URN no principal signs in as,
so a team's queue is one query too, and a team that holds a pause keeps the project. Whether the
escalation is still routed to the team, and in what state, is the escalation fold's
(`dd_harness.projects.escalations`), from the log. A backend orders
a principal's projects by when each project was created (its UUIDv7 `project_id`), not by when
they were first named, so that a project someone was added to later sits where it was created.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# `dd_harness.projects.PROJECT_CREATED`; the backends do not import the rules.
_PROJECT_CREATED = "project_created"
# `dd_harness.projects.MEMBER_ADDED`, `MEMBER_ROLE_CHANGED` and `MEMBER_REMOVED`.
_MEMBERSHIP = frozenset({"member_added", "member_role_changed", "member_removed"})
# `dd_harness.projects.SUPPORT_TEAM_CHOSEN`, `ESCALATION_OPENED` and `PROJECT_PAUSED`, which name a
# team: a team that holds a pause keeps the project until it lifts it.
_ROUTING = frozenset({"support_team_chosen", "escalation_opened", "project_paused"})
TEAM_KEY_PREFIX = "urn:dd:steward-team:"


def team_key(team_id: str) -> str:
    """What the index names a steward team by: a URN that no principal signs in as."""
    return TEAM_KEY_PREFIX + team_id


def names(event: Mapping[str, Any]) -> str | None:
    """The `principal_id` whose role in the project `event` may change, the `team_key` of the
    steward team it routes the project to, or None."""
    kind = event.get("event")
    if kind == _PROJECT_CREATED:
        found = (event.get("acted_for") or {}).get("principal_id")
    elif kind in _MEMBERSHIP:
        found = event.get("member_id")
    elif kind in _ROUTING:
        return team_key(str(event["team_id"])) if event.get("team_id") else None
    else:
        return None
    return str(found) if found else None
