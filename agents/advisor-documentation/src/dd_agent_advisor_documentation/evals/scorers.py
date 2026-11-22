"""The Documentation Editor's own scorers: whether every value in its draft says truly where it
came from, whether it asks about every gap, and how its inferences and suggestions compare with the
crib sheet's true values.

Each is a separate score, never blended with another (docs/specs/evaluation.md, invariant 4). A
scorer that does not apply to a case, such as a data dictionary scorer on a README, returns
NOANSWER and is left out of the mean.
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Iterable, Mapping
from typing import Any

from inspect_ai.scorer import CORRECT, INCORRECT, NOANSWER, Score, Scorer, Target, scorer
from inspect_ai.solver import TaskState

from dd_agent_advisor_documentation.checks import NAMED, NOT_PROSE
from dd_agent_advisor_documentation.dictionary import (
    SOURCE_SUFFIX,
    VALUE_COLUMNS,
    Source,
    asks_about,
    worked_out_unit_code,
)
from dd_agent_advisor_documentation.drafted import drafted
from dd_agent_advisor_documentation.outline import GAP_MARKER
from dd_agent_advisor_documentation.readme_facts import _facts
from dd_agent_advisor_documentation.record import _record
from dd_agent_advisor_documentation.sections import SOURCES as FACT_SOURCES
from dd_agent_advisor_documentation.sections import load_sections
from dd_sdk.contract.models import DraftRequest
from workbench.evaluation import envelope_of, expectation_of, mean_applicable

GAP = re.compile(GAP_MARKER.format(question_id=r"(q-[0-9a-f]+)"))
SOURCES = frozenset(s.value for s in Source)
# What a dictionary column's suggestion is compared with in the gold.
GOLD_KEYS = {"description": ("definition", "definition_wrong"), "unit": ("unit", "unit_wrong")}


# --- What a case produced ---------------------------------------------------------------------


def request_of(state: TaskState) -> DraftRequest:
    return DraftRequest.model_validate_json(state.input_text)


def document_of(state: TaskState) -> dict[str, Any] | None:
    """The `Document` the editor returned, or None if it stopped."""
    envelope = envelope_of(state)
    if envelope["outcome"]["status"] != "succeeded":
        return None
    payload: dict[str, Any] | None = envelope.get("payload")
    return payload


def dictionary_rows(document: Mapping[str, Any]) -> list[dict[str, str]] | None:
    if document.get("document_kind") != "data_dictionary":
        return None
    return list(csv.DictReader(io.StringIO(document["document_text"])))


def cell_questions(document: Mapping[str, Any]) -> dict[tuple[str, str, str], dict[str, Any]]:
    """Each data dictionary cell a question fills, by file, field and column: a question about a
    column several files share fills that column's cell in each of its `gap_files`."""
    return {
        (file, q["gap_field"], q["gap_column"]): q
        for q in document.get("document_questions", [])
        if q.get("gap_file") is not None
        for file in q.get("gap_files") or [q["gap_file"]]
    }


def answers_of(state: TaskState) -> list[dict[str, Any]]:
    answers: list[dict[str, Any]] = state.metadata.get("answers", [])
    return answers


def gold_of(state: TaskState) -> dict[str, dict[str, Any]]:
    gold: dict[str, dict[str, Any]] = state.metadata.get("gold", {})
    return gold


def _not_applicable(why: str) -> Score:
    return Score(value=NOANSWER, explanation=why)


def _share(good: int, total: int, problems: list[str], what: str) -> Score:
    if not total:
        return _not_applicable(f"no {what} to score")
    return Score(
        value=good / total,
        answer=f"{good}/{total}",
        explanation="; ".join(problems[:20]) or "none",
        metadata={"problems": problems},
    )


def mentions(text: str, phrases: Iterable[str]) -> list[str]:
    """The phrases `text` names as a whole word or symbol, ignoring case."""
    folded = text.casefold()
    return [p for p in phrases if re.search(rf"(?<!\w){re.escape(p.casefold())}(?!\w)", folded)]


# --- The data dictionary ----------------------------------------------------------------------


