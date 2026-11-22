"""What the editor says of a revision a person asked for, and what it keeps as given
(docs/specs/drafting.md, invariant 12): when it declines to revise, which values a person gave
are kept byte for byte, and the outcome's statement."""

from __future__ import annotations

from collections.abc import Sequence

from dd_agent_advisor_documentation.checks import count, listed
from dd_agent_advisor_documentation.outline import Outlined
from dd_agent_advisor_documentation.revise import Revision
from dd_sdk.contract.models import DocumentKind, DraftRequest, ReasonCode

# What the editor does not do when it revises, said in every revision's outcome.
REVISION_LIMITATIONS = (
    "It reads the version you asked to change and your request, never an earlier version or the "
    "reason given for a decision, and does not open the files. A value your request gives counts "
    "as given by you."
)


def revisable(asked: DraftRequest) -> tuple[ReasonCode, str] | None:
    """Why the editor declines to revise what `asked` names, or None if it can."""
    current = asked.current_version
    if asked.document_kind != DocumentKind.README:
        return (
            ReasonCode.OUTSIDE_AGENT_SCOPE,
            "The Documentation Editor revises only a README as you ask, not a "
            f"{asked.document_kind.value.replace('_', ' ')}: edit it yourself, or answer its "
            "questions and draft it again.",
        )
    if current is None or current.revision_request is None:
        return (
            ReasonCode.INSUFFICIENT_INPUT,
            "Say what to change first: no version of the README has a change asked of it.",
        )
    if asked.inventory is None or not asked.inventory.inventory_files:
        return (
            ReasonCode.INSUFFICIENT_INPUT,
            "Add the project's file inventory first: a revision is checked against it.",
        )
    return None


def given_values(asked: DraftRequest, outline: Sequence[Outlined]) -> list[str]:
    """The blocks a revision keeps as they are: the researcher's answers as given, and what the
    rules place from the facts, such as the metadata record's description and the citation."""
    placed = [piece for p in outline for body in p.bodies.values() for piece in body.split("\n\n")]
    return [a.answer_text for a in asked.draft_answers] + placed


def unrevised(revision: Revision) -> str:
    """Why a revision changed nothing, and what the person can do instead."""
    if revision.unused is not None:
        why = revision.unused
    elif revision.dropped:
        why = "none of the model's changes passed the checks (" + "; ".join(revision.dropped) + ")"
    else:
        why = "the model found no change it could make as you asked"
    return (
        f"The README was not changed: {why}. A revision changes only the README's prose, never "
        "a gap, a table or a value you gave: edit the README yourself for those, or answer its "
        "questions and draft it again."
    )


def revised_statement(revision: Revision, gaps: int, asked: int) -> str:
    """What the outcome says of a revision: what changed, what was not used, and the gaps."""
    said = (
        f"A revision of the README as you asked, in the words of a model ({revision.model_id}): "
        f"it changes the prose of {listed(list(revision.changed))}."
    )
    if revision.dropped:
        said += (
            f" It did not use {count(len(revision.dropped), 'change')} the model made: "
            f"{'; '.join(revision.dropped)}."
        )
    said += (
        " It keeps every heading, table and value you gave as it was, and every gap still to "
        f"fill ({count(gaps, 'gap')}), each asked as a question: a revision never fills a gap."
    )
    if asked < gaps:
        said += (
            f" {count(gaps - asked, 'gap')} of them now {'has' if gaps - asked == 1 else 'have'} "
            "an answer: draft the README again to place it."
        )
    return said + " Check the prose before you approve it."
