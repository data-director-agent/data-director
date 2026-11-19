"""Readers: the sharing commitments of a data management plan the researcher attached
(docs/specs/agents.md, Model-backed personas; #962).

A plan is usually free text: a Word document or PDF written for a funding application, or the text
of one. A reader is given the documents the conductor put into the checker's input
(`project_documents`) and proposes each commitment to share an output, with where, how openly and
under what licence, and a quote of the plan's own words. The checker returns the commitments as
project facts (`sharing_commitment`) for the researcher to confirm or correct; nothing a reader
proposes is compared until they have (docs/specs/projects.md, invariant 28).

`TemplateReader` reads nothing: a plan's text is read only by a model. `ModelReader` calls the
model the agent's settings name through the SDK's model seam, as the matcher does (`match.py`), and
the reply is constrained to a schema (`ReadReply`). What it proposes is checked before it is used
(`check`): a commitment must name an output and a document it was given, and its quote must be
found in that document's text once case, whitespace, quotation marks and dashes are set aside.
Anything else is dropped and said. "No commitments found" and "too vague to say" are results, not
failures.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from dd_agent_advisor_dmp.classes import DmpCommitments, SharingCommitment
from dd_agent_advisor_dmp.match import _unfenced
from dd_sdk.agent import RunContext
from dd_sdk.contract.facts import FactKind, ProjectDocument, ProjectFact
from dd_sdk.model import Model, ModelCallError, ModelOutputError, Usage, call
from dd_sdk.prompts import ModelCallLog

READ_PROMPT = Path(__file__).with_name("read_prompt.md").read_text(encoding="utf-8").strip()
# The most text of the attached documents a reader is given, in characters, the latest first.
MAX_PLAN = 60_000
# The fewest characters a quote needs to show a commitment, and the most kept.
MIN_QUOTE, MAX_QUOTE = 12, 800
# Hyphens, dashes and quotation marks, which a quote may give differently from its source.
_CODE_POINTS = (0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x201C, 0x201D, 0x2018, 0x2019)
_SET_ASIDE = "".join(map(chr, _CODE_POINTS)) + "-\"'"
_TRANSLATE = str.maketrans(dict.fromkeys(_SET_ASIDE, " "))


def normalise(text: str) -> str:
    """Text as quotes are matched: case, whitespace, quotation marks and dashes set aside."""
    return " ".join(text.casefold().translate(_TRANSLATE).split())


class _Reply(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReadCommitment(_Reply):
    """One commitment the model read, with the document it is in and the plan's words."""

    output: str
    repository: str | None
    access: str | None
    licence: str | None
    document: int
    quote: str


class ReadReply(_Reply):
    """What the model replies with. Every field is required, as a provider's strict schema needs."""

    commitments: list[ReadCommitment]
    vague: bool


@dataclass(frozen=True)
class Reading:
    """What a reader proposed and the checks kept. Returned rather than kept on the reader,
    because one reader serves concurrent runs."""

    proposals: tuple[ProjectFact, ...] = ()
    # The commitments the model read that were not kept, and why.
    dropped: tuple[str, ...] = ()
    # Whether the model found the plan too vague to name an output.
    vague: bool = False
    # Why the reply as a whole was not used, if so.
    unused: str | None = None
    # The model configured; None on the template path, which reads nothing.
    model_id: str | None = None
    # The documents the model was given, by name, and those cut short to fit.
    read: tuple[str, ...] = ()
    cut: tuple[str, ...] = ()
    usage: Usage = field(default_factory=Usage)
    calls: ModelCallLog | None = None


class PlanReader(Protocol):
    model_id: str | None

    def read(self, documents: Sequence[ProjectDocument], ctx: RunContext) -> Reading: ...


class TemplateReader:
    """Reads nothing: a plan's text is read only by a model."""

    model_id: str | None = None

    def read(self, documents: Sequence[ProjectDocument], ctx: RunContext) -> Reading:
        return Reading()


class ModelReader:
    """Reads a plan's commitments with the model the agent's settings name, or a
    `dd_sdk.testing.FakeModel` in tests."""

    def __init__(self, model: Model) -> None:
        self.model = model
        self.model_id: str | None = model.model_id

    def read(self, documents: Sequence[ProjectDocument], ctx: RunContext) -> Reading:
        given, cut = fitted(documents)
        names = tuple(d.documentation_name for d in given)
        log = ModelCallLog(self.model.provider)
        messages = [{"role": "user", "content": prompt(given, cut)}]
        try:
            reply = call(
                self.model, ctx, system=READ_PROMPT, messages=messages, schema=ReadReply, calls=log
            )
        except ModelCallError as error:
            return _unused(f"the model could not be reached ({error})", self.model_id, names, log)
        except ModelOutputError as error:
            got = error.reply
            try:
                parsed = ReadReply.model_validate_json(_unfenced(got.text))
            except ValidationError:
                why = "the model's reply did not match its schema"
                return _unused(why, got.model_id, names, got.calls, got.usage)
            return check(parsed, given, cut, got.model_id, got.usage, got.calls)
        if reply.parsed is None:
            return _unused("the model declined", reply.model_id, names, reply.calls, reply.usage)
        return check(reply.parsed, given, cut, reply.model_id, reply.usage, reply.calls)


