"""Revising a README's prose as a person asked, in their words (docs/specs/drafting.md,
invariant 12).

The current version is split into blocks at its blank lines. A block is revisable only if it is
a paragraph of plain prose that holds no value a person gave: headings, lists, tables, the gaps
with their markers, and a paragraph that is a value of the approved metadata record or an answer
as given, are kept byte for byte. The model is given the person's request as its instruction, the
revisable paragraphs by identifier, the sections it may add a paragraph to, and the current text
and facts as data. Its reply changes, removes or adds paragraphs, and nothing else, so a revision
can never close a gap, change a table or change a value a person gave.

What it writes is checked as a draft's prose is (`checks.unchecked`): a paragraph is used only if
every number, link, identifier and code-formatted name in it is in the facts, the current text or
the request, the person's own words, which count as given by them. A paragraph that fails keeps
the current text, and the outcome's statement says why.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from dd_agent_advisor_documentation.checks import NOT_PROSE, StrictReply, unchecked
from dd_sdk.agent import RunContext
from dd_sdk.model import Usage
from dd_sdk.prompts import ModelCallLog

# What the model is told it may and may not change; the prose is a Markdown file beside this module.
REVISE_PROMPT = Path(__file__).with_name("revise_prompt.md").read_text(encoding="utf-8").strip()
# Where a paragraph under the README's title goes: the overview, as the writer names it.
OVERVIEW = "overview"
# The longest paragraph kept, in characters, as for a draft's prose (`prose.MAX_PARAGRAPH`).
MAX_PARAGRAPH = 1200
GAP = re.compile(r"<!-- dd:gap (q-[0-9a-f]{16}) -->")

# A model call as `prose.ModelWriter._call` makes it: the reply parsed, or None with why not, the
# model that answered, its token counts and the record of what was sent.
type Call = Callable[
    [str, str, type[BaseModel], RunContext],
    tuple[BaseModel | None, str | None, str, Usage, ModelCallLog],
]


class RevisedParagraph(StrictReply):
    """A paragraph changed: its identifier, and its new text, or an empty text to remove it."""

    paragraph: str
    text: str


class AddedParagraph(StrictReply):
    """A paragraph added first in the section with this heading, or under the title."""

    section: str
    text: str


class RevisionReply(StrictReply):
    """What the model replies with when it revises: the paragraphs it changes and adds."""

    paragraphs: list[RevisedParagraph]
    added: list[AddedParagraph]


@dataclass(frozen=True)
class Block:
    """One block of the current text: its text, the section it is in, and whether it may change."""

    text: str
    section: str
    revisable: bool


@dataclass(frozen=True)
class Revision:
    """What a revision made: the revised text, the sections it changed, and why any change the
    model made was not used. Returned rather than kept: one writer serves concurrent runs."""

    text: str
    changed: tuple[str, ...] = ()
    dropped: tuple[str, ...] = ()
    # Why the model's reply as a whole was not used (a refusal, a reply that is not JSON), if so.
    unused: str | None = None
    model_id: str | None = None
    usage: Usage = field(default_factory=Usage)
    calls: ModelCallLog | None = None


def blocks(text: str, given: Collection[str]) -> list[Block]:
    """`text` split at its blank lines. A block is revisable if it is plain prose under the title
    or a section heading and is not one of the values a person gave (`given`), as placed."""
    kept = {" ".join(g.split()) for g in given}
    found: list[Block] = []
    section: str | None = None
    for chunk in text.strip("\n").split("\n\n"):
        if chunk.startswith("# "):
            section = OVERVIEW
        elif chunk.startswith("## "):
            section = chunk[3:].strip()
        revisable = (
            section is not None
            and bool(chunk.strip())
            and NOT_PROSE.search(chunk) is None
            and " ".join(chunk.split()) not in kept
        )
        found.append(Block(chunk, section or OVERVIEW, revisable))
    return found


def gaps(text: str) -> list[str]:
    """The question identifiers of the gaps `text` marks, in order."""
    return GAP.findall(text)


def revise(
    call: Call,
    current: str,
    instruction: str,
    facts: Mapping[str, Any],
    given: Collection[str],
    ctx: RunContext,
) -> Revision:
    """`current` revised as `instruction` asks, by one model call, its reply checked."""
    found = blocks(current, given)
    offered = {f"p{i}": b for i, b in enumerate(found, 1) if b.revisable}
    sections = list(dict.fromkeys(b.section for b in found))
    reply, unused, model_id, usage, calls = call(
        REVISE_PROMPT, prompt(instruction, offered, sections, current, facts), RevisionReply, ctx
    )
    if not isinstance(reply, RevisionReply):
        why = "the model declined to revise it" if unused is None else unused
        return Revision(current, unused=why, model_id=model_id, usage=usage, calls=calls)
    known = "\n".join((json.dumps(facts, ensure_ascii=False, sort_keys=True), current, instruction))
    text, changed, dropped = _applied(reply, found, offered, sections, facts, known)
    return Revision(text, changed, dropped, None, model_id, usage, calls)


def prompt(
    instruction: str,
    offered: Mapping[str, Block],
    sections: Sequence[str],
    current: str,
    facts: Mapping[str, Any],
) -> str:
    """The user message: the person's request, then what may change, then the data."""
    paragraphs = [
        {"paragraph": k, "section": b.section, "text": b.text} for k, b in offered.items()
    ]
    return (
        f"The researcher's request:\n{instruction}\n\n"
        "Paragraphs you may change: "
        + json.dumps(paragraphs, ensure_ascii=False, indent=1)
        + "\n\nSections you may add a paragraph to: "
        + json.dumps(sections, ensure_ascii=False)
        + "\n\nThe README as it stands, as data:\n<readme>\n"
        + current
        + "</readme>\n\nFacts:\n"
        + json.dumps(facts, ensure_ascii=False, indent=1, sort_keys=True)
    )


