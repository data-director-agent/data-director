"""A README section's gaps and questions, decided by rule before any prose
(docs/specs/drafting.md, invariant 5): its bodies from the facts, the researcher's answer to it as
a whole or to each of its parts, and a question, with the shared field it asks for, for each gap
left (invariant 11)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from dd_agent_advisor_documentation.dictionary import question_id as _question_id
from dd_agent_advisor_documentation.record import _record_general
from dd_agent_advisor_documentation.sections import Section
from dd_sdk.contract.models import DocumentQuestion

# How the draft marks what the researcher writes. A person's edit replaces it.
PLACEHOLDER = "_Still needed: {ask}_"
# What follows a placeholder: the question that asks for it. Not shown in the rendered README.
GAP_MARKER = "<!-- dd:gap {question_id} -->"


@dataclass(frozen=True)
class Outlined:
    """One README section as the rules draft it, before any prose: its bodies from the facts,
    the researcher's answer to it as a whole, its part lines and gap, and the questions asked."""

    section: Section
    bodies: Mapping[str, str]
    answer: str | None = None
    lines: tuple[str, ...] = ()
    questions: tuple[DocumentQuestion, ...] = ()
    answered_parts: int = 0
    complete: bool = False


def outlined(
    section: Section,
    bodies: Mapping[str, str],
    record: Mapping[str, Any] | None,
    answers: Mapping[str, str],
    document: str = "README",
) -> Outlined:
    """A section's gaps and questions, decided by rule (docs/specs/drafting.md, invariant 5)."""
    question_id = _question_id({"section": section.heading})
    answer = answers.get(question_id)
    if answer is not None:
        return Outlined(section, bodies, answer=answer)
    if section.parts:
        # Each part is its own gap and question. An answer to the section as a whole, recorded
        # before it was asked part by part, is placed above and asks nothing.
        given = _record_general(record)
        lines: list[str] = []
        questions: list[DocumentQuestion] = []
        answered = 0
        for part in section.parts:
            if part.given_by and given[part.given_by]:
                continue
            part_id = _question_id({"section": section.heading, "part": part.label})
            part_answer = answers.get(part_id)
            if part_answer is not None:
                lines.append(f"- **{part.label}:** {part_answer}")
                answered += 1
                continue
            marker = GAP_MARKER.format(question_id=part_id)
            lines.append(f"- **{part.label}:** {PLACEHOLDER.format(ask=part.ask)}\n{marker}")
            questions.append(
                DocumentQuestion(
                    question_id=part_id,
                    question_prompt=f"{part.label}: {part.ask}",
                    gap_section=section.heading,
                    gap_part=part.label,
                    shared_field=part.shares,
                )
            )
        return Outlined(section, bodies, None, tuple(lines), tuple(questions), answered)
    if section.complete_from in bodies:
        return Outlined(section, bodies, complete=True)
    marker = GAP_MARKER.format(question_id=question_id)
    question = DocumentQuestion(
        question_id=question_id,
        question_prompt=f"For the {document}'s {section.heading} section: {section.ask}",
        gap_section=section.heading,
        shared_field=section.shares,
    )
    return Outlined(
        section,
        bodies,
        lines=(f"{PLACEHOLDER.format(ask=section.ask)}\n{marker}",),
        questions=(question,),
    )
