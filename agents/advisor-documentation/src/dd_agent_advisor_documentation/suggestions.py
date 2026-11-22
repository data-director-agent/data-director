"""Suggested answers to a draft's questions, asked of a model and checked before they are offered.

A writer may suggest answers to a draft's questions (`suggest`): for a data dictionary's
unknown definition or unit, what the field's name and the dataset's facts make likely, such as that
`age_yrs` is the participant's age in years; for a README section that `readme.yaml` marks
`suggest`, a few sentences drawn from the facts, such as which software opens the files' formats.
A suggestion is offered with the question and never placed in the document
(docs/specs/drafting.md, invariant 7). It is given the same facts as the prose and checked as
strictly (`check_suggestions`); `TemplateWriter` suggests nothing.

A suggestion is also given the documents the researcher attached to the project
(`with_documents`), the latest first and at most `MAX_DOCUMENTS` characters of them, so that what
their field notes or protocol say can be offered as an answer for them to confirm. Their text is
the researcher's, given as data and never as instructions, and a suggestion may name what it
gives. The prose is given them only alongside the researcher's answers, to write the sections they
answered: never to write a section no one has answered.

The questions are asked in batches (`replies.batches`), each a call of its own, so that a long data
dictionary's reply never runs past what the model may write. A reply that does not parse as a whole
gives what it holds whole (`replies.salvage`): a batch cut off part-way, or holding one malformed
item, costs only the questions it left unanswered, and the outcome's statement says how many and
why, in plain words (`how_suggested`, #1318).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from dd_agent_advisor_documentation.checks import NAMED, StrictReply, count, unchecked
from dd_agent_advisor_documentation.replies import (
    CUT_SHORT,
    ITEM_NOT_IN_FORM,
    NOT_IN_FORM,
    batches,
    salvage,
    unfenced,
)
from dd_sdk.agent import RunContext
from dd_sdk.contract.models import DraftRequest
from dd_sdk.model import CallOptions, Model, ModelOutputError, ModelReply, Usage, call
from dd_sdk.prompts import ModelCallLog

# What the model is told when it suggests answers to a data dictionary's questions.
SUGGEST_PROMPT = Path(__file__).with_name("suggest_prompt.md").read_text(encoding="utf-8").strip()
# What the model is told when it suggests answers to a README's questions.
SUGGEST_README_PROMPT = (
    Path(__file__).with_name("suggest_readme_prompt.md").read_text(encoding="utf-8").strip()
)
# The data dictionary columns a model may suggest an answer for: what a field's name can say.
# Never a type or format, which are read from the data, nor missing-value codes, which are not.
SUGGESTED_COLUMNS = frozenset({"description", "unit"})
# The longest suggestion kept, in characters: a definition or a unit, not a paragraph.
MAX_SUGGESTION = 200
# The longest suggestion kept for a README section, in characters: a few sentences.
MAX_SECTION_SUGGESTION = 600
# The key under which a writer is given the documents the researcher attached, for suggestions.
DOCUMENTS = "attached_documents"
# The most text of attached documents a writer is given, in characters: a few field notebooks.
MAX_DOCUMENTS = 60_000


class SuggestedAnswer(StrictReply):
    """One suggested answer, to the question with this identifier, or null for none."""

    question_id: str
    answer: str | None


class SuggestionReply(StrictReply):
    """What the model replies with when it suggests answers to a draft's questions."""

    suggestions: list[SuggestedAnswer]


@dataclass(frozen=True)
class Ask:
    """One question a writer may suggest an answer for: an unknown data dictionary cell (`file`,
    `field`, `column`) or a README section (`section`, with what it asks in `asks`)."""

    question_id: str
    file: str | None = None
    field: str | None = None
    column: str | None = None
    section: str | None = None
    asks: str | None = None


@dataclass(frozen=True)
class Suggestions:
    """What a writer suggested: an answer for some questions, by question identifier. Returned
    rather than kept on the writer, because one writer serves concurrent runs."""

    answers: Mapping[str, str] = field(default_factory=dict)
    # The suggestions the model made that were not used, and why, for the outcome's statement.
    dropped: tuple[str, ...] = ()
    # Why no suggestion could be used at all, if so: every batch's reply was unusable.
    unused: str | None = None
    model_id: str | None = None
    usage: Usage = field(default_factory=Usage)
    calls: ModelCallLog | None = None
    # How many questions got no suggestion because their batch's reply was cut off or not in the
    # form asked for, while other questions got one; and why, in plain words (`replies.py`).
    unanswered: int = 0
    unanswered_why: str | None = None
    # The attached documents the model was given, by name, and those cut short to fit.
    documents: tuple[str, ...] = ()
    cut: tuple[str, ...] = ()


