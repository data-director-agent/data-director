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
(`ProseReply`), which the provider constrains it to; a reply that does not match is not used.
`TemplateWriter`, selected with `DD_DOCUMENTATION_WRITER=template`, writes no prose: the draft is
the template's.

What the model writes is checked before it is used (`check`). A paragraph is dropped, and the
section drafted as the template drafts it, if it is not plain prose, or if it names a number, a
link, an email address, an identifier or a code-formatted name that the facts do not contain,
or a count of files, folders or tables that is not one the facts give (`counts.py`). The counts,
those at the top level and in each folder among them, are worked out by rule and given in the
facts, so the model need not add anything up.

A writer also suggests answers to a draft's questions (`suggest`, `suggestions.py`), and a
`ModelWriter` revises a README's prose as a person asked (`revise`, `revise.py`), the one time it
is given an earlier version: the version that person asked to change.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from dd_agent_advisor_documentation.checks import StrictReply, unchecked
from dd_agent_advisor_documentation.replies import unfenced
from dd_agent_advisor_documentation.revise import Revision, revise
from dd_agent_advisor_documentation.suggestions import Ask, Suggestions, suggest
from dd_sdk.agent import RunContext
from dd_sdk.model import Model, ModelOutputError, call
from dd_sdk.model import Usage as Usage
from dd_sdk.prompts import ModelCallLog

DEFAULT_MODEL = "claude-sonnet-5-5"
# What the model is told it may and may not write; the prose is a Markdown file beside this module.
SYSTEM_PROMPT = Path(__file__).with_name("system_prompt.md").read_text(encoding="utf-8").strip()
# The key under which the overview, which goes under the README's title, is written.
OVERVIEW = "overview"
# The longest paragraph kept, in characters: a README's prose introduces its facts, briefly.
MAX_PARAGRAPH = 1200


class SectionParagraph(StrictReply):
    """One paragraph of prose, for the section with this heading, or null for none."""

    section: str
    paragraph: str | None


class ProseReply(StrictReply):
    """What the model replies with when it writes the README's prose: the overview that goes under
    the title, and a paragraph for some of the sections it was offered. Every field is required
    and may be null, as a provider's strict schema needs."""

    overview: str | None
    sections: list[SectionParagraph]


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


class Writer(Protocol):
    model_id: str | None

    def write(
        self, facts: Mapping[str, Any], sections: Sequence[str], ctx: RunContext
    ) -> Prose: ...

    def suggest(
        self, facts: Mapping[str, Any], asks: Sequence[Ask], ctx: RunContext
    ) -> Suggestions: ...

    def revise(
        self,
        facts: Mapping[str, Any],
        current: str,
        instruction: str,
        given: Collection[str],
        ctx: RunContext,
    ) -> Revision | None: ...


class TemplateWriter:
    """Writes no prose and suggests nothing: the draft is the template's."""

    model_id: str | None = None

    def write(self, facts: Mapping[str, Any], sections: Sequence[str], ctx: RunContext) -> Prose:
        return Prose()

    def suggest(
        self, facts: Mapping[str, Any], asks: Sequence[Ask], ctx: RunContext
    ) -> Suggestions:
        return Suggestions()

    def revise(
        self,
        facts: Mapping[str, Any],
        current: str,
        instruction: str,
        given: Collection[str],
        ctx: RunContext,
    ) -> Revision | None:
        """None: a revision as a person asks needs a model (docs/specs/drafting.md)."""
        return None


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
        return suggest(self.model, facts, asks, ctx)

    def revise(
        self,
        facts: Mapping[str, Any],
        current: str,
        instruction: str,
        given: Collection[str],
        ctx: RunContext,
    ) -> Revision | None:
        """`current` revised as a person asked, its reply checked (`revise.py`)."""
        return revise(self._call, current, instruction, facts, given, ctx)

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
                parsed = schema.model_validate_json(unfenced(got.text))
            except ValidationError:
                return None, "the model's reply did not match its schema", *_of(got)
            return parsed, None, *_of(got)
        return reply.parsed, None, *_of(reply)


def _of(reply: Any) -> tuple[str, Usage, ModelCallLog]:
    return reply.model_id, reply.usage, reply.calls


def prompt(facts: Mapping[str, Any], sections: Sequence[str]) -> str:
    """The user message: the sections the model may write about, and the facts, as JSON."""
    return (
        "Sections you may write a paragraph for: "
        + json.dumps([OVERVIEW, *sections], ensure_ascii=False)
        + "\n\nFacts:\n"
        + json.dumps(facts, ensure_ascii=False, indent=1, sort_keys=True)
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
            else _unusable(heading, paragraph, offered, facts, known, MAX_PARAGRAPH)
        )
        if why:
            dropped.append(f"{heading}: {why}")
        else:
            kept[heading] = " ".join(paragraph.split())
    overview = kept.pop(OVERVIEW, None)
    return Prose(overview, kept, tuple(dropped))


def _unusable(
    heading: str,
    paragraph: str,
    offered: set[str],
    facts: Mapping[str, Any],
    known: str,
    longest: int,
) -> str | None:
    """Why a paragraph cannot be used, or None if it can."""
    if heading not in offered:
        return "not a section it was asked to write"
    return unchecked(paragraph, facts, known, longest)
