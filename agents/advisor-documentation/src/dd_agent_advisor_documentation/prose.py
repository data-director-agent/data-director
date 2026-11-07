"""Writers: the README's prose, drafted from the project's facts (docs/specs/drafting.md).

A writer is given the facts the README is drafted from and the sections it may write about, and
returns a short paragraph for some of them and an overview of the dataset. It writes nothing else:
the gaps, their questions, the tables and the values placed from the metadata record are drafted
by rule in `agent.py`, so a writer cannot close a gap, change a value or rephrase an answer. It is
never given the researcher's answers or an earlier version.

`TemplateWriter` is the default and writes no prose: the draft is the template's. `AnthropicWriter`
is selected with `DD_DOCUMENTATION_WRITER=anthropic` (`factory.py`) and is the package's only
importer of the `anthropic` SDK (docs/specs/dependencies.md). It is sent the inventory's
structure, the metadata record's values and the repository's name and licences, never the data.

What the model writes is checked before it is used (`check`). A paragraph is dropped, and the
section drafted as the template drafts it, if it is not plain prose, or if it names a number, a
link, an email address, an identifier or a code-formatted name that the facts do not contain.

A writer may also suggest answers to a data dictionary's questions (`suggest`): for an unknown
definition or unit, what the field's name and the dataset's facts make likely, such as that
`age_yrs` is the participant's age in years. A suggestion is offered with the question and never
placed in a cell (docs/specs/drafting.md, invariant 7). It is given the same facts as the prose and
checked as strictly (`check_suggestions`); `TemplateWriter` suggests nothing.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from dd_sdk.agent import RunContext
from dd_sdk.contract.models import now
from dd_sdk.prompts import ModelCallLog
from dd_sdk.tracing import chat_span, record_tokens

if TYPE_CHECKING:
    import anthropic

DEFAULT_MODEL = "claude-sonnet-5-5"
# Who serves the model, as the agent's card names it (factory.py).
PROVIDER = "anthropic"
# What the model is told it may and may not write; the prose is a Markdown file beside this module.
SYSTEM_PROMPT = Path(__file__).with_name("system_prompt.md").read_text(encoding="utf-8").strip()
# What the model is told when it suggests answers to a data dictionary's questions.
SUGGEST_PROMPT = Path(__file__).with_name("suggest_prompt.md").read_text(encoding="utf-8").strip()
# The data dictionary columns a model may suggest an answer for: what a field's name can say.
# Never a type or format, which are read from the data, nor missing-value codes, which are not.
SUGGESTED_COLUMNS = frozenset({"description", "unit"})
# The longest suggestion kept, in characters: a definition or a unit, not a paragraph.
MAX_SUGGESTION = 200
# The key under which the overview, which goes under the README's title, is written.
OVERVIEW = "overview"
# The longest paragraph kept, in characters: a README's prose introduces its facts, briefly.
MAX_PARAGRAPH = 1200


@dataclass
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class Prose:
    """What a writer wrote: an overview, if any, and a paragraph for some sections, by heading.
    Returned rather than kept on the writer, because one writer serves concurrent runs."""

    overview: str | None = None
    sections: Mapping[str, str] = field(default_factory=dict)
    # The paragraphs the model wrote that were not used, and why, for the outcome's statement.
    dropped: tuple[str, ...] = ()
    # Why the model's draft as a whole was not used (a refusal, a reply that is not JSON), if so.
    unused: str | None = None
    model_id: str | None = None
    usage: Usage = field(default_factory=Usage)
    # The model calls made and the prompts sent (dd_sdk.prompts); None if no model was called.
    calls: ModelCallLog | None = None

    @property
    def written(self) -> int:
        return (self.overview is not None) + len(self.sections)


@dataclass(frozen=True)
class Ask:
    """One unknown data dictionary cell a writer may suggest an answer for."""

    question_id: str
    file: str
    field: str
    column: str


@dataclass(frozen=True)
class Suggestions:
    """What a writer suggested: an answer for some questions, by question identifier. Returned
    rather than kept on the writer, because one writer serves concurrent runs."""

    answers: Mapping[str, str] = field(default_factory=dict)
    # The suggestions the model made that were not used, and why, for the outcome's statement.
    dropped: tuple[str, ...] = ()
    # Why the model's reply as a whole was not used, if so.
    unused: str | None = None
    model_id: str | None = None
    usage: Usage = field(default_factory=Usage)
    calls: ModelCallLog | None = None


class Writer(Protocol):
    model_id: str | None

    def write(
        self, facts: Mapping[str, Any], sections: Sequence[str], ctx: RunContext
    ) -> Prose: ...

    def suggest(
        self, facts: Mapping[str, Any], asks: Sequence[Ask], ctx: RunContext
    ) -> Suggestions: ...


class TemplateWriter:
    """Writes no prose and suggests nothing: the draft is the template's."""

    model_id: str | None = None

    def write(self, facts: Mapping[str, Any], sections: Sequence[str], ctx: RunContext) -> Prose:
        return Prose()

    def suggest(
        self, facts: Mapping[str, Any], asks: Sequence[Ask], ctx: RunContext
    ) -> Suggestions:
        return Suggestions()


