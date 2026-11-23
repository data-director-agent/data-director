"""Suggesters: values a model offers beside the record's questions (docs/specs/drafting.md,
invariant 7).

A suggester is given the facts the record is drafted from and the questions it may suggest an
answer to, and returns a short suggestion for some of them. A suggestion is offered with its
question and never placed in the record: the null stays null until the researcher records an
answer. The record, its gaps and its questions are drafted by rule in `agent.py`, so a suggester
cannot fill a value, close a gap or change an answer. It is never given the researcher's answers,
an earlier version, or the data.

`ModelSuggester` is the default (`DD_METADATA_SUGGESTER` unset or `model`, `factory.py`);
`TemplateSuggester` (`DD_METADATA_SUGGESTER=template`) suggests nothing and needs no key.
`ModelSuggester` calls whichever model the agent's settings name through the SDK's model seam
(`dd_sdk.model`, `dd_sdk.model_provider`), so this package imports no model provider's SDK
(docs/specs/dependencies.md). The model replies against a schema (`SuggestionReply`); a reply that
does not match is not used. Each suggestion is checked before it is offered (`check_suggestions`):
it must answer a question the model was asked, once, in one short line of plain text that names no
link, DOI, email address or ORCID iD the facts do not give. A question that offers a closed set of
choices, the fields of a named classification (`categories.py`), is answered with one of their
codes, or not at all."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from dd_sdk.agent import RunContext
from dd_sdk.model import Model, ModelOutputError, Usage, call
from dd_sdk.prompts import ModelCallLog

DEFAULT_MODEL = "claude-sonnet-5-5"
# What the model is told it may and may not suggest: a Markdown file beside this module.
SUGGEST_PROMPT = Path(__file__).with_name("suggest_prompt.md").read_text(encoding="utf-8").strip()
# The longest suggestion kept, in characters: a title, a keyword or a short abstract.
MAX_SUGGESTION = 1000


class _Reply(BaseModel):
    # A reply with a key the schema does not name does not match it.
    model_config = ConfigDict(extra="forbid")


class SuggestedAnswer(_Reply):
    """One suggested value, for the question with this identifier, or null for none."""

    question_id: str
    answer: str | None


class SuggestionReply(_Reply):
    """What the model replies with: a suggested value for some of the questions it was offered."""

    suggestions: list[SuggestedAnswer]


@dataclass(frozen=True)
class Ask:
    """One question a suggester may suggest an answer to: the value at `path` in the record, of
    the DataCite property `prop`, asked as `prompt`, with the qualifiers beside it, and, for an
    entry from a named classification, the (code, label) pairs it is answered from."""

    question_id: str
    path: str
    prop: str
    prompt: str
    qualifier: Mapping[str, Any] = field(default_factory=dict)
    choices: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Suggestions:
    """What a suggester suggested, by question identifier. Returned rather than kept on the
    suggester, because one suggester serves concurrent runs."""

    answers: Mapping[str, str] = field(default_factory=dict)
    # The suggestions the model made that were not offered, and why, for the outcome's statement.
    dropped: tuple[str, ...] = ()
    # Why the model's reply as a whole was not used, if so.
    unused: str | None = None
    model_id: str | None = None
    usage: Usage = field(default_factory=Usage)
    calls: ModelCallLog | None = None


class Suggester(Protocol):
    model_id: str | None

    def suggest(
        self, facts: Mapping[str, Any], asks: Sequence[Ask], ctx: RunContext
    ) -> Suggestions: ...


class TemplateSuggester:
    """Suggests nothing: the questions are the template's."""

    model_id: str | None = None

    def suggest(
        self, facts: Mapping[str, Any], asks: Sequence[Ask], ctx: RunContext
    ) -> Suggestions:
        return Suggestions()


class ModelSuggester:
    """Suggests with the model the agent's settings name (`dd_sdk.model_provider`). Emits one
    `chat` span per call, carrying the model id and the token counts (`dd_sdk.model.call`)."""

    def __init__(self, model: Model) -> None:
        self.model = model
        self.model_id: str | None = model.model_id

    def suggest(
        self, facts: Mapping[str, Any], asks: Sequence[Ask], ctx: RunContext
    ) -> Suggestions:
        if not asks:
            return Suggestions()
        messages = [{"role": "user", "content": suggestion_prompt(facts, asks)}]
        try:
            reply = call(
                self.model, ctx, system=SUGGEST_PROMPT, messages=messages, schema=SuggestionReply
            )
            parsed: SuggestionReply | None = reply.parsed
            got: Any = reply
        except ModelOutputError as error:
            # An endpoint that does not constrain its output may fence the JSON; a fenced reply
            # that matches is used, anything else is not.
            got = error.reply
            try:
                parsed = SuggestionReply.model_validate_json(_unfenced(got.text))
            except ValidationError:
                return Suggestions(
                    unused="the model's reply did not match its schema",
                    model_id=got.model_id,
                    usage=got.usage,
                    calls=got.calls,
                )
        if parsed is None:
            return Suggestions(
                unused="the model declined to suggest values",
                model_id=got.model_id,
                usage=got.usage,
                calls=got.calls,
            )
        checked = check_suggestions(parsed, facts, asks)
        return Suggestions(
            checked.answers, checked.dropped, None, got.model_id, got.usage, got.calls
        )


