"""Writers: the retrofit recommendation for each check the record does not meet (R9).

The rules in `checks.yaml` decide whether each check is met (`agent.py`); a writer is given only
the checks that are not, and returns one recommendation for each, in order. It cannot change
whether a check is met, drop a check or add one.

`TemplateWriter` is the default (`DD_FAIRNESS_WRITER` unset or `template`, `factory.py`): each
recommendation is the rule table's own text. `ModelWriter` calls whichever model the agent's
settings name through the SDK's model seam (`dd_sdk.model`, `dd_sdk.model_provider`), so this
package imports no model provider's SDK (docs/specs/dependencies.md). It is sent the record as the
researcher gave it and the unmet checks with their template text, and replies against a schema
(`WriterReply`).

What the model returns is checked before it is used (`check`): a recommendation for a check that
was not sent, an empty or overlong one, or one naming an identifier or address the record does not
give, is dropped and the reason recorded. Each unmet check whose recommendation was dropped or not
given keeps its template text, marked `template`. A refusal, a reply that does not match the
schema and a model that cannot be reached leave every recommendation as the template's.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from dd_agent_advisor_fairness.classes import PublishedRecord
from dd_sdk.agent import RunContext
from dd_sdk.contract.models import Derivation
from dd_sdk.model import Model, ModelCallError, ModelOutputError, Usage, call
from dd_sdk.prompts import ModelCallLog

DEFAULT_MODEL = "claude-sonnet-5-5"
# What the model is told it may and may not do; the prose is a Markdown file beside this module.
SYSTEM_PROMPT = Path(__file__).with_name("system_prompt.md").read_text(encoding="utf-8").strip()
# The longest recommendation kept, in characters: two or three sentences.
MAX_RECOMMENDATION = 600
# Identifiers and addresses a recommendation may name only if the record gives them: a DOI, an
# ORCID iD and any web address.
IDENTIFIER = re.compile(
    r"https?://[^\s\"'<>()]+|\b10\.\d{4,9}/[^\s\"'<>()]+|\b\d{4}-\d{4}-\d{4}-\d{3}[\dX]\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Unmet:
    """A check the record does not meet, as a writer is told it: the FAIR sub-principle, the
    check's identifier and the rule table's recommendation."""

    principle: str
    check: str
    template: str


@dataclass(frozen=True)
class Recommendation:
    text: str
    derivation: Derivation


class _Reply(BaseModel):
    # A reply with a key the schema does not name does not match it.
    model_config = ConfigDict(extra="forbid")


class WrittenRecommendation(_Reply):
    check: str
    recommendation: str


class WriterReply(_Reply):
    """What the model replies with: one recommendation per unmet check, by check identifier."""

    recommendations: list[WrittenRecommendation]


@dataclass(frozen=True)
class Writing:
    """One recommendation per unmet check, in order. Returned rather than kept on the writer,
    because one writer serves concurrent runs."""

    recommendations: tuple[Recommendation, ...] = ()
    # What the model returned that was not used, and why, for the statement.
    dropped: tuple[str, ...] = ()
    # Why the model's reply as a whole was not used (a refusal, a reply that is not JSON), if so.
    unused: str | None = None
    model_id: str | None = None
    usage: Usage = field(default_factory=Usage)
    # The model calls made and the prompts sent (dd_sdk.prompts); None if no model was called.
    calls: ModelCallLog | None = None


class Writer(Protocol):
    model_id: str | None

    def write(
        self, record: PublishedRecord, unmet: Sequence[Unmet], ctx: RunContext
    ) -> Writing: ...


def templated(unmet: Sequence[Unmet]) -> tuple[Recommendation, ...]:
    return tuple(Recommendation(u.template, Derivation.TEMPLATE) for u in unmet)


class TemplateWriter:
    """Each recommendation is the rule table's own text."""

    model_id: str | None = None

    def write(self, record: PublishedRecord, unmet: Sequence[Unmet], ctx: RunContext) -> Writing:
        return Writing(templated(unmet))


