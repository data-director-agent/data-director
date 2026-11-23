"""What a README's version says about itself: the note a `questions` version holds in place of the
README, and what its statement says about the prose."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from dd_agent_advisor_documentation.checks import count, listed
from dd_agent_advisor_documentation.outline import Outlined
from dd_agent_advisor_documentation.prose import Prose
from dd_sdk.contract.models import DraftRequest, FileInventory


def questions_note(
    title: str,
    outline: Sequence[Outlined],
    inventory: FileInventory | None,
    record: Mapping[str, Any] | None,
    asked: DraftRequest,
) -> str:
    """What a `questions` version says in place of the README: what is asked, and what the README
    will be written from. It has no gaps: its questions are on the version. Before the data are
    collected (no inventory, #1017), it says the README plans the documentation instead."""
    known = ["what people in the project decided"]
    if inventory is not None and inventory.inventory_files:
        tables = sum(1 for f in inventory.inventory_files if f.file_fields)
        known = [count(len(inventory.inventory_files), "file")]
        if tables:
            known.append(count(tables, "table"))
    if record is not None:
        known.append("the approved metadata record")
    if asked.project_documents:
        known.append(f"{count(len(asked.project_documents), 'document')} you attached")
    asking = listed([p.section.heading for p in outline if p.questions])
    if inventory is None or not inventory.inventory_files:
        return (
            f"# {title}\n\n"
            "_This is a plan for the README, before your data are collected._ Answering these "
            f"questions now about {asking} records what you expect to produce and what to note "
            "down as you collect. Your answers are kept: once the data exist and the file "
            f"inventory is added, the README is drafted from them and from {listed(known)}, and "
            "you can revise any answer then.\n"
        )
    return (
        f"# {title}\n\n"
        "_This is not the README yet._ Before writing it, the Documentation Editor needs what only "
        f"you can say about {asking}. Answer the questions below, then ask for the README to be "
        f"drafted: it will be written from your answers and from {listed(known)}. Anything you "
        "leave unanswered is marked in the README as still needed.\n"
    )


def how_written(prose: Prose) -> str:
    """What the statement says about the README's prose: who wrote it, and what was not used."""
    if prose.model_id is None:
        return "It was drafted on the template path: no model is configured, so it has no prose."
    if prose.unused:
        return (
            f"It was drafted on the template path, with no prose, because {prose.unused} "
            f"({prose.model_id})."
        )
    said = (
        f"A model ({prose.model_id}) wrote {count(prose.written, 'paragraph')} of prose from "
        "those facts alone"
        if prose.written
        else f"A model ({prose.model_id}) was asked for prose but its draft added none"
    )
    if prose.dropped:
        said += (
            f"; {count(len(prose.dropped), 'paragraph')} it wrote "
            f"{'was' if len(prose.dropped) == 1 else 'were'} not used ("
            + "; ".join(prose.dropped)
            + ")"
        )
    return said + ". Check the prose before you approve it."


def drafted_from(asked: DraftRequest, unread: str | None, *, collected: bool) -> str:
    """What a README's statement says it was drafted from: a plan before the data are collected
    (#1017), the inventory alone, or the approved metadata record too, or why the record was not
    read (`unread`)."""
    if not collected:
        return (
            " It was given no file inventory, so it plans the README before the data are "
            "collected: it asks what you expect to produce and record, and keeps your answers "
            "for the README drafted once the data exist."
        )
    if asked.metadata_record is None:
        return " It was given no approved metadata record, so it drafts from the inventory alone."
    if unread:
        return f" {unread}"
    version = asked.metadata_record.version_ref.version
    return f" It takes what it can from version {version} of the approved metadata record."
