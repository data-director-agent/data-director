"""Interpreters: the reuse a researcher wants, read by a model (docs/specs/agents.md, Model-backed
personas).

The rules in `agent.py` understand the reuse wanted only when it is one of the table's own
values (`any`, `attribution`, `share-alike`, `non-commercial`), and ask fixed questions whatever
the context. An interpreter is given what the rules could not read, and may propose:

- `reuse`: the table's values that the researcher's own words fit ("anyone may use it but not
  sell it" is `non-commercial`), when the rules did not understand them;
- `licences`: the order in which to offer the licences that fit those values; and
- `questions`: up to three questions about third-party content or a mandated licence, tailored to
  what the researcher said.

The licences are a closed set (item 3 of Model-backed personas): every licence offered is a row
of `licences.yaml`, built by `agent.py` from that row. A reuse value the table does not have, or a
licence that is not among those that fit, is dropped and recorded, so a licence the model names
from outside the table cannot reach the payload. A licence that fits is never left out: one the
model does not order follows in the table's order. A mandated licence is listed by rule, as
before.

`ModelInterpreter` is the default (`DD_RIGHTS_INTERPRETER` unset or `model`, `factory.py`);
`TemplateInterpreter` (`DD_RIGHTS_INTERPRETER=template`) proposes nothing, so the rules' result
stands, and needs no key. `ModelInterpreter` calls whichever model the agent's settings name
through the SDK's model seam (`dd_sdk.model`, `dd_sdk.model_provider`), so this package imports no
model provider's SDK. A refused reply, a reply that is not the schema's JSON, or a model that
cannot be reached leaves the rules' result as it is, and the agent says so.

TODO(#877): the closed set becomes the SPDX records the shell retrieves through the tool gateway,
and a `licence-choice` Skill joins the system prompt; `check` keeps its rule.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from dd_sdk.agent import RunContext
from dd_sdk.model import CallOptions, Model, ModelCallError, ModelOutputError, Usage, call
from dd_sdk.prompts import ModelCallLog

DEFAULT_MODEL = "claude-sonnet-5-5"
# What the model is told it may propose; the prose is a Markdown file beside this module.
SYSTEM_PROMPT = Path(__file__).with_name("system_prompt.md").read_text(encoding="utf-8").strip()
# The most questions kept, and the longest, in characters: a question, not an essay.
MAX_QUESTIONS = 3
MAX_QUESTION = 300


def key(text: str) -> str:
    """How values and identifiers are compared: case and surrounding spaces ignored."""
    return text.strip().casefold()


@dataclass(frozen=True)
class Asked:
    """All an interpreter is given: what the rules could not read, and the table to choose from.

    `reuse_wanted` is set only when the rules did not understand it. `fixed_questions` are the
    rules' own questions, which a model's question may not repeat."""

    table: Mapping[str, Any]
    reuse_wanted: str | None = None
    mandated_licence: str | None = None
    third_party_content: bool | None = None
    fixed_questions: tuple[str, ...] = ()

    @property
    def readable(self) -> bool:
        """Whether there is anything to read: words the rules did not understand, or third-party
        content or a mandate to tailor questions to."""
        return bool(self.reuse_wanted) or bool(self.third_party_content) or self.may_ask

    @property
    def may_ask(self) -> bool:
        """Whether a model may add questions: only about third-party content or a mandate."""
        return bool(self.third_party_content) or bool(self.mandated_licence)

    def fits(self) -> list[str]:
        """The table's reuse values, in the table's order."""
        seen: dict[str, None] = {}
        for row in self.table["licences"]:
            for fit in row["fits"]:
                seen.setdefault(fit, None)
        return list(seen)


class _Reply(BaseModel):
    # A reply with a key the schema does not name does not match it.
    model_config = ConfigDict(extra="forbid")


class RightsReply(_Reply):
    """What the model replies with. Every field is required, as a provider's strict schema
    needs; an empty list proposes nothing."""

    reuse: list[str]
    licences: list[str]
    questions: list[str]


@dataclass(frozen=True)
class Reading:
    """What an interpreter proposed and the checks kept. Returned rather than kept on the
    interpreter, because one interpreter serves concurrent runs."""

    # The table's reuse values the words fit, in the table's order; empty if none was read.
    reuse: tuple[str, ...] = ()
    # The SPDX ids, as the table writes them, of every licence that fits `reuse`, in the order to
    # offer them; empty with `reuse`, and on a mandate, whose licence is listed by rule.
    licences: tuple[str, ...] = ()
    questions: tuple[str, ...] = ()
    # What the model proposed that was not used, and why, for the payload and the statement.
    dropped: tuple[str, ...] = ()
    # Why the model's reply as a whole was not used (a refusal, a reply that is not JSON), if so.
    unused: str | None = None
    # The model configured, whether or not it was called; None on the template path.
    model_id: str | None = None
    # Whether the model was called: not when there is nothing for it to read.
    called: bool = False
    usage: Usage = field(default_factory=Usage)
    # The model calls made and the prompts sent (dd_sdk.prompts); None if no model was called.
    calls: ModelCallLog | None = None


class Interpreter(Protocol):
    model_id: str | None

    def read(self, asked: Asked, ctx: RunContext) -> Reading: ...


class TemplateInterpreter:
    """Proposes nothing: the rules' result stands."""

    model_id: str | None = None

    def read(self, asked: Asked, ctx: RunContext) -> Reading:
        return Reading()