def suggestion_prompt(facts: Mapping[str, Any], asks: Sequence[Ask]) -> str:
    """The user message: the questions the model may suggest a value for, and the facts, as JSON."""
    questions = [
        {
            "question_id": a.question_id,
            "property": a.prop,
            "asks": a.prompt,
            **({"qualifier": dict(a.qualifier)} if a.qualifier else {}),
            **(
                {"choose_from": [{"code": c, "label": label} for c, label in a.choices]}
                if a.choices
                else {}
            ),
        }
        for a in asks
    ]
    return (
        "Questions you may suggest a value for:\n"
        + json.dumps(questions, ensure_ascii=False, indent=1)
        + "\n\nFacts:\n"
        + json.dumps(facts, ensure_ascii=False, indent=1, sort_keys=True)
    )


# What a suggestion may not contain: Markdown structure, HTML or a line break.
_NOT_A_SUGGESTION = re.compile(r"^\s*(#|\||[-*+]\s|\d+[.)]\s|>)|<|\n", re.MULTILINE)
# What a suggestion may name only if the facts give it.
_NAMED = (
    re.compile(r"https?://\S+?(?=[.,;:)]?(?:\s|$))"),  # a link
    re.compile(r"\b10\.\d{4,9}/\S+?(?=[.,;:)]?(?:\s|$))"),  # a DOI
    re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),  # an email address
    re.compile(r"\b\d{4}-\d{4}-\d{4}-\d{3}[\dX]\b"),  # an ORCID iD
)


def check_suggestions(
    reply: SuggestionReply, facts: Mapping[str, Any], asks: Sequence[Ask]
) -> Suggestions:
    """The suggestions of a model's reply that may be offered, and why any others were not."""
    known = json.dumps(facts, ensure_ascii=False, sort_keys=True)
    by_id = {a.question_id: a for a in asks}
    kept: dict[str, str] = {}
    dropped: list[str] = []
    for suggested in reply.suggestions:
        question, answer = suggested.question_id, suggested.answer
        if answer is None or not answer.strip():
            continue
        choices = by_id[question].choices if question in by_id else ()
        chosen = _chosen(answer, choices) if choices else None
        if question in kept:
            why: str | None = "suggested twice"
        elif choices:
            why = None if chosen else "not one of the codes it was offered"
        else:
            why = _unsuggestable(question, answer, set(by_id), known)
        if why:
            dropped.append(f"{question}: {why}")
        else:
            kept[question] = chosen or " ".join(answer.split())
    if any(a.choices for a in asks):
        repeated = _repeated(kept, by_id)
        dropped += [f"{q}: suggested for another entry too" for q in repeated]
        kept = {q: a for q, a in kept.items() if q not in repeated}
    return Suggestions(kept, tuple(dropped))


def _chosen(answer: str, choices: tuple[tuple[str, str], ...]) -> str | None:
    """The code of the choice `answer` names, by its code or its label; None if none."""
    given = " ".join(answer.split()).casefold()
    for code, label in choices:
        if given in {code.casefold(), label.casefold()}:
            return code
    return None


def _repeated(kept: Mapping[str, str], by_id: Mapping[str, Ask]) -> set[str]:
    """The later questions given a code an earlier entry of the same vocabulary was given."""
    seen: set[tuple[str, str]] = set()
    repeated: set[str] = set()
    for question, code in kept.items():
        ask = by_id[question]
        if not ask.choices:
            continue
        key = (json.dumps(dict(ask.qualifier), sort_keys=True), code)
        if key in seen:
            repeated.add(question)
        seen.add(key)
    return repeated


def _unsuggestable(question: str, answer: str, asked: set[str], known: str) -> str | None:
    """Why a suggestion cannot be offered, or None if it can."""
    if question not in asked:
        return "not a question it was asked to suggest a value for"
    if len(answer) > MAX_SUGGESTION:
        return "too long"
    if _NOT_A_SUGGESTION.search(answer.strip()):
        return "not plain text"
    for pattern in _NAMED:
        for match in pattern.finditer(answer):
            if match.group(0) not in known:
                return f"names {match.group(0)!r}, which the facts do not give"
    return None


def _unfenced(text: str) -> str:
    """The reply without a Markdown code fence around it, which models add unasked."""
    stripped = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL)
    return fenced.group(1) if fenced else stripped
