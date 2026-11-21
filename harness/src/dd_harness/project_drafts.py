"""What a `Message` is told of a project's inventory revisions and drafted documents
(docs/specs/projects.md, invariant 6), read from the project log on every turn (#1280).

An orchestrator learns of a draft within a turn from the drafter's result, and of earlier drafts
only from its own earlier replies. When a researcher leaves files out in Edit inventory, the
project gains a new inventory without them, and the next draft follows it; an orchestrator that
relied on its replies about an earlier version would say a file is still listed when the latest
version has dropped it. So the conductor says, from the log:

- when the inventory was added and how many files the one it replaced listed (`revision`);
- for each drafted document, its latest version, that version's state, and whether it was
  drafted after the inventory was last added (`drafts`), by the order of the log's events, so
  that no clock is compared.

Neither holds a document's text or a file's name: what a researcher left out is never named, as
the inventory's own limitation does not name it (`inventory/browser/src/omit.ts`).
"""

from __future__ import annotations

from typing import Any

from dd_harness.projects.fold import fold
from dd_harness.projects.rules import DOCUMENT_VERSION_ADDED, INVENTORY_ADDED


def revision(events: list[dict[str, Any]]) -> dict[str, Any]:
    """When the latest inventory was added, and how many files the inventory it replaced listed,
    as `InventorySummary` slots. Empty when the project holds no inventory."""
    added = [e for e in events if e["event"] == INVENTORY_ADDED]
    if not added:
        return {}
    found: dict[str, Any] = {"inventory_added_at": added[-1]["at"]}
    if len(added) > 1:
        found["inventory_revised_from_file_count"] = added[-2]["file_count"]
    return found


def drafts(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The latest version of each document drafted in the project, as `DraftSummary`s, in the
    order first drafted. `drafted_since_inventory` is absent when the project holds no inventory,
    and otherwise says whether the version was added after the inventory added last."""
    inventory_at: int | None = None
    version_at: dict[tuple[str, int], int] = {}
    for position, event in enumerate(events):
        if event["event"] == INVENTORY_ADDED:
            inventory_at = position
        elif event["event"] == DOCUMENT_VERSION_ADDED:
            version_at[(event["document_id"], event["version"])] = position
    found = []
    for document in fold(events).values():
        latest = document["versions"][-1]
        summary: dict[str, Any] = {
            "document_kind": document["document_kind"],
            "version": latest["version"],
            "version_state": latest["state"],
        }
        if inventory_at is not None:
            position = version_at[(document["document_id"], latest["version"])]
            summary["drafted_since_inventory"] = position > inventory_at
        found.append(summary)
    return found
