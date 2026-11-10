"""What the conductor puts into an agent's input from the project the run belongs to
(docs/specs/projects.md, invariant 6).

Three core classes are filled. Within a project:

- a `DraftRequest`'s `inventory`, `requirements`, `metadata_record` and `draft_answers` are the
  project's own: whatever the caller sent is replaced, and a slot the project has no value for
  is removed, so that an agent is never given facts a caller, or a model, made up. The metadata
  record is the version a person approved last, since a drafter treats it as supplied. The
  answers are the latest a person recorded to each question of the project's documents of the
  kind asked for (docs/specs/drafting.md, invariant 6): a drafter marks an answer
  `supplied`, so no caller may send one. The `current_version` is the latest version of the
  project's document of that kind drafted or revised last, or of the one `redraft_document`
  names, so a drafter that revises it makes that document's next version. A `redraft_document`
  that is not the project's, or is of another kind, is refused (`refusal`); outside a project it
  is removed, since it names a project document;
- a plain `FileInventory` is the project's inventory, when it holds one;
- a `Message`'s `project_inventory` says what the project's inventory is, so that an orchestrator
  knows the project holds one without being given its files; its `project_entry` and
  `project_progress` say which entry point the researcher chose and how far each step of the
  process flow has gone, derived from the log on every turn (`dd_harness.progress`); its
  `project_title` is the project's latest title, and `project_title_by_researcher` whether a
  person gave it, so that an orchestrator's model can name a project nobody has named; its
  `project_entry_by_researcher` whether the researcher chose the entry point, so that the model
  can record one it worked out from what they said until they do.

A `Message`'s project slots are the conductor's alone: outside a project they are removed. Any
other input is left as it was sent. The conductor fills the input before hashing it, so the input
hash covers what the agent was shown.

`given` says which classes of project content (invariant 8) a filled input holds, so that the
conductor can refuse to send `documentation` to an agent that calls a hosted model unless the
profile's `hosted_models` allows it. An inventory, and what it is, are `inventory`. A metadata
record, a version to regenerate and a person's answers are `documentation`. A repository's
requirements are the repository's, not the project's, and a `Message`'s entry point and progress
say only which steps of the process flow have gone how far; they are neither. Nor is a project's
title: a name a researcher typed, or a model wrote from what was said in the conversation, which
the model is sent anyway.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dd_harness.progress import ENTRY_BY_RESEARCHER
from dd_harness.projects import TITLE_BY_RESEARCHER
from dd_harness.storage import ProjectStorage
from dd_sdk.contract.models import DocumentKind
from dd_sdk.evidence import input_hash

# The core input classes whose slots the conductor fills from a project.
DRAFT_REQUEST = "DraftRequest"
FILE_INVENTORY = "FileInventory"
MESSAGE = "Message"
# A `Message`'s slots that only the conductor fills.
MESSAGE_PROJECT_SLOTS = (
    "project_inventory",
    "project_entry",
    "project_progress",
    "project_title",
    "project_title_by_researcher",
    "project_entry_by_researcher",
)

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
            for slot in MESSAGE_PROJECT_SLOTS:
                filled.pop(slot, None)
        elif schema_class == DRAFT_REQUEST:
            filled.pop("redraft_document", None)
        return filled
    if schema_class == MESSAGE:
        where = store.progress(project_id)
        summary = store.summary(project_id)
        _put(
            filled,
            {
                "project_inventory": summarise(store, project_id),
                "project_entry": where["entry"],
                # Left out while every step is open, as `project_entry` is until one is chosen.
                "project_progress": [
                    {"step_id": step_id, "step_state": state}
                    for step_id, state in where["steps"].items()
                ]
                or None,
                "project_title": summary["title"],
                # False while the project is untitled too: the model may name it.
                "project_title_by_researcher": summary["title_source"] == TITLE_BY_RESEARCHER,
                # Absent until an entry point is recorded, as `project_entry` is.
                "project_entry_by_researcher": (
                    where["entry_source"] == ENTRY_BY_RESEARCHER
                    if where["entry_source"] is not None
                    else None
                ),
            },
        )
    elif schema_class == DRAFT_REQUEST:
        _put(
            filled,
            {
                "inventory": store.inventory(project_id),
                "requirements": store.requirements(project_id),
                "metadata_record": store.metadata_record(project_id),
                "current_version": _current(store, project_id, filled),
                # Only answers a person recorded may be placed as supplied.
                "draft_answers": _answers(store, project_id, filled.get("document_kind")),
            },
        )
    elif schema_class == FILE_INVENTORY:
        held = store.inventory(project_id)
        if held is not None:
            return dict(held)
    return filled


def refusal(
    store: ProjectStorage | None, project_id: str | None, filled: Mapping[str, Any]
) -> str | None:
    """Why the conductor refuses to run `filled`, an input `give` returned for `project_id`: a
    `DraftRequest` naming a `redraft_document` that is not the project's, or is of another kind.
    None if nothing is refused."""
    named = filled.get("redraft_document")
    if store is None or project_id is None or named is None:
        return None
    try:
        store.current_version(project_id, DocumentKind(str(filled.get("document_kind"))), named)
    except ValueError as exc:  # ProjectError, or a kind that is not one
        return f"redraft_document {named!r}: {exc}"
    return None


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


def _current(
    store: ProjectStorage, project_id: str, filled: Mapping[str, Any]
) -> dict[str, Any] | None:
    """The version a drafter regenerates. None for a kind that is not one, which the request's
    validation then refuses, and for a `redraft_document` that `refusal` refuses."""
    try:
        return store.current_version(
            project_id,
            DocumentKind(str(filled.get("document_kind"))),
            filled.get("redraft_document"),
        )
    except ValueError:  # ProjectError, or a kind that is not one
        return None


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
