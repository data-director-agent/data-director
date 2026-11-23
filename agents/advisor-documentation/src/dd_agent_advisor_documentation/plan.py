"""A Data Management Plan, drafted by rule from the project's decisions and the researcher's
answers (docs/specs/drafting.md). Serves `setup.dmp-create`.

The plan's sections are the core requirements of `dd_dmp_template`, after Science Europe's, under
a first section of project details. Each is drafted as a README section is (`outline.py`): what
people in the project decided (the funders, the repository and licence chosen, how sensitive data
are handled, the standards chosen, and the description of the data a person confirmed, from what
the researcher said in any conversation in the project) is placed as given, with the inventory's
files if the data already exist, and what only the researcher can say is a gap with its question.
As a README does, it asks first: before any answer is recorded, the version is a note that asks.
The section on storage and backup offers the institution's storage services, from the deployment's
profile, as a suggestion to its question (`storage`), never placed in the plan.

No model writes the plan's text. Where a model is configured, it may suggest answers to some
sections' questions from the documents the researcher attached, such as a grant application or a
protocol, offered beside the question and never written into the plan
(`suggest_dmp_prompt.md`, docs/specs/drafting.md, invariant 7).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from dd_agent_advisor_documentation import storage
from dd_agent_advisor_documentation.checks import count, listed
from dd_agent_advisor_documentation.dictionary import _answers
from dd_agent_advisor_documentation.drafted import drafted
from dd_agent_advisor_documentation.outline import Outlined, outlined
from dd_agent_advisor_documentation.record import _title
from dd_agent_advisor_documentation.sections import Section, sections_from
from dd_agent_advisor_documentation.suggestions import (
    DOCUMENT_KIND,
    Ask,
    Suggestions,
    how_suggested,
    section_asks,
    with_documents,
)
from dd_dmp_template import SECTIONS
from dd_sdk import shared_answers
from dd_sdk.contract.facts import ProjectFact
from dd_sdk.contract.models import DocumentKind, DocumentQuestion, DraftRequest

TITLE = "Data Management Plan"
# The plan's first section: who and what it is for. A part is not asked when the approved
# metadata record gives it, and a decided funder or the record's title is offered beside it.
DETAILS: dict[str, Any] = {
    "heading": "Project details",
    "from": ["project", "funders"],
    "parts": [
        {
            "label": "Project title",
            "given_by": "title",
            "shares": "title",
            "ask": "the project's title.",
        },
        {
            "label": "Researchers",
            "given_by": "creators",
            "shares": "creators",
            "ask": "who leads the project, by name, and who else works on its data.",
        },
        {
            "label": "Funding",
            "given_by": "funding",
            "shares": "funder",
            "ask": "the funders and grant numbers, or say the project is not funded.",
        },
    ],
}
# For each core requirement (`dd_dmp_template.SECTIONS`, by id): the project facts it is drafted
# from, whether a model may suggest an answer to it (always, or only from attached documents), and
# the value it shares with other documents. Its heading and what it asks are the template's.
SECTION_FACTS: dict[str, dict[str, Any]] = {
    "data-collection": {
        "from": ["data_description", "data_description_so_far", "files"],
        "complete_from": "data_description",
        "suggest": "documents",
    },
    "documentation-quality": {"from": ["standards"], "suggest": "documents"},
    "storage-backup": {"suggest": "documents"},
    "legal-ethical": {"from": ["sensitivity"], "suggest": "documents"},
    # A plan is written before the repository (Phase 3) and the licence (Phase 5) are chosen, so
    # its sharing question asks for what is intended, not what is decided.
    "sharing-preservation": {
        "ask": (
            "what you intend for sharing and long-term preservation: how and when the data will "
            "be shared, under what licence and restrictions, where they will be preserved and "
            "how they will get a persistent identifier. If the repository or licence is not "
            "chosen yet, say what you expect, such as a repository that issues DOIs; the plan "
            "is updated once they are chosen."
        ),
        "from": ["repository", "licence", "licences"],
        "suggest": "documents",
        "shares": "licence",
    },
    "responsibilities-resources": {"suggest": "documents"},
}
# What the editor does not do for a plan, said in every outcome.
LIMITATIONS = (
    "It writes no prose of its own: the plan holds what people in the project decided and what "
    "you answered, as given. It follows one funder-neutral template, after Science Europe's core "
    "requirements; check what your own funder's template asks for besides."
)

type Suggest = Callable[
    [Mapping[str, Any], Sequence[Ask], list[DocumentQuestion]],
    tuple[list[DocumentQuestion], Suggestions],
]


def load_plan_sections() -> list[Section]:
    """The plan's sections: the project details, then the template's core requirements."""
    entries = [DETAILS] + [
        {"heading": s.heading, "ask": s.summary, **SECTION_FACTS[s.id]} for s in SECTIONS
    ]
    return sections_from(entries, "plan.py")


def draft_plan(
    sections: Sequence[Section],
    asked: DraftRequest,
    record: Mapping[str, Any] | None,
    suggest: Suggest,
) -> tuple[str, list[DocumentQuestion], str, Suggestions, bool]:
    """The plan's text, its questions, the statement, the suggestions made, and whether the
    version is a note that asks first rather than the plan itself."""
    answers = _answers(asked.draft_answers)
    outline = [
        outlined(
            section,
            {
                source: body
                for source in section.sources
                if (body := drafted(source, asked, record)) is not None
            },
            record,
            answers,
            document="plan",
        )
        for section in sections
    ]
    questions = [q for planned in outline for q in planned.questions]
    # A person's own words, from another document or a decision, come before a model's.
    questions = shared_answers.offer(
        questions, asked.shared_answers, asked.project_decisions, asked.researchers
    )
    # Then the institution's storage, by rule; a model is asked only about what is left.
    questions = storage.offer(questions, asked)
    questions, suggested = suggest(
        with_documents(plan_facts(asked.project_decisions, record), asked),
        section_asks(sections, questions, has_documents=bool(asked.project_documents)),
        questions,
    )
    title = (_title(record) if record is not None else None) or TITLE
    answered = sum(bool(p.answer or p.answered_parts) for p in outline)
    said = f" {how_suggested(suggested, 'plan')}{shared_answers.how_offered(questions)}"
    if storage.offered(questions):
        said += " The storage question offers your institution's storage services to confirm."
    if asked.current_version is None and questions and not answered:
        statement = (
            f"It asks {count(len(questions), 'question')} before it writes the plan, about "
            f"{listed([p.section.heading for p in outline if p.questions])}. Once they are "
            "answered, drafting the plan again writes it from the answers. This version is a "
            "note, not the plan, and cannot be approved."
        )
        return _note(title, outline, asked), questions, statement + said, suggested, True
    statement = (
        f"A Data Management Plan of {len(sections)} sections, after Science Europe's core "
        f"requirements: {sum(bool(p.bodies) for p in outline)} drafted from what people in the "
        f"project decided, and {answered} written from your answers, as given. It leaves "
        f"{count(len(questions), 'gap')} for you to fill, each marked and asked as a question."
    )
    return _text(title, outline), questions, statement + said, suggested, False


def _text(title: str, outline: Sequence[Outlined]) -> str:
    parts = [f"# {title}"]
    for planned in outline:
        parts.append(f"## {planned.section.heading}")
        parts.extend(planned.bodies.values())
        if planned.answer is not None:
            parts.append(planned.answer)
            continue
        parts.extend(planned.lines)
    return "\n\n".join(parts) + "\n"


def _note(title: str, outline: Sequence[Outlined], asked: DraftRequest) -> str:
    """What a `questions` version says in place of the plan."""
    known = ["what people in the project decided"]
    if asked.inventory is not None and asked.inventory.inventory_files:
        known.append("the file inventory")
    if asked.project_documents:
        known.append(f"{count(len(asked.project_documents), 'document')} you attached")
    asking = listed([p.section.heading for p in outline if p.questions])
    return (
        f"# {title}\n\n"
        "_This is not the plan yet._ Before writing it, the Documentation Editor needs what only "
        f"you can say about {asking}. Answer the questions below, then ask for the plan to be "
        f"drafted: it will be written from your answers and from {listed(known)}. Anything you "
        "leave unanswered is marked in the plan as still needed.\n"
    )


def plan_facts(
    decisions: Sequence[ProjectFact], record: Mapping[str, Any] | None
) -> dict[str, Any]:
    """What a model suggesting a plan's answers is told, besides the attached documents: the
    decisions people made and the approved record's title, never the researcher's answers."""
    facts: dict[str, Any] = {DOCUMENT_KIND: DocumentKind.DMP.value}
    if decisions:
        facts["project_decisions"] = [
            d.model_dump(mode="json", exclude_none=True, exclude={"proposed_because"})
            for d in decisions
        ]
    title = _title(record) if record is not None else None
    if title:
        facts["title"] = title
    return facts