@scorer(metrics=[mean_applicable()])
def every_cell_sourced() -> Scorer:
    """Every value in the data dictionary has a source from the vocabulary, and a cell is filled
    exactly when its source is not `unknown`."""

    async def score(state: TaskState, target: Target) -> Score:
        document = document_of(state)
        rows = dictionary_rows(document) if document else None
        if rows is None:
            return _not_applicable("not a data dictionary")
        problems = []
        for row in rows:
            for column in VALUE_COLUMNS:
                value, source = row.get(column) or "", row.get(column + SOURCE_SUFFIX)
                where = f"{row['file']} {row['field']} {column}"
                if source not in SOURCES:
                    problems.append(f"{where}: source {source!r}")
                elif bool(value) == (source == Source.UNKNOWN):
                    problems.append(f"{where}: {value!r} marked {source}")
        return Score(
            value=INCORRECT if problems else CORRECT,
            answer=str(len(problems)),
            explanation="; ".join(problems[:20]) or "none",
            metadata={"problems": problems},
        )

    return score


@scorer(metrics=[mean_applicable()])
def no_model_value_in_cell() -> Scorer:
    """No value is in a cell that its source does not account for: an `inferred` value is the
    inventory's, or the unit code the rule gives the row's unit, and a `supplied` one is the
    inventory's description or the researcher's recorded answer for that cell. Anything else came
    from somewhere a person did not see, such as a model."""

    async def score(state: TaskState, target: Target) -> Score:
        document = document_of(state)
        rows = dictionary_rows(document) if document else None
        if rows is None:
            return _not_applicable("not a data dictionary")
        inventory = request_of(state).inventory
        given: dict[tuple[str, str], dict[str, str | None]] = {}
        for f in inventory.inventory_files if inventory else []:
            for c in f.file_fields:
                given[(f.file_path, c.name)] = {
                    "type": c.field_type,
                    "format": c.field_format,
                    "description": c.field_description,
                }
        answered = {
            (a["file"], a["field"], a["column"]): a["text"]
            for a in answers_of(state)
            if "column" in a
        }
        problems = []
        for row in rows:
            key = (row["file"], row["field"])
            for column in VALUE_COLUMNS:
                value, source = row.get(column) or "", row.get(column + SOURCE_SUFFIX)
                if source not in SOURCES or source == Source.UNKNOWN or not value:
                    continue  # every_cell_sourced scores these
                inferred = given.get(key, {}).get(column)
                if column == "unit_code":
                    inferred = worked_out_unit_code(row.get("unit") or "")
                accounted = {
                    Source.INFERRED: {inferred},
                    Source.SUPPLIED: {
                        given.get(key, {}).get("description") if column == "description" else None,
                        answered.get((*key, column)),
                    },
                }.get(Source(str(source)), set())
                if value not in accounted:
                    problems.append(f"{row['file']} {row['field']} {column}: {value!r} ({source})")
        return Score(
            value=INCORRECT if problems else CORRECT,
            answer=str(len(problems)),
            explanation="; ".join(problems[:20]) or "none",
            metadata={"problems": problems},
        )

    return score


@scorer(metrics=[mean_applicable()])
def unknown_cells_asked() -> Scorer:
    """Of the unknown cells it may ask about and the cells asked about, the share that are both:
    every such cell has its question, and no question asks about a cell that is filled. A unit
    code is not asked while the unit it is worked out from is unknown."""

    async def score(state: TaskState, target: Target) -> Score:
        document = document_of(state)
        rows = dictionary_rows(document) if document else None
        if rows is None or document is None:
            return _not_applicable("not a data dictionary")
        unknown = {
            (row["file"], row["field"], column)
            for row in rows
            for column in VALUE_COLUMNS
            if row.get(column + SOURCE_SUFFIX) == Source.UNKNOWN and asks_about(column, row)
        }
        asked = set(cell_questions(document))
        problems = [f"{' '.join(k)}: not asked" for k in sorted(unknown - asked)] + [
            f"{' '.join(k)}: asked but not unknown" for k in sorted(asked - unknown)
        ]
        return _share(len(unknown & asked), len(unknown | asked), problems, "unknown cells")

    return score


@scorer(metrics=[mean_applicable()])
def inferred_types_match_gold() -> Scorer:
    """Of the fields the crib sheet gives a type for, the share whose `inferred` type agrees. A
    type marked `inferred` that is wrong tells the researcher a falsehood they may not check."""

    async def score(state: TaskState, target: Target) -> Score:
        document = document_of(state)
        rows = dictionary_rows(document) if document else None
        gold = gold_of(state)
        if rows is None or not gold:
            return _not_applicable("not a data dictionary with gold")
        good = total = 0
        problems = []
        for row in rows:
            want = gold.get(row["field"], {}).get("type")
            if want is None or row.get("type_source") != Source.INFERRED:
                continue
            total += 1
            if row["type"] == want:
                good += 1
            else:
                problems.append(f"{row['file']} {row['field']}: {row['type']}, not {want}")
        return _share(good, total, problems, "inferred types with gold")

    return score


