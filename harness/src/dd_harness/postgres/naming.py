"""The SQL that finds a person's projects from `project_events_by_principal`
(`dd_harness.postgres.PostgresProjectLog.projects_naming` and `logs_naming`), kept apart so that
a test can ask the database how it plans each (docs/specs/storage.md, "Listing")."""

from __future__ import annotations

from typing import Any


def projects_naming_query(principal_id: str) -> tuple[str, dict[str, Any]]:
    """The SQL `projects_naming` runs, and its parameters: the projects with an event naming the
    principal, read from `project_events_by_principal` alone, in the order created. A project's
    first event is its creation, appended in the transaction that creates its row, so the place
    of the first event naming a principal orders the projects as they were created."""
    query = (
        "select project_id from project_events where names_principal = %(principal)s"
        " group by project_id order by min(seq)"
    )
    return query, {"principal": principal_id}


def logs_naming_query(principal_id: str) -> tuple[str, dict[str, Any]]:
    """The SQL `logs_naming` runs, and its parameters: every event of each project with an event
    naming the principal, the projects in the order created and each one's events oldest first.
    The projects are found from `project_events_by_principal` and each log is read from
    `project_events_by_project`, so what is read follows the principal's projects, in one query.
    The `order by` inside the lateral subquery keeps the planner from flattening it into a join
    that scans the whole table, which it prefers once a principal has a few hundred projects."""
    query = (
        "select log.project_id, log.event from"
        " (select project_id, min(seq) as first from project_events"
        " where names_principal = %(principal)s group by project_id) as named"
        " cross join lateral (select project_id, event, seq from project_events"
        " where project_events.project_id = named.project_id order by seq) as log"
        " order by named.first, log.seq"
    )
    return query, {"principal": principal_id}


__all__ = ["logs_naming_query", "projects_naming_query"]