def _unused(
    why: str,
    model_id: str | None,
    names: tuple[str, ...],
    calls: ModelCallLog,
    usage: Usage | None = None,
) -> Reading:
    return Reading(unused=why, model_id=model_id, read=names, usage=usage or Usage(), calls=calls)


def fitted(documents: Sequence[ProjectDocument]) -> tuple[list[ProjectDocument], set[str]]:
    """The documents a reader is given, the latest first, within `MAX_PLAN` characters, and the
    names of those cut short, or left out, to fit."""
    given: list[ProjectDocument] = []
    cut: set[str] = set()
    room = MAX_PLAN
    for document in reversed(documents):
        text = document.documentation_text[:room]
        if len(text) < len(document.documentation_text):
            cut.add(document.documentation_name)
        if text:
            room -= len(text)
            given.append(document.model_copy(update={"documentation_text": text}))
    return given, cut


def prompt(documents: Sequence[ProjectDocument], cut: set[str]) -> str:
    """The user message: the documents, numbered, as JSON."""
    return "The documents the researcher attached, as JSON:\n" + json.dumps(
        [
            {
                "document": n,
                "name": d.documentation_name,
                "text": d.documentation_text,
                **({"cut": True} if d.documentation_name in cut else {}),
            }
            for n, d in enumerate(documents, start=1)
        ],
        ensure_ascii=False,
        indent=1,
    )


def check(
    reply: ReadReply,
    documents: Sequence[ProjectDocument],
    cut: set[str],
    model_id: str,
    usage: Usage,
    calls: ModelCallLog,
) -> Reading:
    """The commitments of a reply that may be proposed, as `sharing_commitment` facts, and why
    any others were not."""
    kept: dict[str, ProjectFact] = {}
    dropped: list[str] = []
    for c in reply.commitments:
        why = _unusable(c, documents)
        if why is None and c.output.strip().casefold() in kept:
            why = "named twice"
        if why:
            dropped.append(f"{c.output.strip() or '(no output)'}: {why}")
            continue
        document = documents[c.document - 1]
        kept[c.output.strip().casefold()] = ProjectFact(
            fact_kind=FactKind.SHARING_COMMITMENT,
            fact_subject=c.output.strip(),
            commitment_repository=_value(c.repository),
            commitment_access=_value(c.access),
            commitment_licence=_value(c.licence),
            commitment_quote=" ".join(c.quote.split()),
            commitment_document=document.documentation_digest,
            proposed_because=(
                f"Read from {document.documentation_name}; check it against the quoted passage."
            ),
        )
    return Reading(
        proposals=tuple(kept.values()),
        dropped=tuple(dropped),
        vague=reply.vague and not kept,
        model_id=model_id,
        read=tuple(d.documentation_name for d in documents),
        cut=tuple(sorted(cut)),
        usage=usage,
        calls=calls,
    )


def _unusable(c: ReadCommitment, documents: Sequence[ProjectDocument]) -> str | None:
    """Why a commitment the model read cannot be proposed, or None if it can."""
    if not c.output.strip():
        return "it names no output"
    if not 1 <= c.document <= len(documents):
        return "it names no document it was given"
    quote = normalise(c.quote)
    if len(quote) < MIN_QUOTE or len(c.quote) > MAX_QUOTE:
        return "its quote is too short or too long to show the commitment"
    if quote not in normalise(documents[c.document - 1].documentation_text):
        return "its quote is not in the document"
    return None


def _value(text: str | None) -> str | None:
    return " ".join(text.split()) if text and text.strip() else None


def confirmed(commitments: DmpCommitments) -> list[SharingCommitment]:
    """The commitments a person confirmed, from the facts the project holds: the last decision
    on each, as the person left it, never what was only proposed."""
    return [
        SharingCommitment(
            output=f.fact_subject,
            repository=f.commitment_repository,
            access=f.commitment_access,
            licence=f.commitment_licence,
        )
        for f in commitments.project_decisions
        if f.fact_kind == FactKind.SHARING_COMMITMENT
    ]