@scorer(metrics=[mean_applicable()])
def suggestions_match_gold() -> Scorer:
    """Of the suggested definitions and units the crib sheet can judge, the share that agree with
    it: naming an accepted value, and nothing that would make it confidently wrong (such as `%`
    for a soil moisture field recorded in raw counts). Does not apply when nothing was suggested,
    as on the template path."""

    async def score(state: TaskState, target: Target) -> Score:
        document = document_of(state)
        gold = gold_of(state)
        if document is None or document.get("document_kind") != "data_dictionary" or not gold:
            return _not_applicable("not a data dictionary with gold")
        good = total = 0
        problems = []
        for (file, field, column), q in sorted(cell_questions(document).items()):
            suggestion = q.get("suggested_answer")
            if not suggestion or column not in GOLD_KEYS:
                continue
            accepted_key, wrong_key = GOLD_KEYS[column]
            accepted = gold.get(field, {}).get(accepted_key)
            if not accepted:
                continue
            total += 1
            wrong = mentions(suggestion, gold[field].get(wrong_key, []))
            if mentions(suggestion, accepted) and not wrong:
                good += 1
            else:
                why = f"names {', '.join(wrong)}" if wrong else "names no accepted value"
                problems.append(f"{file} {field} {column}: {suggestion!r} {why}")
        return _share(good, total, problems, "suggestions with gold")

    return score


# --- The README -------------------------------------------------------------------------------


def readme_of(state: TaskState) -> dict[str, Any] | None:
    document = document_of(state)
    if document is None or document.get("document_kind") != "readme":
        return None
    return document


def _gap_name(q: Mapping[str, Any]) -> str:
    return str(q["gap_section"]) + (f"/{q['gap_part']}" if q.get("gap_part") else "")


@scorer(metrics=[mean_applicable()])
def required_sections_present() -> Scorer:
    """The README has every section of `readme.yaml`, in order. Does not apply to a note that
    asks before the README is written."""

    async def score(state: TaskState, target: Target) -> Score:
        document = readme_of(state)
        if document is None:
            return _not_applicable("not a README")
        if document.get("document_stage") == "questions":
            return _not_applicable("a note that asks first, not the README")
        headings = re.findall(r"^## (.+)$", document["document_text"], re.MULTILINE)
        wanted = [s.heading for s in load_sections()]
        ok = [h for h in headings if h in wanted] == wanted
        return Score(
            value=CORRECT if ok else INCORRECT,
            explanation="all, in order" if ok else f"found {headings}, wanted {wanted}",
        )

    return score


@scorer(metrics=[mean_applicable()])
def every_gap_marked_and_asked() -> Scorer:
    """Of the README's gap markers and its questions, the share that match: every marked gap is
    asked, and every question has its marker."""

    async def score(state: TaskState, target: Target) -> Score:
        document = readme_of(state)
        if document is None:
            return _not_applicable("not a README")
        marked = set(GAP.findall(document["document_text"]))
        asked = {q["question_id"] for q in document.get("document_questions", [])}
        if document.get("document_stage") == "questions":
            # A note that asks before the README is written: it asks, and marks nothing.
            problems = [f"{q}: marked in a note" for q in sorted(marked)]
            problems += [] if asked else ["asks nothing"]
            return _share(int(not problems), 1, problems, "notes")
        problems = [f"{q}: marked, not asked" for q in sorted(marked - asked)] + [
            f"{q}: asked, not marked" for q in sorted(asked - marked)
        ]
        return _share(len(marked & asked), len(marked | asked), problems, "gaps")

    return score


@scorer(metrics=[mean_applicable()])
def expected_content_present() -> Scorer:
    """The share of the case's README expectations met: each `present` text is in the README,
    each `asked` gap is asked and each `not_asked` gap is not."""

    async def score(state: TaskState, target: Target) -> Score:
        document = readme_of(state)
        expect = expectation_of(state)
        if document is None:
            return _not_applicable("not a README")
        text = document["document_text"]
        asked = {
            _gap_name(q) for q in document.get("document_questions", []) if q.get("gap_section")
        }
        checks = (
            [(t in text, f"{t!r} missing") for t in expect.get("present", [])]
            + [(g in asked, f"{g} not asked") for g in expect.get("asked", [])]
            + [(g not in asked, f"{g} asked") for g in expect.get("not_asked", [])]
        )
        problems = [why for ok, why in checks if not ok]
        return _share(sum(ok for ok, _ in checks), len(checks), problems, "expectations")

    return score