class AnthropicWriter:
    """Writes the prose with Claude. Emits one `chat` span carrying model id and token counts."""

    def __init__(
        self,
        client: anthropic.Anthropic | None = None,
        model_id: str = DEFAULT_MODEL,
        api_key: str | None = None,
    ) -> None:
        """Give a `client` (tests) or an `api_key` (`dd_sdk.credentials.api_key`). The key is
        always passed explicitly, so the SDK's own credential chain is never used
        (docs/specs/policy-and-identity.md)."""
        if client is None:
            if not api_key:
                raise ValueError("AnthropicWriter needs a client or an api_key")
            import anthropic as _anthropic

            client = _anthropic.Anthropic(api_key=api_key)
        self._client = client
        self.model_id: str | None = model_id

    def write(self, facts: Mapping[str, Any], sections: Sequence[str], ctx: RunContext) -> Prose:
        if not sections:
            return Prose()
        text, refused, model_id, usage, calls = self._call(
            SYSTEM_PROMPT, prompt(facts, sections), ctx
        )
        prose = (
            Prose(unused="the model declined to write it")
            if refused
            else check(text, facts, sections)
        )
        return Prose(
            prose.overview,
            prose.sections,
            prose.dropped,
            prose.unused,
            model_id,
            usage,
            calls,
        )

    def suggest(
        self, facts: Mapping[str, Any], asks: Sequence[Ask], ctx: RunContext
    ) -> Suggestions:
        asks = [a for a in asks if a.column in SUGGESTED_COLUMNS]
        if not asks:
            return Suggestions()
        text, refused, model_id, usage, calls = self._call(
            SUGGEST_PROMPT, suggestion_prompt(facts, asks), ctx
        )
        got = (
            Suggestions(unused="the model declined to suggest answers")
            if refused
            else check_suggestions(text, facts, asks)
        )
        return Suggestions(got.answers, got.dropped, got.unused, model_id, usage, calls)

    def _call(
        self, system: str, content: str, ctx: RunContext
    ) -> tuple[str, bool, str, Usage, ModelCallLog]:
        """One model call: its text, whether it was refused, the model that answered, its token
        counts and the record of what was sent."""
        assert self.model_id is not None
        # What is sent, kept by digest with the run (docs/specs/disclosure.md).
        sent = {"system": system, "messages": [{"role": "user", "content": content}]}
        calls = ModelCallLog(PROVIDER)
        with chat_span(ctx.tracer, self.model_id) as span:
            called_at = now()
            response = self._client.messages.create(
                model=self.model_id,
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": content}],
            )
            usage = Usage(response.usage.input_tokens, response.usage.output_tokens)
            record_tokens(span, usage.input_tokens, usage.output_tokens)
        # The model the response names, which may be more exact than the one asked for.
        model_id = getattr(response, "model", None) or self.model_id
        calls.record(
            sent,
            model_id,
            called_at=called_at,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        return text, response.stop_reason == "refusal", model_id, usage, calls


def prompt(facts: Mapping[str, Any], sections: Sequence[str]) -> str:
    """The user message: the sections the model may write about, and the facts, as JSON."""
    return (
        "Sections you may write a paragraph for: "
        + json.dumps([OVERVIEW, *sections], ensure_ascii=False)
        + "\n\nFacts:\n"
        + json.dumps(facts, ensure_ascii=False, indent=1, sort_keys=True)
    )


# What a paragraph may not contain: Markdown structure, HTML (the gap markers among it), and the
# template's placeholder, any of which would let prose pass for something it is not.
_NOT_PROSE = re.compile(r"^\s*(#|\||[-*+]\s|\d+[.)]\s|>)|<|To be written by", re.MULTILINE)
# What a paragraph may name only if the facts contain it, as written.
_NAMED = (
    re.compile(r"https?://\S+?(?=[.,;:)]?(?:\s|$))"),  # a link
    re.compile(r"\b10\.\d{4,9}/\S+?(?=[.,;:)]?(?:\s|$))"),  # a DOI
    re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),  # an email address
    re.compile(r"\b\d{4}-\d{4}-\d{4}-\d{3}[\dX]\b"),  # an ORCID iD
    re.compile(r"`([^`]+)`"),  # a code-formatted name: a file, a field, a licence
    re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*"),  # a number: a count, a size, a year, a date's parts
)


