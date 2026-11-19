"""The files a metadata record's formats and sizes leave out, and those a person must decide on
(#1072).

The File Archivist's rules (`dd_inventory.hints`) mark a system file, an empty file or a
byte-for-byte copy as rarely deposited, and a file whose name suggests free text, coordinates,
someone else's material or terms as one a person must decide on. The project's decisions on which
files go in stand over them (docs/specs/drafting.md, invariant 9). The statement names every file
left out or to decide on, so nothing is left out unsaid.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from dd_inventory.hints import DepositHints, Hint, deposit_hints
from dd_sdk.contract.facts import FactKind, FileDecision, ProjectFact
from dd_sdk.contract.models import FileInventory


def count(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def kept(
    inventory: FileInventory | None, decisions: Sequence[ProjectFact]
) -> tuple[FileInventory | None, DepositHints]:
    """The inventory without the files a record would rarely describe or a person decided to
    leave out, and the hints that say which files those are and which a person must decide on
    (#1072). A person's decision on a file stands over its hints (docs/specs/drafting.md,
    invariant 9)."""
    if inventory is None:
        return None, DepositHints()
    decided = {
        f.fact_file_path: f.file_decision == FileDecision.INCLUDE
        for f in decisions
        if f.fact_kind == FactKind.FILE_INCLUSION
        and f.fact_file_path is not None
        and f.file_decision in (FileDecision.INCLUDE, FileDecision.EXCLUDE)
    }
    hinted = deposit_hints(
        (f.model_dump(mode="json") for f in inventory.inventory_files), decided=decided
    )
    out = set(hinted.leave_out) | set(hinted.excluded)
    if not out:
        return inventory, hinted
    kept = [f for f in inventory.inventory_files if f.file_path not in out]
    return inventory.model_copy(update={"inventory_files": kept}), hinted


def hinted_statement(hinted: DepositHints) -> str:
    """What the statement says, after a space, of the files the formats and sizes leave out and
    of those a person must decide on; empty when there are none."""

    def named(files: Mapping[str, Sequence[Hint]]) -> str:
        return "; ".join(
            f"{path} ({', '.join(dict.fromkeys(h.kind.value for h in hints))})"
            for path, hints in files.items()
        )

    said = ""
    if hinted.excluded:
        said += (
            f" The formats and sizes leave out {count(len(hinted.excluded), 'file')} the "
            f"project decided to leave out: {'; '.join(hinted.excluded)}."
        )
    if hinted.leave_out:
        said += (
            f" The formats and sizes leave out {count(len(hinted.leave_out), 'file')} rarely "
            f"deposited: {named(hinted.leave_out)}."
        )
    if hinted.decide:
        said += (
            f" A person must decide before deposit on {count(len(hinted.decide), 'file')} they "
            f"count: {named(hinted.decide)}."
        )
    return said