class ModelInterpreter:
    """Reads the reuse wanted and tailors questions with the model the agent's settings name
    (`dd_sdk.model_provider`), or a `dd_sdk.testing.FakeModel` in tests. Emits one `chat` span per
    call, carrying the model id and the token counts (`dd_sdk.model.call`)."""

    def __init__(self, model: Model) -> None:
        self.model = model
        self.model_id: str | None = model.model_id

    def read(self, asked: Asked, ctx: RunContext) -> Reading:
        if not asked.readable:
            return Reading(model_id=self.model_id)
        log = ModelCallLog(self.model.provider)
        messages = [{"role": "user", "content": prompt(asked)}]
        try:
            reply = call(
                self.model,
                ctx,
                system=SYSTEM_PROMPT,
                messages=messages,
                schema=RightsReply,
                options=CallOptions(calls=log),
            )
        except ModelCallError as error:
            return self._unused(f"the model could not be reached ({error})", log)
        except ModelOutputError as error:
            # An endpoint that does not constrain its output may fence the JSON, or stray from
            # the schema; a fenced reply that matches is used, anything else is not.
            got = error.reply
            try:
                parsed = RightsReply.model_validate_json(_unfenced(got.text))
            except ValidationError:
                return self._unused(
                    "the model's reply did not match its schema", got.calls, got.usage, got.model_id
                )
            return check(parsed, asked, got.model_id, got.usage, got.calls)
        if reply.parsed is None:
            return self._unused("the model declined", reply.calls, reply.usage, reply.model_id)
        return check(reply.parsed, asked, reply.model_id, reply.usage, reply.calls)

    def _unused(
        self,
        why: str,
        calls: ModelCallLog,
        usage: Usage | None = None,
        model_id: str | None = None,
    ) -> Reading:
        return Reading(
            unused=why,
            model_id=model_id or self.model_id,
            called=True,
            usage=usage or Usage(),
            calls=calls,
        )


def prompt(asked: Asked) -> str:
    """The user message, as JSON: what the researcher said that the rules could not read, and the
    table's licences to choose from. Nothing else about the dataset is sent."""
    said: dict[str, Any] = {}
    if asked.reuse_wanted:
        said["reuse_wanted"] = asked.reuse_wanted
    if asked.mandated_licence:
        said["mandated_licence"] = asked.mandated_licence
    if asked.third_party_content is not None:
        said["third_party_content"] = asked.third_party_content
    return "What the researcher said, the reuse values and the licences, as JSON:\n" + json.dumps(
        {
            "said": said,
            "reuse_values": asked.fits(),
            "licences": [
                {"spdx_id": row["spdx_id"], "name": row["name"], "fits": list(row["fits"])}
                for row in asked.table["licences"]
            ],
            "questions_already_asked": list(asked.fixed_questions),
        },
        ensure_ascii=False,
        indent=1,
    )


def check(
    reply: RightsReply,
    asked: Asked,
    model_id: str | None = None,
    usage: Usage | None = None,
    calls: ModelCallLog | None = None,
) -> Reading:
    """What of a model's reply may be used, and why anything else was not. Every value kept is
    one the table or the request already holds, apart from the questions, which are prose for
    the researcher and are only kept where they may be asked."""
    dropped: list[str] = []

    known = {key(v): v for v in asked.fits()}
    reuse: list[str] = []
    for value in reply.reuse:
        why = (
            "the rules already read the reuse wanted, or none was given"
            if not asked.reuse_wanted
            else f"'{value}' is not a reuse value in the table"
            if key(value) not in known
            else "given twice"
            if known[key(value)] in reuse
            else None
        )
        if why:
            dropped.append(f"reuse '{value}': {why}")
            continue
        reuse.append(known[key(value)])
    reuse = [v for v in asked.fits() if v in reuse]  # the table's order

    fitting = [row["spdx_id"] for row in asked.table["licences"] if set(row["fits"]) & set(reuse)]
    by_id = {key(i): i for i in fitting}
    ordered: list[str] = []
    for spdx_id in reply.licences:
        why = (
            "a mandated licence is listed by rule"
            if asked.mandated_licence
            else f"'{spdx_id}' is not among the licences that fit the reuse read"
            if key(spdx_id) not in by_id
            else "given twice"
            if by_id[key(spdx_id)] in ordered
            else None
        )
        if why:
            dropped.append(f"licence '{spdx_id}': {why}")
            continue
        ordered.append(by_id[key(spdx_id)])
    licences: list[str] = []
    if not asked.mandated_licence:
        licences = ordered + [i for i in fitting if i not in ordered]

    fixed = {key(q) for q in asked.fixed_questions}
    questions: list[str] = []
    for text in reply.questions:
        tidy = " ".join(text.split())
        why = (
            "it may only ask about third-party content or a mandated licence, and neither was given"
            if not asked.may_ask
            else "it is empty"
            if not tidy
            else "it is too long"
            if len(tidy) > MAX_QUESTION
            else "it repeats a question already asked"
            if key(tidy) in fixed or key(tidy) in {key(q) for q in questions}
            else f"more than {MAX_QUESTIONS} questions"
            if len(questions) >= MAX_QUESTIONS
            else None
        )
        if why:
            dropped.append(f"question '{_short(tidy)}': {why}")
            continue
        questions.append(tidy)

    return Reading(
        reuse=tuple(reuse),
        licences=tuple(licences),
        questions=tuple(questions),
        dropped=tuple(dropped),
        model_id=model_id,
        called=True,
        usage=usage or Usage(),
        calls=calls,
    )


def _short(text: str, longest: int = 60) -> str:
    return text if len(text) <= longest else text[: longest - 1] + "…"


def _unfenced(text: str) -> str:
    """The reply without a Markdown code fence around it, which models add unasked."""
    stripped = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL)
    return fenced.group(1) if fenced else stripped
