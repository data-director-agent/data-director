"""Which core requirements a plan's headings cover, by rule.

A plan is split into passages at its headings (`split`): a Markdown heading (`## Storage`), a
numbered line (`3. Storage and backup`, `3.1 Backup`), or a line in bold alone
(`**Storage and backup**`). A section is covered by each passage whose heading holds one of the
section's cues (`coverage`); a heading may name several sections. The rule reads headings only:
it does not say whether a passage answers its section's questions well, or at all, which is for a
person, or a model whose reading a person checks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from dd_dmp_template.sections import SECTIONS, Section

# The longest line read as a heading; a longer one is prose.
MAX_HEADING = 100
_MARKDOWN = re.compile(r"^\s{0,3}#{1,6}\s+(?P<heading>.+?)\s*#*\s*$")
_NUMBERED = re.compile(
    r"^\s*(?:[Ss]ection\s+)?\d+(?:\.\d+)*\.?\s+(?P<heading>[A-Za-z].*?)\s*:?\s*$"
)
_BOLD = re.compile(r"^\s*(?:\*\*|__)(?P<heading>[^*_].*?)(?:\*\*|__)\s*:?\s*$")


@dataclass(frozen=True)
class Passage:
    """A run of a plan's text under one heading, or before the first."""

    heading: str | None
    text: str


@dataclass(frozen=True)
class Coverage:
    """A section, and the passages whose headings name it; none: the plan has no heading for it."""

    section: Section
    passages: tuple[Passage, ...]

    @property
    def covered(self) -> bool:
        return bool(self.passages)


def heading_of(line: str) -> str | None:
    """The heading a line is, or None if it is not one."""
    if len(line.strip()) > MAX_HEADING:
        return None
    for pattern in (_MARKDOWN, _BOLD, _NUMBERED):
        found = pattern.match(line)
        if found is not None:
            heading = found["heading"].strip().strip("*_").strip()
            # A numbered sentence ("1. We will store...") is a list item, not a heading.
            if pattern is _NUMBERED and heading.endswith((".", "?", "!")):
                return None
            return heading or None
    return None


def split(text: str) -> list[Passage]:
    """The plan's passages, in order, each with its heading's text and the lines under it."""
    passages: list[Passage] = []
    heading: str | None = None
    lines: list[str] = []
    for line in text.splitlines():
        found = heading_of(line)
        if found is None:
            lines.append(line)
            continue
        if heading is not None or "\n".join(lines).strip():
            passages.append(Passage(heading, "\n".join(lines).strip()))
        heading, lines = found, []
    if heading is not None or "\n".join(lines).strip():
        passages.append(Passage(heading, "\n".join(lines).strip()))
    return passages


def names(heading: str, section: Section) -> bool:
    """Whether a heading names the section, by one of its cues."""
    lowered = heading.lower()
    return any(cue in lowered for cue in section.cues)


def coverage(text: str, sections: tuple[Section, ...] = SECTIONS) -> list[Coverage]:
    """For each section, in order, the passages of `text` whose headings name it."""
    passages = [p for p in split(text) if p.heading is not None]
    return [
        Coverage(s, tuple(p for p in passages if p.heading is not None and names(p.heading, s)))
        for s in sections
    ]