class ModelWriter:
    """Writes with the model the agent's settings name (`dd_sdk.model_provider`), or a
    `dd_sdk.testing.FakeModel` in tests. Emits one `chat` span per call, carrying the model id
    and the token counts (`dd_sdk.model.call`)."""

    def __init__(self, model: Model) -> None:
        self.model = model
        self.model_id: str | None = model.model_id

    def write(self, record: PublishedRecord, unmet: Sequence[Unmet], ctx: RunContext) -> Writing:
        if not unmet:
            return Writing()
        messages = [{"role": "user", "content": prompt(record, unmet)}]
        try:
            reply = call(
                self.model, ctx, system=SYSTEM_PROMPT, messages=messages, schema=WriterReply
            )
        except ModelCallError as exc:
            return Writing(
                templated(unmet),
                unused=f"the model could not be reached ({exc})",
                model_id=self.model.model_id,
            )
        except ModelOutputError as error:
            # An endpoint that does not constrain its output may fence the JSON, or stray from
            # the schema; a fenced reply that matches is used, anything else is not.
            got = error.reply
            try:
                parsed = WriterReply.model_validate_json(_unfenced(got.text))
            except ValidationError:
                return Writing(
                    templated(unmet),
                    unused="the model's reply did not match its schema",
                    model_id=got.model_id,
                    usage=got.usage,
                    calls=got.calls,
                )
            return _checked(parsed, record, unmet, got.model_id, got.usage, got.calls)
        if reply.refused or reply.parsed is None:
            return Writing(
                templated(unmet),
                unused="the model declined to write the recommendations",
                model_id=reply.model_id,
                usage=reply.usage,
                calls=reply.calls,
            )
        return _checked(reply.parsed, record, unmet, reply.model_id, reply.usage, reply.calls)


def prompt(record: PublishedRecord, unmet: Sequence[Unmet]) -> str:
    """The user turn: the record as the researcher gave it, and the unmet checks, as JSON."""
    return json.dumps(
        {
            "record": record.model_dump(mode="json", exclude={"schema_class"}),
            "unmet_checks": [
                {"check": u.check, "principle": u.principle, "template": u.template} for u in unmet
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


def given_identifiers(record: PublishedRecord) -> tuple[str, ...]:
    """The identifiers and addresses the record gives, lower-cased: a recommendation may name
    these, or a part of one (an ORCID iD within its URL), and nothing else."""
    given = [record.identifier or "", *record.creator_identifiers, *record.related_identifiers]
    return tuple(g.strip().lower() for g in given if g.strip())


def names_other_identifier(text: str, given: Sequence[str]) -> bool:
    """Whether `text` names a DOI, ORCID iD or web address the record does not give."""
    for found in IDENTIFIER.findall(text):
        wanted = found.rstrip(".,;:").lower()
        if not any(wanted in g for g in given):
            return True
    return False


@dataclass(frozen=True)
class Checked:
    recommendations: tuple[Recommendation, ...]
    dropped: tuple[str, ...] = ()


def check(reply: WriterReply, record: PublishedRecord, unmet: Sequence[Unmet]) -> Checked:
    """One recommendation per unmet check, in order: the model's where it may be used, the
    template's otherwise, and what was dropped and why."""
    sent = {u.check for u in unmet}
    given = given_identifiers(record)
    written: dict[str, str] = {}
    dropped: list[str] = []
    for got in reply.recommendations:
        text = got.recommendation.strip()
        if got.check not in sent:
            dropped.append(f"{got.check}: not one of the unmet checks")
        elif got.check in written:
            dropped.append(f"{got.check}: a second recommendation for the same check")
        elif not text or len(text) > MAX_RECOMMENDATION:
            dropped.append(f"{got.check}: no short recommendation given")
        elif names_other_identifier(text, given):
            dropped.append(f"{got.check}: names an identifier or address the record does not give")
        else:
            written[got.check] = text
    recommendations = tuple(
        Recommendation(written[u.check], Derivation.MODEL)
        if u.check in written
        else Recommendation(u.template, Derivation.TEMPLATE)
        for u in unmet
    )
    return Checked(recommendations, tuple(dropped))


def _checked(
    reply: WriterReply,
    record: PublishedRecord,
    unmet: Sequence[Unmet],
    model_id: str,
    usage: Usage,
    calls: ModelCallLog,
) -> Writing:
    got = check(reply, record, unmet)
    return Writing(got.recommendations, got.dropped, None, model_id, usage, calls)


def _unfenced(text: str) -> str:
    """The reply without a Markdown code fence around it, which models add unasked."""
    stripped = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL)
    return fenced.group(1) if fenced else stripped
