"""Writers: the README's prose, drafted from the project's facts (docs/specs/drafting.md).

A writer is given the facts the README is drafted from and the sections it may write about, and
returns a short paragraph for some of them and an overview of the dataset. Once the researcher has
answered a section, the writer is also given their answers (`researcher_answers`, by heading), the
project's decisions and the documents they attached, and may write that section's paragraph from
them; the paragraph then takes the place of the answer as given. It writes nothing else: the gaps,
their questions, the tables and the values placed from the metadata record are drafted by rule in
`agent.py`, so a writer cannot close a gap or change a value. It is never given an earlier
version.

`ModelWriter` is the default (`DD_DOCUMENTATION_WRITER` unset or `model`, `factory.py`) and calls
whichever model the agent's settings name through the SDK's model seam (`dd_sdk.model`,
`dd_sdk.model_provider`), so this package imports no model provider's SDK
(docs/specs/dependencies.md). It is sent the inventory's structure, the metadata record's values
and the repository's name and licences, never the data. The model replies against a schema
(`ProseReply`, `SuggestionReply`), which the provider constrains it to; a reply that does not match
is not used. `TemplateWriter`, selected with `DD_DOCUMENTATION_WRITER=template`, writes no prose:
the draft is the template's.

What the model writes is checked before it is used (`check`). A paragraph is dropped, and the
section drafted as the template drafts it, if it is not plain prose, or if it names a number, a
link, an email address, an identifier or a code-formatted name that the facts do not contain.

A writer may also suggest answers to a draft's questions (`suggest`): for a data dictionary's
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
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from dd_sdk.agent import RunContext
from dd_sdk.contract.models import DraftRequest
from dd_sdk.model import Model, ModelOutputError, call
from dd_sdk.model import Usage as Usage
from dd_sdk.prompts import ModelCallLog

DEFAULT_MODEL = "claude-sonnet-5-5"
# What the model is told it may and may not write; the prose is a Markdown file beside this module.
SYSTEM_PROMPT = Path(__file__).with_name("system_prompt.md").read_text(encoding="utf-8").strip()
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
# The key under which the overview, which goes under the README's title, is written.
OVERVIEW = "overview"
# The longest paragraph kept, in characters: a README's prose introduces its facts, briefly.
MAX_PARAGRAPH = 1200
# The key under which a writer is given the documents the researcher attached, for suggestions.
DOCUMENTS = "attached_documents"
# The most text of attached documents a writer is given, in characters: a few field notebooks.
MAX_DOCUMENTS = 60_000


class _Reply(BaseModel):
    # A reply with a key the schema does not name does not match it.
    model_config = ConfigDict(extra="forbid")


class SectionParagraph(_Reply):
    """One paragraph of prose, for the section with this heading, or null for none."""

    section: str
    paragraph: str | None


class ProseReply(_Reply):
    """What the model replies with when it writes the README's prose: the overview that goes under
    the title, and a paragraph for some of the sections it was offered. Every field is required
    and may be null, as a provider's strict schema needs."""

    overview: str | None
    sections: list[SectionParagraph]


class SuggestedAnswer(_Reply):
    """One suggested answer, to the question with this identifier, or null for none."""

    question_id: str
    answer: str | None


class SuggestionReply(_Reply):
    """What the model replies with when it suggests answers to a draft's questions."""

    suggestions: list[SuggestedAnswer]


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
    # Why the model's reply as a whole was not used, if so.
    unused: str | None = None
    model_id: str | None = None
    usage: Usage = field(default_factory=Usage)
    calls: ModelCallLog | None = None
    # The attached documents the model was given, by name, and those cut short to fit.
    documents: tuple[str, ...] = ()
    cut: tuple[str, ...] = ()


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


class ModelWriter:
    """Writes the prose with the model the agent's settings name (`dd_sdk.model_provider`), or a
    `dd_sdk.testing.FakeModel` in tests. Emits one `chat` span per call, carrying the model id and
    the token counts (`dd_sdk.model.call`)."""

    def __init__(self, model: Model) -> None:
        self.model = model
        self.model_id: str | None = model.model_id

    def write(self, facts: Mapping[str, Any], sections: Sequence[str], ctx: RunContext) -> Prose:
        if not sections:
            return Prose()
        reply, unused, model_id, usage, calls = self._call(
            SYSTEM_PROMPT, prompt(facts, sections), ProseReply, ctx
        )
        if reply is None:
            unused = "the model declined to write it" if unused is None else unused
            return Prose(unused=unused, model_id=model_id, usage=usage, calls=calls)
        prose = check(reply, facts, sections)
        return Prose(prose.overview, prose.sections, prose.dropped, None, model_id, usage, calls)

    def suggest(
        self, facts: Mapping[str, Any], asks: Sequence[Ask], ctx: RunContext
    ) -> Suggestions:
        asks = [a for a in asks if _suggestable(a)]
        if not asks:
            return Suggestions()
        if len({a.section is None for a in asks}) > 1:
            raise ValueError("a README's and a data dictionary's questions are asked apart")
        readme = asks[0].section is not None
        reply, unused, model_id, usage, calls = self._call(
            SUGGEST_README_PROMPT if readme else SUGGEST_PROMPT,
            suggestion_prompt(facts, asks),
            SuggestionReply,
            ctx,
        )
        if reply is None:
            unused = "the model declined to suggest answers" if unused is None else unused
            return Suggestions(unused=unused, model_id=model_id, usage=usage, calls=calls)
        got = check_suggestions(reply, facts, asks)
        given = facts.get(DOCUMENTS, ())
        return Suggestions(
            got.answers,
            got.dropped,
            None,
            model_id,
            usage,
            calls,
            tuple(d["name"] for d in given),
            tuple(d["name"] for d in given if d.get("cut")),
        )

    def _call[T: BaseModel](
        self, system: str, content: str, schema: type[T], ctx: RunContext
    ) -> tuple[T | None, str | None, str, Usage, ModelCallLog]:
        """One model call, its reply constrained to `schema`: the reply parsed, or None with why
        not (None if the model declined), the model that answered, its token counts and the
        record of what was sent."""
        messages = [{"role": "user", "content": content}]
        try:
            reply = call(self.model, ctx, system=system, messages=messages, schema=schema)
        except ModelOutputError as error:
            # An endpoint that does not constrain its output may fence the JSON, or stray from
            # the schema; a fenced reply that matches is used, anything else is not.
            got = error.reply
            try:
                parsed = schema.model_validate_json(_unfenced(got.text))
            except ValidationError:
                return None, "the model's reply did not match its schema", *_of(got)
            return parsed, None, *_of(got)
        return reply.parsed, None, *_of(reply)


