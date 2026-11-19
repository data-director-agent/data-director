"""Which principal a project event may give a role to (docs/specs/projects.md, invariant 16).

A backend indexes each event under the principal `names` returns, so that the projects a person
may read are found without reading every project's log (docs/specs/storage.md, "Listing"). The
index is a superset: it says whose role an event may have changed, never what the role is.
Deciding that is the access check's (`dd_harness.project_access.roles`), from the log.

It is a module of its own, imported by the backends and by the access check, because the backends
decide nothing and import none of the project rules.

Today a project's creator is its only owner. The membership events that add, change and remove a
member are TODO(#389): each names the member it is about, here and in `roles` together. The
PostgreSQL backend orders a principal's projects by the first event naming them, which is the
creation order only while a creation is the one event that names anyone; #389 keeps that order.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# `dd_harness.projects.PROJECT_CREATED`, which the backends do not import.
_PROJECT_CREATED = "project_created"


def names(event: Mapping[str, Any]) -> str | None:
    """The `principal_id` whose role in the project `event` may change, or None."""
    if event.get("event") == _PROJECT_CREATED:
        found = (event.get("acted_for") or {}).get("principal_id")
        return str(found) if found else None
    return None
