"""What the conductor puts into an agent's input from the project the run belongs to
(docs/specs/projects.md, invariant 6).

Three core classes are filled. Within a project:

- a `DraftRequest`'s `inventory`, `requirements`, `metadata_record` and `draft_answers` are the
  project's own: whatever the caller sent is replaced, and a slot the project has no value for
  is removed, so that an agent is never given facts a caller, or a model, made up. The metadata
  record is the version a person approved last, since a drafter treats it as supplied. The
  answers are the latest a person recorded to each question of the project's documents of the
  kind asked for (docs/specs/drafting.md, invariant 6): a drafter marks an answer
  `supplied`, so no caller may send one. `current_version` is removed until regeneration is
  filled from the project, TODO(#394);
- a plain `FileInventory` is the project's inventory, when it holds one;
- a `Message`'s `project_inventory` says what the project's inventory is, so that an orchestrator
  knows the project holds one without being given its files.

A `Message`'s `project_inventory` is the conductor's alone: outside a project it is removed. Any
other input is left as it was sent. The conductor fills the input before hashing it, so the input
hash covers what the agent was shown.

`given` says which classes of project content (invariant 8) a filled input holds, so that the
conductor can refuse to send `documentation` to an agent that calls a hosted model unless the
profile's `hosted_models` allows it. An inventory, and what it is, are `inventory`. A metadata
record, a version to regenerate and a person's answers are `documentation`. A repository's
requirements are the repository's, not the project's, and are neither.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dd_harness.storage import ProjectStorage
from dd_sdk.contract.models import DocumentKind
from dd_sdk.evidence import input_hash

# The core input classes whose slots the conductor fills from a project.
DRAFT_REQUEST = "DraftRequest"
FILE_INVENTORY = "FileInventory"
MESSAGE = "Message"

# The classes of project content (docs/specs/projects.md, invariant 8).
INVENTORY = "inventory"
DOCUMENTATION = "documentation"
# A `DraftRequest`'s slots that hold documentation.
DOCUMENTATION_SLOTS = ("metadata_record", "current_version", "draft_answers")


def give(
    store: ProjectStorage | None, project_id: str | None, input_doc: Mapping[str, Any]
) -> dict[str, Any]:
    """`input_doc` with the project's facts put in, for a class that asks for them. With no
    store or no project, only what a caller may never set is removed."""
    filled = dict(input_doc)
    schema_class = filled.get("schema_class")
    if store is None or project_id is None:
        if schema_class == MESSAGE:
            filled.pop("project_inventory", None)
        return filled
    if schema_class == MESSAGE:
        _put(filled, {"project_inventory": summarise(store, project_id)})
    elif schema_class == DRAFT_REQUEST:
        _put(
            filled,
            {
                "inventory": store.inventory(project_id),
                "requirements": store.requirements(project_id),
                "metadata_record": store.metadata_record(project_id),
                "current_version": None,
                # Only answers a person recorded may be placed as supplied.
                "draft_answers": _answers(store, project_id, filled.get("document_kind")),
            },
        )
    elif schema_class == FILE_INVENTORY:
        held = store.inventory(project_id)
        if held is not None:
            return dict(held)
    return filled


def given(
    store: ProjectStorage | None, project_id: str | None, filled: Mapping[str, Any]
) -> frozenset[str]:
    """The classes of project content in `filled`, an input `give` returned for `project_id`.
    Empty outside a project."""
    if store is None or project_id is None:
        return frozenset()
    schema_class = filled.get("schema_class")
    found: set[str] = set()
    if schema_class == MESSAGE and filled.get("project_inventory"):
        found.add(INVENTORY)
    elif schema_class == DRAFT_REQUEST:
        if filled.get("inventory"):
            found.add(INVENTORY)
        if any(filled.get(slot) for slot in DOCUMENTATION_SLOTS):
            found.add(DOCUMENTATION)
    elif schema_class == FILE_INVENTORY and store.inventory(project_id) is not None:
        found.add(INVENTORY)
    return frozenset(found)


def summarise(store: ProjectStorage, project_id: str) -> dict[str, Any] | None:
    """What the project's inventory is, as an `InventorySummary`, or None if it holds none."""
    held = store.inventory(project_id)
    if held is None:
        return None
    summary = {
        "inventory_digest": input_hash(held),
        "inventory_file_count": len(held.get("inventory_files") or []),
        "inventory_tool": held["inventory_tool"],
        "inventory_tool_version": held["inventory_tool_version"],
        "inventory_made_at": held["inventory_made_at"],
    }
    if held.get("inventory_limitations"):
        summary["inventory_limitations"] = list(held["inventory_limitations"])
    return summary


def _answers(store: ProjectStorage, project_id: str, kind: Any) -> list[dict[str, Any]] | None:
    """The recorded answers for a drafter of `kind`. None for a kind that is not one, which
    the request's validation then refuses."""
    try:
        document_kind = DocumentKind(kind)
    except ValueError:
        return None
    return store.answers(project_id, document_kind)


def _put(filled: dict[str, Any], facts: Mapping[str, Any]) -> None:
    """Set each slot to its value, or remove it where the value is None."""
    for slot, value in facts.items():
        if value is None:
            filled.pop(slot, None)
        else:
            filled[slot] = value
