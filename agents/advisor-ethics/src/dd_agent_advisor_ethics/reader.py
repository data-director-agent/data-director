"""Readers: what a dataset's field names suggest, beyond the keyword table (docs/specs/agents.md).

A reader is given the field names, whether the data involve people and whether an embargo is
intended, the categories it may use and the fields the keyword table has flagged already. It
returns flags for other fields and any further questions. It cannot remove or change a keyword
flag: the agent merges the two and keeps every keyword flag (`agent.py`, union only).

`TemplateReader` is the default (`DD_ETHICS_READER` unset or `template`, `factory.py`) and adds
nothing: the flags are the keyword table's. `ModelReader` calls whichever model the agent's
settings name through the SDK's model seam (`dd_sdk.model`, `dd_sdk.model_provider`), so this
package imports no model provider's SDK (docs/specs/dependencies.md). It is sent the field names and
the two context flags, never the title, the description or any data value. The model replies
against a schema (`ReaderReply`), which the provider constrains it to; a reply that does not match,
a refusal and a model that cannot be reached are reported and leave the keyword flags as they are.

What the model returns is checked before it is used (`check`): a flag naming a field not in the
input or a category not in the table is dropped, and the reason is recorded.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from dd_agent_advisor_ethics.classes import SensitivityContext
from dd_sdk.agent import RunContext
from dd_sdk.model import Model, ModelCallError, ModelOutputError, Usage, call
from dd_sdk.prompts import ModelCallLog

DEFAULT_MODEL = "claude-sonnet-5-5"
# What the model is told it may and may not do; the prose is a Markdown file beside this module.
SYSTEM_PROMPT = Path(__file__).with_name("system_prompt.md").read_text(encoding="utf-8").strip()
# The longest reason kept, in characters: a phrase.
MAX_REASON = 200
# The longest question kept, in characters, and how many are kept.
MAX_QUESTION = 400
MAX_QUESTIONS = 3


class _Reply(BaseModel):
    # A reply with a key the schema does not name does not match it.
    model_config = ConfigDict(extra="forbid")


class ModelFlag(_Reply):
    field: str
    category: str
    reason: str


class ReaderReply(_Reply):
    """What the model replies with: flags for fields the keywords missed, and questions."""

    flags: list[ModelFlag]
    questions: list[str]


@dataclass(frozen=True)
class Added:
    """A flag a reader added: a field, a category from the table, and why."""

    field: str
    category: str
    reason: str


@dataclass(frozen=True)
class Reading:
    """What a reader added. Returned rather than kept on the reader, because one reader serves
    concurrent runs."""

    flags: tuple[Added, ...] = ()
    questions: tuple[str, ...] = ()
    # What the model returned that was not used, and why, for the payload and the statement.
    dropped: tuple[str, ...] = ()
    # Why the model's reply as a whole was not used (a refusal, a reply that is not JSON), if so.
    unused: str | None = None
    model_id: str | None = None
    usage: Usage = field(default_factory=Usage)
    # The model calls made and the prompts sent (dd_sdk.prompts); None if no model was called.
    calls: ModelCallLog | None = None


class Reader(Protocol):
    model_id: str | None

    def read(
        self,
        context: SensitivityContext,
        categories: Sequence[str],
        flagged: Sequence[str],
        ctx: RunContext,
    ) -> Reading: ...


class TemplateReader:
    """Adds nothing: the flags are the keyword table's."""

    model_id: str | None = None

    def read(
        self,
        context: SensitivityContext,
        categories: Sequence[str],
        flagged: Sequence[str],
        ctx: RunContext,
    ) -> Reading:
        return Reading()