@dataclass(frozen=True)
class _BatchReply:
    """What can be read from one batch's reply: the suggestions in it, an identifier for each item
    not in the form asked for (None if it gave none), and why the reply was not used whole."""

    reply: SuggestionReply
    unusable: tuple[str | None, ...] = ()
    why: str | None = None


# Why a model's reply gave no suggestions when it declined to answer.
DECLINED = "the model declined to suggest answers"


def suggest(
    model: Model, facts: Mapping[str, Any], asks: Sequence[Ask], ctx: RunContext
) -> Suggestions:
    """Suggestions for `asks`, asked in batches (`replies.batches`) so that no reply runs past
    what the model may write; a batch whose reply is unusable costs only its own questions."""
    asks = [a for a in asks if _suggestable(a)]
    if not asks:
        return Suggestions()
    if len({a.section is None for a in asks}) > 1:
        raise ValueError("a README's and a data dictionary's questions are asked apart")
    system = SUGGEST_README_PROMPT if asks[0].section is not None else SUGGEST_PROMPT
    calls: ModelCallLog | None = None
    answers: dict[str, str] = {}
    dropped: list[str] = []
    usages: list[Usage] = []
    missed: list[tuple[int, str]] = []  # questions a batch's reply left out, and why
    model_id = model.model_id
    asked = batches(asks)
    for batch in asked:
        got, batch_reply = _suggest_batch(model, system, facts, batch, ctx, calls)
        calls, model_id = got.calls, got.model_id
        usages.append(got.usage)
        checked = check_suggestions(batch_reply.reply, facts, batch)
        answers |= {q: a for q, a in checked.answers.items() if q not in answers}
        dropped += checked.dropped
        dropped += [f"{q or 'a suggestion'}: {ITEM_NOT_IN_FORM}" for q in batch_reply.unusable]
        if batch_reply.why is not None:
            # An item not in the form asked for is counted among the dropped, not here.
            replied = {s.question_id for s in batch_reply.reply.suggestions}
            left = sum(a.question_id not in replied for a in batch) - len(batch_reply.unusable)
            missed.append((max(left, 0), batch_reply.why))
    why = missed[0][1] if missed else None
    # Nothing at all came of any batch: no suggestion could be used, and the statement says why.
    unused = why if len(missed) == len(asked) and not answers and not dropped else None
    given = facts.get(DOCUMENTS, ())
    return Suggestions(
        answers,
        tuple(dropped),
        unused,
        model_id,
        _total(usages),
        calls,
        0 if unused else sum(n for n, _ in missed),
        None if unused else why,
        tuple(d["name"] for d in given),
        tuple(d["name"] for d in given if d.get("cut")),
    )


def _suggest_batch(
    model: Model,
    system: str,
    facts: Mapping[str, Any],
    batch: Sequence[Ask],
    ctx: RunContext,
    calls: ModelCallLog | None,
) -> tuple[ModelReply[SuggestionReply], _BatchReply]:
    """One call for one batch of questions, and what can be read from its reply."""
    messages = [{"role": "user", "content": suggestion_prompt(facts, batch)}]
    try:
        got = call(
            model,
            ctx,
            system=system,
            messages=messages,
            schema=SuggestionReply,
            options=CallOptions(calls=calls),
        )
    except ModelOutputError as error:
        # An endpoint that does not constrain its output may fence the JSON, stray from the
        # schema in one item, or be cut off at its length limit: what is whole is kept.
        got = error.reply
        text = unfenced(got.text)
        try:
            return got, _BatchReply(SuggestionReply.model_validate_json(text))
        except ValidationError:
            kept = salvage(text, "suggestions", SuggestedAnswer, "question_id")
        why = CUT_SHORT if got.stop == "max_tokens" else NOT_IN_FORM
        return got, _BatchReply(SuggestionReply(suggestions=list(kept.items)), kept.unusable, why)
    if got.parsed is None:
        return got, _BatchReply(SuggestionReply(suggestions=[]), (), DECLINED)
    return got, _BatchReply(got.parsed)


def _total(usages: Sequence[Usage]) -> Usage:
    """The tokens of several calls: unknown only if no call reports them."""
    inputs = [u.input_tokens for u in usages if u.input_tokens is not None]
    outputs = [u.output_tokens for u in usages if u.output_tokens is not None]
    return Usage(sum(inputs) if inputs else None, sum(outputs) if outputs else None)


def _suggestable(ask: Ask) -> bool:
    """Whether a writer may suggest an answer to `ask`: a README section, or a data dictionary's
    definition or unit."""
    return ask.section is not None or ask.column in SUGGESTED_COLUMNS


