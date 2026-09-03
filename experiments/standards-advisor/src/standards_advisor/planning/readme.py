"""Reading title, abstract and keywords out of a README (§8).

Pre-collection there is no repository metadata record, because there is no deposit — so the
README R5 has just drafted is the only free-text description of the project, and `retrieve` puts
both the title and the abstract into registry queries. That makes this small function part of
the search path, which is why what it produces carries `Derivation.LOCAL_PARSE`: it is parsed,
not supplied, and a profiling mistake here surfaces as a retrieval mistake.

Deliberately thin, and deliberately not a Markdown parser. Three conventions cover the READMEs
this is meant to read, and anything cleverer would be inventing structure that R5 never promised
to produce:

- the first level-one heading is the title;
- the first run of prose after it is the abstract;
- a `Keywords:` line, comma-separated, is keywords.

Anything not found is left `None` for the caller to fill from elsewhere or leave empty. A README
that does not follow the conventions yields less, not something wrong.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

#: Prefixes of a line that names keywords. Matched case-insensitively on a stripped line.
KEYWORD_PREFIXES: tuple[str, ...] = ("keywords:", "key words:", "tags:")

#: Headings whose following prose is the abstract, when there is no prose directly under the
#: title. `## Description` and friends are the common R5 shapes.
ABSTRACT_HEADINGS: tuple[str, ...] = (
    "description",
    "abstract",
    "summary",
    "overview",
    "about",
)

#: How many characters of prose to take as the abstract. Long enough for a real project
#: description, short enough that a whole README does not become one registry query's free text.
ABSTRACT_MAX_CHARS = 2000


@dataclass(frozen=True)
class ParsedReadme:
    """What could be read out of a README."""

    title: str | None = None
    abstract: str | None = None
    keywords: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    error: str | None = None
    """Set when the file could not be read at all. Not a crash — see `errors`."""


def read_readme(path: Path) -> ParsedReadme:
    """Parse a README. Never raises."""
    if not path.is_file():
        return ParsedReadme(error=f"{path} is not a readable file")
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return ParsedReadme(error=f"{path} could not be read: {exc}")

    # Setext headings are rewritten as ATX first, so everything below has one heading form to
    # reason about. Without it a `Title\n=====` README yielded a title but no abstract, because
    # prose collection only ever started at a `#`.
    lines = _headings_as_atx(text.splitlines())
    title = _title(lines)
    keywords = _keywords(lines)
    abstract, notes = _abstract(lines)
    return ParsedReadme(title=title, abstract=abstract, keywords=keywords, notes=notes)


def _headings_as_atx(lines: list[str]) -> list[str]:
    """Rewrite `Title` + `=====` as `# Title`, and the `-----` form as `## Title`.

    Requiring a non-blank line above is what separates a setext underline from a horizontal
    rule: `---` on its own after a blank line is a rule, and after a line of text it is a
    heading.
    """
    result: list[str] = []
    index = 0
    while index < len(lines):
        current = lines[index]
        following = lines[index + 1].strip() if index + 1 < len(lines) else ""
        if current.strip() and _is_setext_underline(following):
            level = "#" if set(following) == {"="} else "##"
            result.append(f"{level} {current.strip()}")
            index += 2
            continue
        result.append(current)
        index += 1
    return result


def _is_setext_underline(line: str) -> bool:
    return len(line) >= 3 and set(line) in ({"="}, {"-"})


def _title(lines: list[str]) -> str | None:
    """The first level-one heading."""
    for raw in lines:
        line = raw.strip()
        if line.startswith("# "):
            return line[2:].strip() or None
    return None


def _keywords(lines: list[str]) -> list[str]:
    for raw in lines:
        line = raw.strip().lstrip("*-_ ").strip()
        lowered = line.lower()
        for prefix in KEYWORD_PREFIXES:
            if lowered.startswith(prefix):
                tail = line[len(prefix) :]
                return [item.strip(" *_`") for item in tail.split(",") if item.strip(" *_`")]
    return []


def _abstract(lines: list[str]) -> tuple[str | None, list[str]]:
    """The first prose paragraphs, from under the title or under a description heading."""
    notes: list[str] = []
    paragraphs = _paragraphs(lines)
    if not paragraphs:
        return None, notes

    collected = " ".join(paragraphs)
    if len(collected) > ABSTRACT_MAX_CHARS:
        # Truncated rather than dropped, and said out loud: the abstract reaches a registry
        # query, so silently sending a prefix of it would make a query hard to account for.
        notes.append(f"README prose truncated to {ABSTRACT_MAX_CHARS} characters for the abstract")
        collected = collected[:ABSTRACT_MAX_CHARS].rstrip()
    return collected or None, notes


def _paragraphs(lines: list[str]) -> list[str]:
    """Prose paragraphs following the title, or following a description-like heading.

    Stops at the next heading, so a README's title paragraph does not run into its installation
    instructions.
    """
    started = False
    in_description = False
    buffer: list[str] = []
    paragraphs: list[str] = []

    for raw in lines:
        line = raw.strip()

        if line.startswith("#"):
            heading = line.lstrip("#").strip().lower()
            if paragraphs:
                break
            if heading in ABSTRACT_HEADINGS:
                in_description = True
                started = True
                buffer = []
                continue
            started = True
            in_description = False
            buffer = []
            continue

        if not started and not in_description:
            continue
        if _is_setext_underline(line):
            # A leftover rule, not prose. Real setext headings became ATX before this ran.
            continue
        if _is_keyword_line(line):
            continue

        if line:
            buffer.append(line)
        elif buffer:
            paragraphs.append(" ".join(buffer))
            buffer = []

    if buffer:
        paragraphs.append(" ".join(buffer))
    return paragraphs


def _is_keyword_line(line: str) -> bool:
    lowered = line.strip().lstrip("*-_ ").strip().lower()
    return any(lowered.startswith(prefix) for prefix in KEYWORD_PREFIXES)