@scorer(metrics=[mean_applicable()])
def no_unsupported_claim() -> Scorer:
    """Every paragraph of a README that a model wrote names only what the facts it was given
    contain: every number, link, DOI, email address, ORCID iD and code-formatted name. The
    paragraphs drafted by rule from a project fact and the researcher's answers are left out: a
    model wrote neither. Does not apply to a version drafted by template."""

    async def score(state: TaskState, target: Target) -> Score:
        document = readme_of(state)
        if document is None:
            return _not_applicable("not a README")
        if document.get("document_derivation") != "model":
            return _not_applicable("no prose written by a model")
        asked = request_of(state)
        record, _ = _record(asked.metadata_record)
        assert asked.inventory is not None  # a README was drafted, so there was an inventory
        # Once the researcher has answered, the model is also given the answers, the decisions
        # and the documents they attached, so what they name is supported too.
        known = json.dumps(
            _facts(asked.inventory, asked.requirements, record), ensure_ascii=False, sort_keys=True
        ) + json.dumps(
            [a.answer_text for a in asked.draft_answers]
            + [d.documentation_text for d in asked.project_documents]
            + [d.model_dump(mode="json") for d in asked.project_decisions],
            ensure_ascii=False,
        )
        not_model = {" ".join(a.answer_text.split()) for a in asked.draft_answers} | {
            " ".join(body.split())
            for source in FACT_SOURCES
            if (body := drafted(source, asked, record))
        }
        problems = []
        for paragraph in document["document_text"].split("\n\n"):
            flat = " ".join(paragraph.split())
            if not flat or NOT_PROSE.search(paragraph) or flat in not_model:
                continue
            for pattern in NAMED:
                for match in pattern.finditer(flat):
                    named = match.group(match.lastindex or 0)
                    if named not in known:
                        problems.append(f"{named!r} in {flat[:60]!r}")
        return Score(
            value=INCORRECT if problems else CORRECT,
            answer=str(len(problems)),
            explanation="; ".join(problems[:20]) or "none",
            metadata={"problems": problems},
        )

    return score


def _written_from(answer: Mapping[str, Any], document: Mapping[str, Any]) -> bool:
    """Whether a model wrote a README section from `answer` in its own words and kept every
    number, link, identifier and code-formatted name the answer gives. Only an answer to a whole
    section is written so; a part's is placed as given."""
    if "part" in answer or document.get("document_derivation") != "model":
        return False
    text = document["document_text"]
    named = [m.group(m.lastindex or 0) for p in NAMED for m in p.finditer(answer["text"])]
    return all(n in text for n in named)


# --- Both kinds -------------------------------------------------------------------------------


@scorer(metrics=[mean_applicable()])
def answers_placed_supplied() -> Scorer:
    """The share of the researcher's recorded answers placed as given and not asked again: in a
    data dictionary, in their cell and marked `supplied`; in a README, in its text. Does not apply
    to a case with no answers."""

    async def score(state: TaskState, target: Target) -> Score:
        answers = answers_of(state)
        document = document_of(state)
        if not answers or document is None:
            return _not_applicable("no answers recorded")
        asked = {q["question_id"] for q in document.get("document_questions", [])}
        rows = {(r["file"], r["field"]): r for r in dictionary_rows(document) or []}
        problems = []
        for a in answers:
            if a["question_id"] in asked:
                problems.append(f"{a['question_id']}: asked again")
            elif "column" in a:
                row = rows.get((a["file"], a["field"]), {})
                if row.get(a["column"]) != a["text"]:
                    problems.append(f"{a['field']} {a['column']}: not placed as given")
                elif row.get(a["column"] + SOURCE_SUFFIX) != Source.SUPPLIED:
                    problems.append(f"{a['field']} {a['column']}: not marked supplied")
            elif a["text"] not in document["document_text"] and not _written_from(a, document):
                problems.append(f"{a['section']}: not placed as given")
        return _share(len(answers) - len(problems), len(answers), problems, "answers")

    return score
