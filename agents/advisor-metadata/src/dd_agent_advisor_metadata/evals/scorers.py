"""The Metadata Librarian's own scorers: the categories it suggests from the repository's
controlled vocabulary, whether each cites a vocabulary record, the questions it must ask, and the
values it must leave for the researcher.

A category is a subject entry the repository qualifies with a `subjectScheme`, such as ORDA's
ANZSRC Fields of Research; a question on it is found by its `gap_property` and the entry's
qualifier in the drafted record, not by its wording.
"""

from __future__ import annotations

import json
import re
from typing import Any

from inspect_ai.scorer import NOANSWER, Score, Scorer, Target, scorer
from inspect_ai.solver import TaskState

from workbench.evaluation import envelope_of, expectation_of, mean_applicable, recall

_SUBJECT = re.compile(r"^subjects\[(\d+)\]\.subject$")
# The evidence item that cites the librarian's own input, not a record it retrieved.
_INPUT = "input:"


def _drafted(state: TaskState) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """The payload and the record drafted in it; none for a run with no payload."""
    payload: dict[str, Any] | None = envelope_of(state).get("payload")
    if not payload or "document_text" not in payload:
        return None
    return payload, json.loads(payload["document_text"])


def _category_questions(payload: dict[str, Any], record: dict[str, Any]) -> list[dict[str, Any]]:
    """The questions on subject entries a vocabulary qualifies."""
    entries = record.get("subjects") or []
    found = []
    for question in payload.get("document_questions") or []:
        match = _SUBJECT.match(question.get("gap_property") or "")
        if match and int(match[1]) < len(entries) and entries[int(match[1])].get("subjectScheme"):
            found.append(question)
    return found


def _suggested(state: TaskState) -> list[str]:
    """The categories suggested on category questions, in the order asked."""
    drafted = _drafted(state)
    if drafted is None:
        return []
    return [
        q["suggested_answer"] for q in _category_questions(*drafted) if q.get("suggested_answer")
    ]


def _matches(answer: str, code: str, label: str) -> bool:
    words = answer.casefold()
    return words.startswith(code) or label.casefold() in words


@scorer(metrics=[mean_applicable()])
def subjects_recalled() -> Scorer:
    """The share of the categories a curator would choose (`subjects`) that the librarian
    suggests on a category question, by code or label, with each one missed in the score's
    metadata. Does not apply to a case that names none."""

    async def score(state: TaskState, target: Target) -> Score:
        wanted: dict[str, str] = {
            str(k): v for k, v in (expectation_of(state).get("subjects") or {}).items()
        }
        if not wanted:
            return Score(value=NOANSWER, explanation="the case names no category")
        offered = _suggested(state)
        missing = [
            c for c, label in wanted.items() if not any(_matches(a, c, label) for a in offered)
        ]
        return recall(
            list(wanted), missing, "all suggested", "; ".join(offered) or "none suggested"
        )

    return score


@scorer(metrics=[mean_applicable()])
def terms_cited() -> Scorer:
    """The share of the categories suggested that a retrieved record in the evidence gives, by
    the suggested term appearing in the record's content: each suggested term cites the
    vocabulary record it came from (#703). Does not apply to a run that suggests no category."""

    async def score(state: TaskState, target: Target) -> Score:
        offered = _suggested(state)
        if not offered:
            return Score(value=NOANSWER, explanation="no category was suggested")
        records = [
            json.dumps(e.get("content"), ensure_ascii=False).casefold()
            for e in envelope_of(state).get("evidence") or []
            if not str(e.get("source_id", "")).startswith(_INPUT)
        ]
        uncited = [a for a in offered if not any(a.casefold() in r for r in records)]
        return Score(
            value=(len(offered) - len(uncited)) / len(offered),
            answer=f"{len(offered) - len(uncited)}/{len(offered)}",
            explanation="uncited: " + "; ".join(uncited) if uncited else "all cited",
            metadata={"uncited": uncited},
        )

    return score


def _asked_about(payload: dict[str, Any]) -> set[str]:
    """The properties the questions ask about, by the first name in each `gap_property`."""
    return {
        re.split(r"[.\[]", q["gap_property"])[0]
        for q in payload.get("document_questions") or []
        if q.get("gap_property")
    }


@scorer(metrics=[mean_applicable()])
def questions_asked() -> Scorer:
    """The share of the properties the case names in `asked` that some question asks about, with
    each one missed in the score's metadata. Does not apply to a case that names none."""

    async def score(state: TaskState, target: Target) -> Score:
        wanted = list(expectation_of(state).get("asked") or [])
        if not wanted:
            return Score(value=NOANSWER, explanation="the case names no property to ask about")
        drafted = _drafted(state)
        asked = _asked_about(drafted[0]) if drafted else set()
        return recall(wanted, [p for p in wanted if p not in asked], "all asked")

    return score


def _empty(value: Any) -> bool:
    """Whether a property's value holds nothing but nulls and the qualifiers beside them."""
    if value is None:
        return True
    if isinstance(value, list):
        return all(_empty(v) for v in value)
    if isinstance(value, dict):
        return all(
            v is None or (isinstance(v, str) and k.endswith(("Type", "Scheme")))
            for k, v in value.items()
        )
    return False


@scorer(metrics=[mean_applicable()])
def nothing_placed() -> Scorer:
    """Whether every property the case names in `never_placed`, which only the researcher can
    give, is left null in the record (docs/specs/drafting.md). Does not apply to a case that names
    none."""

    async def score(state: TaskState, target: Target) -> Score:
        wanted = list(expectation_of(state).get("never_placed") or [])
        if not wanted:
            return Score(value=NOANSWER, explanation="the case names no property to leave null")
        drafted = _drafted(state)
        if drafted is None:
            return Score(value=NOANSWER, explanation="the run drafted no record")
        placed = [p for p in wanted if not _empty(drafted[1].get(p))]
        return Score(
            value=0.0 if placed else 1.0,
            answer=", ".join(placed) or "none placed",
            explanation="placed: " + ", ".join(placed) if placed else "all left null",
            metadata={"placed": placed},
        )

    return score
