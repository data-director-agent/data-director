"""Offering a person's own answer from one document as a suggestion in another
(docs/specs/drafting.md, invariant 7; #1284).

A drafter names, in a question's `shared_field`, a value every kind of project document gives the
same way: the dataset's title, its creators, its funder. In a project the conductor gives the
drafter `shared_answers`, the latest answer a person recorded on each such field for a document
of another kind, and `project_decisions`, the facts people decided. `offer` puts the answer, or
the decided fact where nobody answered, beside each open question on that field as its
`suggested_answer`, derived as `answer`, with `suggested_from` naming where it came from. It is
never placed in the document: it becomes supplied only when a person saves it there.

A person's own words come before a model's: a drafter calls `offer` first, and asks its model to
suggest only for the questions left without a suggestion.
"""

from __future__ import annotations

from collections.abc import Sequence

from dd_sdk.contract.facts import (
    AffiliationKind,
    FactKind,
    ProjectFact,
    ResearcherRecord,
)
from dd_sdk.contract.questions import (
    SUGGESTED_FROM_DECISION,
    SUGGESTED_FROM_RESEARCHERS,
    Derivation,
    DocumentQuestion,
    SharedAnswer,
    SharedField,
)


def offer(
    questions: Sequence[DocumentQuestion],
    shared: Sequence[SharedAnswer],
    decisions: Sequence[ProjectFact] = (),
    researchers: Sequence[ResearcherRecord] = (),
) -> list[DocumentQuestion]:
    """`questions`, each open one on a shared field offered the person's answer to it in another
    document, or else the fact people decided, or else the project's people, as its suggestion."""
    answered = {a.shared_field: a for a in shared if a.answer_text.strip()}
    decided = decided_values(decisions)
    people = creators_of(researchers)
    out: list[DocumentQuestion] = []
    for q in questions:
        field = q.shared_field
        if field is None or q.suggested_answer is not None:
            out.append(q)
        elif (answer := answered.get(field)) is not None:
            out.append(_offered(q, answer.answer_text, answer.answered_in.value))
        elif (value := decided.get(field)) is not None:
            out.append(_offered(q, value, SUGGESTED_FROM_DECISION))
        elif field == SharedField.CREATORS and people:
            out.append(_offered(q, people, SUGGESTED_FROM_RESEARCHERS))
        else:
            out.append(q)
    return out


def offered(questions: Sequence[DocumentQuestion]) -> int:
    """How many of `questions` offer a person's own words as their suggestion."""
    return sum(q.suggestion_derivation == Derivation.ANSWER for q in questions)


def how_offered(questions: Sequence[DocumentQuestion]) -> str:
    """A sentence for a drafter's statement on the questions that offer a person's own words,
    beginning with a space; empty when none does."""
    n = offered(questions)
    if not n:
        return ""
    return (
        f" {n} question{'' if n == 1 else 's'} offer{'s' if n == 1 else ''} what you gave for "
        "another document, or decided in the project, as a suggestion to confirm here."
    )


def decided_values(decisions: Sequence[ProjectFact]) -> dict[SharedField, str]:
    """The shared fields the project's decided facts give: its funders, by name, and its
    licence."""
    funders = list(
        dict.fromkeys(
            str(f.fact_funder_name)
            for f in decisions
            if f.fact_kind == FactKind.FUNDER and f.fact_funder_name
        )
    )
    licences = [f.licence_id for f in decisions if f.fact_kind == FactKind.LICENCE and f.licence_id]
    out: dict[SharedField, str] = {}
    if funders:
        out[SharedField.FUNDER] = "; ".join(funders)
    if licences:
        out[SharedField.LICENCE] = str(licences[-1])
    return out


def creators_of(researchers: Sequence[ResearcherRecord]) -> str:
    """The project's people who kept a name, one per line as `Name (ORCID iD, employer)`, for the
    creators question; empty when none did. Which of them answers questions about the data is not
    known, so it is left for the person to say."""
    lines: list[str] = []
    for r in researchers:
        name = (r.researcher_name or "").strip()
        if not name:
            continue
        employers = [
            a.organisation_name
            for a in r.affiliations
            if a.affiliation_kind == AffiliationKind.EMPLOYMENT and a.end_year is None
        ]
        details = ", ".join([r.orcid_id, *employers])
        lines.append(f"{name} ({details})")
    return "\n".join(lines)


def _offered(question: DocumentQuestion, text: str, source: str) -> DocumentQuestion:
    return question.model_copy(
        update={
            "suggested_answer": text,
            "suggestion_derivation": Derivation.ANSWER,
            "suggested_from": source,
        }
    )
