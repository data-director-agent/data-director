"""What a model's text is checked against before it is used: that a paragraph is plain prose and
names nothing the facts do not give (`prose.check`, `suggestions.check_suggestions`,
docs/specs/drafting.md), and how a count is written in a statement."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict

from dd_agent_advisor_documentation.counts import check_counts


class StrictReply(BaseModel):
    """A model's reply: one with a key the schema does not name does not match it."""

    model_config = ConfigDict(extra="forbid")


# What a paragraph may not contain: Markdown structure, HTML (the gap markers among it), and the
# template's placeholder, any of which would let prose pass for something it is not.
NOT_PROSE = re.compile(r"^\s*(#|\||[-*+]\s|\d+[.)]\s|>)|<|Still needed:", re.MULTILINE)
# What a paragraph may name only if the facts contain it, as written.
NAMED = (
    re.compile(r"https?://\S+?(?=[.,;:)]?(?:\s|$))"),  # a link
    re.compile(r"\b10\.\d{4,9}/\S+?(?=[.,;:)]?(?:\s|$))"),  # a DOI
    re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),  # an email address
    re.compile(r"\b\d{4}-\d{4}-\d{4}-\d{3}[\dX]\b"),  # an ORCID iD
    re.compile(r"`([^`]+)`"),  # a code-formatted name: a file, a field, a licence
    re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*"),  # a number: a count, a size, a year, a date's parts
)


def unchecked(paragraph: str, facts: Mapping[str, Any], known: str, longest: int) -> str | None:
    """Why a paragraph of prose fails the checks, or None if it passes them."""
    if len(paragraph) > longest:
        return "too long"
    if NOT_PROSE.search(paragraph):
        return "not plain prose"
    for pattern in NAMED:
        for match in pattern.finditer(paragraph):
            named = match.group(match.lastindex or 0)
            if named not in known:
                return f"names {named!r}, which the facts do not give"
    return check_counts(paragraph, facts)


def count(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"