def check(text: str, facts: Mapping[str, Any], sections: Sequence[str]) -> Prose:
    """The paragraphs of a model's reply that may be used, and why any others were not."""
    try:
        reply = json.loads(_unfenced(text))
    except json.JSONDecodeError:
        return Prose(unused="the model's reply was not JSON")
    if not isinstance(reply, dict):
        return Prose(unused="the model's reply was not a JSON object")
    known = json.dumps(facts, ensure_ascii=False, sort_keys=True)
    offered = {OVERVIEW, *sections}
    kept: dict[str, str] = {}
    dropped: list[str] = []
    for heading, paragraph in reply.items():
        if paragraph is None or (isinstance(paragraph, str) and not paragraph.strip()):
            continue
        why = _unusable(heading, paragraph, offered, known)
        if why:
            dropped.append(f"{heading}: {why}")
        else:
            kept[heading] = " ".join(str(paragraph).split())
    overview = kept.pop(OVERVIEW, None)
    return Prose(overview, kept, tuple(dropped))


def _unusable(heading: str, paragraph: Any, offered: set[str], known: str) -> str | None:
    """Why a paragraph cannot be used, or None if it can."""
    if heading not in offered:
        return "not a section it was asked to write"
    if not isinstance(paragraph, str):
        return "not text"
    if len(paragraph) > MAX_PARAGRAPH:
        return "too long"
    if _NOT_PROSE.search(paragraph):
        return "not plain prose"
    for pattern in _NAMED:
        for match in pattern.finditer(paragraph):
            named = match.group(match.lastindex or 0)
            if named not in known:
                return f"names {named!r}, which the facts do not give"
    return None


def suggestion_prompt(facts: Mapping[str, Any], asks: Sequence[Ask]) -> str:
    """The user message: the questions the model may suggest answers to, and the facts, as JSON."""
    questions = [
        {"question_id": a.question_id, "file": a.file, "field": a.field, "column": a.column}
        for a in asks
    ]
    return (
        "Questions you may suggest an answer to:\n"
        + json.dumps(questions, ensure_ascii=False, indent=1)
        + "\n\nFacts:\n"
        + json.dumps(facts, ensure_ascii=False, indent=1, sort_keys=True)
    )


# What a suggestion may not contain: Markdown structure, HTML, a line break or the placeholder.
_NOT_A_SUGGESTION = re.compile(
    r"^\s*(#|\||[-*+]\s|\d+[.)]\s|>)|<|\n|To be written by", re.MULTILINE
)


def check_suggestions(text: str, facts: Mapping[str, Any], asks: Sequence[Ask]) -> Suggestions:
    """The suggestions of a model's reply that may be offered, and why any others were not."""
    try:
        reply = json.loads(_unfenced(text))
    except json.JSONDecodeError:
        return Suggestions(unused="the model's reply was not JSON")
    if not isinstance(reply, dict):
        return Suggestions(unused="the model's reply was not a JSON object")
    known = json.dumps(facts, ensure_ascii=False, sort_keys=True)
    asked = {a.question_id: a for a in asks if a.column in SUGGESTED_COLUMNS}
    kept: dict[str, str] = {}
    dropped: list[str] = []
    for question_id, answer in reply.items():
        if answer is None or (isinstance(answer, str) and not answer.strip()):
            continue
        why = _unsuggestable(question_id, answer, asked, known)
        if why:
            dropped.append(f"{question_id}: {why}")
        else:
            kept[question_id] = " ".join(str(answer).split())
    return Suggestions(kept, tuple(dropped))


def _unsuggestable(
    question_id: str, answer: Any, asked: Mapping[str, Ask], known: str
) -> str | None:
    """Why a suggestion cannot be offered, or None if it can."""
    if question_id not in asked:
        return "not a question it was asked to suggest an answer to"
    if not isinstance(answer, str):
        return "not text"
    if len(answer) > MAX_SUGGESTION:
        return "too long"
    if _NOT_A_SUGGESTION.search(answer.strip()):
        return "not plain text"
    # A link, a DOI, an email address or an ORCID iD the facts do not give is invented. Numbers
    # and code-formatted names are allowed: a unit may be "metres per second squared" or "°C".
    for pattern in _NAMED[:4]:
        for match in pattern.finditer(answer):
            named = match.group(match.lastindex or 0)
            if named not in known:
                return f"names {named!r}, which the facts do not give"
    return None


def _unfenced(text: str) -> str:
    """The reply without a Markdown code fence around it, which models add unasked."""
    stripped = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL)
    return fenced.group(1) if fenced else stripped