class ModelReader:
    """Reads the field names with the model the agent's settings name (`dd_sdk.model_provider`), or
    a `dd_sdk.testing.FakeModel` in tests. Emits one `chat` span per call, carrying the model id
    and the token counts (`dd_sdk.model.call`)."""

    def __init__(self, model: Model) -> None:
        self.model = model
        self.model_id: str | None = model.model_id

    def read(
        self,
        context: SensitivityContext,
        categories: Sequence[str],
        flagged: Sequence[str],
        ctx: RunContext,
    ) -> Reading:
        if not context.fields:
            return Reading()
        messages = [{"role": "user", "content": prompt(context, categories, flagged)}]
        try:
            reply = call(
                self.model, ctx, system=SYSTEM_PROMPT, messages=messages, schema=ReaderReply
            )
        except ModelCallError as exc:
            return Reading(
                unused=f"the model could not be reached ({exc})", model_id=self.model.model_id
            )
        except ModelOutputError as error:
            # An endpoint that does not constrain its output may fence the JSON, or stray from
            # the schema; a fenced reply that matches is used, anything else is not.
            got = error.reply
            try:
                parsed = ReaderReply.model_validate_json(_unfenced(got.text))
            except ValidationError:
                return Reading(
                    unused="the model's reply did not match its schema",
                    model_id=got.model_id,
                    usage=got.usage,
                    calls=got.calls,
                )
            return _checked(
                parsed, context, categories, flagged, got.model_id, got.usage, got.calls
            )
        if reply.refused or reply.parsed is None:
            return Reading(
                unused="the model declined to read the field names",
                model_id=reply.model_id,
                usage=reply.usage,
                calls=reply.calls,
            )
        return _checked(
            reply.parsed, context, categories, flagged, reply.model_id, reply.usage, reply.calls
        )


def prompt(context: SensitivityContext, categories: Sequence[str], flagged: Sequence[str]) -> str:
    """The user turn: the field names and the two context flags as JSON, never the title, the
    description or a value."""
    return json.dumps(
        {
            "fields": list(context.fields),
            "involves_people": context.involves_people,
            "embargo_intended": context.embargo_intended,
            "categories": list(categories),
            "already_flagged": list(flagged),
        },
        ensure_ascii=False,
        indent=2,
    )


@dataclass(frozen=True)
class Checked:
    flags: tuple[Added, ...] = ()
    questions: tuple[str, ...] = ()
    dropped: tuple[str, ...] = ()


def check(
    reply: ReaderReply,
    fields: Sequence[str],
    categories: Sequence[str],
    flagged: Sequence[str],
) -> Checked:
    """The flags and questions of `reply` that may be used, and what was dropped and why. A flag
    for a field already flagged is left out silently: the keyword flag stands."""
    known = set(fields)
    allowed = set(categories)
    seen = set(flagged)
    flags: list[Added] = []
    dropped: list[str] = []
    for got in reply.flags:
        if got.field in seen:
            continue
        if got.field not in known:
            dropped.append(f"{got.field}: not one of the field names given")
        elif got.category not in allowed:
            dropped.append(f"{got.field}: category {got.category!r} is not one of the table's")
        elif not got.reason.strip() or len(got.reason) > MAX_REASON:
            dropped.append(f"{got.field}: no short reason given")
        else:
            seen.add(got.field)
            flags.append(Added(got.field, got.category, got.reason.strip()))
    questions: list[str] = []
    for text in (q.strip() for q in reply.questions):
        if not text or text in questions:
            continue
        if len(text) > MAX_QUESTION:
            dropped.append("a question: too long to be one question")
        elif len(questions) == MAX_QUESTIONS:
            dropped.append(f"a question: more than {MAX_QUESTIONS} were asked")
        else:
            questions.append(text)
    return Checked(tuple(flags), tuple(questions), tuple(dropped))


def _checked(
    reply: ReaderReply,
    context: SensitivityContext,
    categories: Sequence[str],
    flagged: Sequence[str],
    model_id: str,
    usage: Usage,
    calls: ModelCallLog,
) -> Reading:
    got = check(reply, context.fields, categories, flagged)
    return Reading(got.flags, got.questions, got.dropped, None, model_id, usage, calls)


def _unfenced(text: str) -> str:
    """The reply without a Markdown code fence around it, which models add unasked."""
    stripped = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL)
    return fenced.group(1) if fenced else stripped