def _of(reply: Any) -> tuple[str, Usage, ModelCallLog]:
    return reply.model_id, reply.usage, reply.calls


def _suggestable(ask: Ask) -> bool:
    """Whether a writer may suggest an answer to `ask`: a README section, or a data dictionary's
    definition or unit."""
    return ask.section is not None or ask.column in SUGGESTED_COLUMNS


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
_NOT_PROSE = re.compile(r"^\s*(#|\||[-*+]\s|\d+[.)]\s|>)|<|Still needed:", re.MULTILINE)
# What a paragraph may name only if the facts contain it, as written.
_NAMED = (
    re.compile(r"https?://\S+?(?=[.,;:)]?(?:\s|$))"),  # a link
    re.compile(r"\b10\.\d{4,9}/\S+?(?=[.,;:)]?(?:\s|$))"),  # a DOI
    re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),  # an email address
    re.compile(r"\b\d{4}-\d{4}-\d{4}-\d{3}[\dX]\b"),  # an ORCID iD
    re.compile(r"`([^`]+)`"),  # a code-formatted name: a file, a field, a licence
    re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*"),  # a number: a count, a size, a year, a date's parts
)


def check(reply: ProseReply, facts: Mapping[str, Any], sections: Sequence[str]) -> Prose:
    """The paragraphs of a model's reply that may be used, and why any others were not."""
    known = json.dumps(facts, ensure_ascii=False, sort_keys=True)
    offered = {OVERVIEW, *sections}
    kept: dict[str, str] = {}
    dropped: list[str] = []
    written = [(OVERVIEW, reply.overview)] + [(p.section, p.paragraph) for p in reply.sections]
    for heading, paragraph in written:
        if paragraph is None or not paragraph.strip():
            continue
        why = (
            "written twice"
            if heading in kept
            else _unusable(heading, paragraph, offered, known, MAX_PARAGRAPH)
        )
        if why:
            dropped.append(f"{heading}: {why}")
        else:
            kept[heading] = " ".join(paragraph.split())
    overview = kept.pop(OVERVIEW, None)
    return Prose(overview, kept, tuple(dropped))


def _unusable(
    heading: str, paragraph: str, offered: set[str], known: str, longest: int
) -> str | None:
    """Why a paragraph cannot be used, or None if it can."""
    if heading not in offered:
        return "not a section it was asked to write"
    return _unchecked(paragraph, known, longest)


def _unchecked(paragraph: str, known: str, longest: int) -> str | None:
    """Why a paragraph of prose fails the checks, or None if it passes them."""
    if len(paragraph) > longest:
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
            else _unsuggestable(question_id, answer, asked, known)
        )
        if why:
            dropped.append(f"{question_id}: {why}")
        else:
            kept[question_id] = " ".join(answer.split())
    return Suggestions(kept, tuple(dropped))


def _unsuggestable(
    question_id: str, answer: str, asked: Mapping[str, Ask], known: str
) -> str | None:
    """Why a suggestion cannot be offered, or None if it can."""
    ask = asked.get(question_id)
    if ask is None:
        return "not a question it was asked to suggest an answer to"
    if ask.section is not None:
        # A README section's suggestion is prose, checked as the prose is: every number, link,
        # identifier and code-formatted name it gives must be in the facts.
        return _unchecked(answer, known, MAX_SECTION_SUGGESTION)
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
        return f"It suggests no answers, because {suggested.unused} ({suggested.model_id})."
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
    said += "."
    if suggested.documents:
        said += f" It was given {count(len(suggested.documents), 'document')} you attached"
        cut = f" ({', '.join(suggested.cut)} only in part, for room)" if suggested.cut else ""
        said += f"{cut}."
    return said


def count(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def _unfenced(text: str) -> str:
    """The reply without a Markdown code fence around it, which models add unasked."""
    stripped = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL)
    return fenced.group(1) if fenced else stripped