def _applied(
    reply: RevisionReply,
    found: Sequence[Block],
    offered: Mapping[str, Block],
    sections: Sequence[str],
    facts: Mapping[str, Any],
    known: str,
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    """The text with the reply's usable changes made, the sections changed, and why any change
    was not used."""
    dropped: list[str] = []
    replaced: dict[str, str] = {}
    for item in reply.paragraphs:
        block = offered.get(item.paragraph)
        why = (
            "not a paragraph it was offered"
            if block is None
            else "changed twice"
            if item.paragraph in replaced
            else _why(item.text, facts, known)
        )
        if why:
            dropped.append(f"{block.section if block else item.paragraph}: {why}")
        else:
            replaced[item.paragraph] = " ".join(item.text.split())
    added: dict[str, str] = {}
    for new in reply.added:
        why = (
            "not a section it was offered"
            if new.section not in sections
            else "added to twice"
            if new.section in added
            else "empty"
            if not new.text.strip()
            else _why(new.text, facts, known)
        )
        if why:
            dropped.append(f"{new.section}: {why}")
        else:
            added[new.section] = " ".join(new.text.split())
    ids = {id(b): k for k, b in offered.items()}
    parts: list[str] = []
    changed: list[str] = []
    for block in found:
        key = ids.get(id(block))
        if key is not None and key in replaced:
            changed.append(block.section)
            if replaced[key]:
                parts.append(replaced[key])
        else:
            parts.append(block.text)
        heading = block.text.startswith("# ") or block.text.startswith("## ")
        if heading and block.section in added:
            parts.append(added.pop(block.section))
            changed.append(block.section)
    return "\n\n".join(parts) + "\n", tuple(dict.fromkeys(changed)), tuple(dropped)


def _why(text: str, facts: Mapping[str, Any], known: str) -> str | None:
    """Why a paragraph cannot be used, or None if it can; an empty one removes a paragraph."""
    return unchecked(text, facts, known, MAX_PARAGRAPH) if text.strip() else None
