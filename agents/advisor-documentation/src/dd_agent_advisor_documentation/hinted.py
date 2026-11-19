"""The files a draft leaves out, and those a person must decide on (#1072).

The File Archivist's rules (`dd_inventory.hints`) mark a system file, an empty file or a
byte-for-byte copy as rarely deposited, and a file whose name suggests free text, coordinates,
someone else's material or terms as one a person must decide on. The README lists both under
Files, and asks a question about each of the latter; the statement of either document names
them, so nothing is left out unsaid.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from dd_agent_advisor_documentation.gaps import GAP_MARKER, PLACEHOLDER, question_id
from dd_agent_advisor_documentation.prose import count
from dd_inventory.hints import DepositHints, Hint, HintKind
from dd_sdk.contract.models import DocumentQuestion, FileInventory

# What a README says above the files it proposes to leave out, and those a person decides on.
LEFT_OUT_HEADING = (
    "**Proposed for exclusion.** These files are not in the table above, because a file of this "
    "kind is rarely part of a dataset. Include one only if it is:"
)
DECIDE_HEADING = (
    "**Decide before deposit.** These files are in the table above, but their names suggest "
    "that a person must decide whether, and how, they are deposited:"
)
DECIDE_ASK = "{reasons} Say whether it is deposited as it is, changed, or left out."


def without(inventory: FileInventory, hinted: DepositHints) -> FileInventory:
    """The inventory without the files the draft proposes to leave out."""
    if not hinted.leave_out:
        return inventory
    kept = [f for f in inventory.inventory_files if f.file_path not in hinted.leave_out]
    return inventory.model_copy(update={"inventory_files": kept})


def _reasons(hints: Sequence[Hint]) -> str:
    """Why a file was marked: each hint's question, and the files a copy is a copy of."""
    said = []
    for h in hints:
        if h.kind == HintKind.DUPLICATE and h.related_paths:
            copies = ", ".join(f"`{p}`" for p in h.related_paths)
            said.append(f"It is a byte-for-byte copy of {copies}, which is kept.")
        else:
            said.append(h.question)
    return " ".join(dict.fromkeys(said))


def hinted_files(
    heading: str,
    hinted: DepositHints,
    answers: Mapping[str, str],
    questions: list[DocumentQuestion],
) -> list[str]:
    """The Files section's lists of the files left out and of those a person decides on, each
    of the latter asked as a part of the section (#1072)."""
    out: list[str] = []
    if hinted.leave_out:
        lines = [f"- `{path}`: {_reasons(hints)}" for path, hints in hinted.leave_out.items()]
        out.append(LEFT_OUT_HEADING + "\n\n" + "\n".join(lines))
    if hinted.decide:
        lines = []
        for path, hints in hinted.decide.items():
            part_id = question_id({"section": heading, "part": path})
            answer = answers.get(part_id)
            if answer is not None:
                lines.append(f"- **{path}:** {answer}")
                continue
            ask = DECIDE_ASK.format(reasons=_reasons(hints))
            marker = GAP_MARKER.format(question_id=part_id)
            lines.append(f"- **{path}:** {PLACEHOLDER.format(ask=ask)}\n{marker}")
            questions.append(
                DocumentQuestion(
                    question_id=part_id,
                    question_prompt=f"{path}: {ask}",
                    gap_section=heading,
                    gap_part=path,
                )
            )
        out.append(DECIDE_HEADING + "\n\n" + "\n".join(lines))
    return out


def _named(files: Mapping[str, Sequence[Hint]]) -> str:
    return "; ".join(
        f"{path} ({', '.join(dict.fromkeys(h.kind.value for h in hints))})"
        for path, hints in files.items()
    )


def hinted_statement(hinted: DepositHints, document: str) -> str:
    """What the statement says, after a space, of the files left out and of those a person
    decides on; empty when there are none."""
    said = ""
    if hinted.leave_out:
        said += (
            f" It leaves {count(len(hinted.leave_out), 'file')} out of the {document}, as files "
            f"rarely deposited: {_named(hinted.leave_out)}."
        )
    if hinted.decide:
        said += (
            f" A person must decide before deposit on {count(len(hinted.decide), 'file')} it "
            f"keeps: {_named(hinted.decide)}."
        )
    return said
