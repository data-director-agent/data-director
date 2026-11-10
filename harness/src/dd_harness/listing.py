"""Listing runs and conversations a page at a time, for the readers allowed to see them
(docs/specs/storage.md, "Listing").

`RunStorage.list_runs` and `RunStorage.list_conversations` answer with a `Page`. A database backend
answers from an index and reads a page, whatever the size of the store; the file backend scans its
index with `scan_runs` and `scan_conversations`, which define what every backend must return.

Order is the stored order (invariant 3): runs newest first, conversations by their latest turn,
most recent first. A cursor is the stored position of the last item of a page, written in decimal;
the next page holds what was stored before it. Positions start at 1, so a malformed cursor reads as
position 0, before everything, and names an empty page (invariant 8).

`Readable` is which runs a reader may see, as `dd_app.governance` decides it (#153): a run in a
project by whoever may read the project, and a run in no project by the principal it acted for. A
conversation is judged on its first turn, a delegated child by its own envelope, which carries its
parent's `acting_for` and `project_id`.

Which projects a reader may read is found the same way, from what is stored: a project log indexes
the principals each event names (`principals_named`), and `dd_harness.project_access` judges each
project it finds from the project's log.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

# A cursor is a stored position: a positive integer that fits a PostgreSQL `bigint`.
_CURSOR = re.compile(r"[1-9][0-9]{0,18}")
_BIGINT_MAX = 2**63 - 1


@dataclass(frozen=True)
class Readable:
    """Which runs a listing includes: a run in one of `project_ids`, or a run in no project that
    acted for `principal_id`. With `project_ids` None, projects are not consulted and a run is
    included by its principal alone, as an app that keeps no projects decides."""

    principal_id: str
    project_ids: frozenset[str] | None = frozenset()

    def includes(self, envelope: dict[str, Any]) -> bool:
        """Whether the run whose envelope is `envelope` is included."""
        project_id = envelope.get("project_id")
        if project_id and self.project_ids is not None:
            return project_id in self.project_ids
        return principal_of(envelope) == self.principal_id


@dataclass(frozen=True)
class Page:
    """One page of a listing, and the cursor of the next, None on the last."""

    items: list[dict[str, Any]]
    next: str | None = None


def principal_of(envelope: dict[str, Any]) -> str | None:
    """The `principal_id` the run acted for, or None for a run stored before runs named one."""
    acting_for = envelope.get("acting_for") or {}
    found = acting_for.get("principal_id")
    return str(found) if found else None


def principals_named(event: dict[str, Any]) -> frozenset[str]:
    """The `principal_id` of each principal a project event names: whom it acted for, so the
    creator of a project is named by its `project_created` event. TODO(#389): the member a
    membership event adds, removes or changes the role of is named here too, so a project log
    finds a member's projects as it finds a creator's."""
    acted_for = event.get("acted_for") or {}
    found = acted_for.get("principal_id")
    return frozenset({str(found)}) if found else frozenset()


def run_summary(envelope: dict[str, Any]) -> dict[str, Any]:
    """What a list of runs shows of one."""
    return {
        "invocation_id": envelope["invocation_id"],
        "agent_id": envelope["agent_id"],
        "status": envelope["outcome"]["status"],
        "completed_at": envelope["completed_at"],
        # Runs stored before docs/specs/policy-and-identity.md name no principal.
        "acting_for": (envelope.get("acting_for") or {}).get("name"),
    }


def is_turn(envelope: dict[str, Any]) -> bool:
    """Whether the run is a turn of a conversation: it has one and was not delegated."""
    return bool(envelope.get("conversation_id")) and not envelope.get("parent_invocation_id")


def position(before: str | None) -> int:
    """The stored position a page ends before: past the end with no cursor, 0 (before everything)
    for a malformed one."""
    if before is None:
        return _BIGINT_MAX
    if not _CURSOR.fullmatch(before) or int(before) > _BIGINT_MAX:
        return 0
    return int(before)


def check_limit(limit: int) -> None:
    """Refuse a page that could hold nothing."""
    if limit < 1:
        raise ValueError(f"a page holds at least one item, not {limit}")


def paged(rows: list[tuple[int, dict[str, Any]]], limit: int) -> Page:
    """A page from up to `limit + 1` (position, item) pairs, newest first: the extra one says
    there is a next page."""
    items = rows[:limit]
    more = len(rows) > limit
    return Page([item for _, item in items], str(items[-1][0]) if more else None)


def scan_runs(
    envelopes: Iterable[dict[str, Any]],
    *,
    readable: Readable | None,
    limit: int,
    before: str | None,
) -> Page:
    """`list_runs` over every envelope in stored order, as a backend without an index answers."""
    check_limit(limit)
    end = position(before)
    found = [
        (n, run_summary(e))
        for n, e in enumerate(envelopes, start=1)
        if n < end and (readable is None or readable.includes(e))
    ]
    found.reverse()
    return paged(found[: limit + 1], limit)


def scan_conversations(
    envelopes: Iterable[dict[str, Any]],
    *,
    readable: Readable | None,
    limit: int,
    before: str | None,
) -> Page:
    """`list_conversations` over every envelope in stored order, as a backend without an index
    answers."""
    check_limit(limit)
    end = position(before)
    summaries: dict[str, tuple[int, dict[str, Any]]] = {}
    excluded: set[str] = set()
    for n, envelope in enumerate(envelopes, start=1):
        if not is_turn(envelope):
            continue
        conversation_id = envelope["conversation_id"]
        if conversation_id in excluded:
            continue
        if conversation_id not in summaries:
            if readable is not None and not readable.includes(envelope):
                excluded.add(conversation_id)
                continue
            summaries[conversation_id] = (n, conversation_summary(envelope))
        _, summary = summaries[conversation_id]
        summary["turns"] += 1
        summary["last_completed_at"] = envelope["completed_at"]
        summary["last_status"] = envelope["outcome"]["status"]
        summaries[conversation_id] = (n, summary)
    found = sorted(
        ((n, s) for n, s in summaries.values() if n < end), key=lambda pair: pair[0], reverse=True
    )
    return paged(found[: limit + 1], limit)


def conversation_summary(first_turn: dict[str, Any]) -> dict[str, Any]:
    """A conversation's summary as its first turn begins it, with no turn counted yet."""
    return {
        "conversation_id": first_turn["conversation_id"],
        # The conductor gives every turn of a conversation the same project, if any.
        "project_id": first_turn.get("project_id"),
        "agent_id": first_turn["agent_id"],
        "first_invocation_id": first_turn["invocation_id"],
        "turns": 0,
        "started_at": first_turn["completed_at"],
        "last_completed_at": first_turn["completed_at"],
        "last_status": first_turn["outcome"]["status"],
    }