def suggestion_prompt(facts: Mapping[str, Any], asks: Sequence[Ask]) -> str:
    """The user message: the questions the model may suggest answers to, and the facts, as JSON."""
    questions = [
        {"question_id": a.question_id, "section": a.section, "asks": a.asks}
        if a.section is not None
        else {"question_id": a.question_id, "file": a.file, "field": a.field, "column": a.column}
        for a in asks
    ]
    return (
        "Questions you may suggest an answer to:\n"
        + json.dumps(questions, ensure_ascii=False, indent=1)
        + "\n\nFacts:\n"
        + json.dumps(facts, ensure_ascii=False, indent=1, sort_keys=True)
    )


# What a suggestion may not contain: Markdown structure, HTML, a line break or the placeholder.
_NOT_A_SUGGESTION = re.compile(r"^\s*(#|\||[-*+]\s|\d+[.)]\s|>)|<|\n|Still needed:", re.MULTILINE)


def check_suggestions(
    reply: SuggestionReply, facts: Mapping[str, Any], asks: Sequence[Ask]
) -> Suggestions:
    """The suggestions of a model's reply that may be offered, and why any others were not."""
    known = json.dumps(facts, ensure_ascii=False, sort_keys=True)
    asked = {a.question_id: a for a in asks if _suggestable(a)}
    kept: dict[str, str] = {}
    dropped: list[str] = []
    for suggested in reply.suggestions:
        question_id, answer = suggested.question_id, suggested.answer
        if answer is None or not answer.strip():
            continue
        why = (
            "suggested twice"
            if question_id in kept
            else _unsuggestable(question_id, answer, asked, facts, known)
        )
        if why:
            dropped.append(f"{question_id}: {why}")
        else:
            kept[question_id] = " ".join(answer.split())
    return Suggestions(kept, tuple(dropped))


def _unsuggestable(
    question_id: str,
    answer: str,
    asked: Mapping[str, Ask],
    facts: Mapping[str, Any],
    known: str,
) -> str | None:
    """Why a suggestion cannot be offered, or None if it can."""
    ask = asked.get(question_id)
    if ask is None:
        return "not a question it was asked to suggest an answer to"
    if ask.section is not None:
        # A README section's suggestion is prose, checked as the prose is: every number, link,
        # identifier and code-formatted name it gives must be in the facts.
        return unchecked(answer, facts, known, MAX_SECTION_SUGGESTION)
    if len(answer) > MAX_SUGGESTION:
        return "too long"
    if _NOT_A_SUGGESTION.search(answer.strip()):
        return "not plain text"
    # A link, a DOI, an email address or an ORCID iD the facts do not give is invented. Numbers
    # and code-formatted names are allowed: a unit may be "metres per second squared" or "°C".
    for pattern in NAMED[:4]:
        for match in pattern.finditer(answer):
            named = match.group(match.lastindex or 0)
            if named not in known:
                return f"names {named!r}, which the facts do not give"
    return None


def with_documents(facts: Mapping[str, Any], asked: DraftRequest) -> dict[str, Any]:
    """`facts` with the documents the researcher attached, the latest first, within
    `MAX_DOCUMENTS` characters; a document cut short, or left out for room, is marked `cut`."""
    given: list[dict[str, Any]] = []
    room = MAX_DOCUMENTS
    for document in reversed(asked.project_documents):
        text = document.documentation_text[:room]
        room -= len(text)
        entry: dict[str, Any] = {"name": document.documentation_name, "text": text}
        if len(text) < len(document.documentation_text):
            entry["cut"] = True
        given.append(entry)
    return {**facts, DOCUMENTS: given} if given else dict(facts)


def how_suggested(suggested: Suggestions, title: str) -> str:
    """What the statement says about the suggested answers."""
    if suggested.model_id is None:
        return "No model is configured, so it suggests no answers."
    if suggested.unused:
        return (
            f"It suggests no answers, because {suggested.unused} ({suggested.model_id}). "
            "Answer the questions yourself, or draft it again to ask for suggestions again."
        )
    n = len(suggested.answers)
    said = (
        f"A model ({suggested.model_id}) suggested an answer to "
        f"{count(n, 'question')}, offered beside the question and not written into the "
        f"{title.lower()}: a suggestion becomes yours only when you save it, or a "
        "correction of it, as your answer"
        if n
        else f"A model ({suggested.model_id}) was asked to suggest answers but offered none"
    )
    if suggested.dropped:
        said += (
            f"; {count(len(suggested.dropped), 'suggestion')} it made "
            f"{'was' if len(suggested.dropped) == 1 else 'were'} not offered ("
            + "; ".join(suggested.dropped)
            + ")"
        )
    if suggested.unanswered:
        n = suggested.unanswered
        said += f"; {count(n, 'question')} got no suggestion, because {suggested.unanswered_why}"
    said += "."
    if suggested.documents:
        said += f" It was given {count(len(suggested.documents), 'document')} you attached"
        cut = f" ({', '.join(suggested.cut)} only in part, for room)" if suggested.cut else ""
        said += f"{cut}."
    return said
