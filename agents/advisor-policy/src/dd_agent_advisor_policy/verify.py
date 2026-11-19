"""Checks a model's claims about a policy record before any is kept.

A model may say what a record asks only with a quote: words that the agent then finds in that
record's document, after case, whitespace, quotation marks and dashes are set aside. A quote too
short to state anything, or not found in the record it names, is dropped, and the reason is kept
for the run's statement. This is what lets a model read a policy's text without being able to
state an obligation the text does not.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from dd_sdk import explain

# The fewest characters and words a quote needs to state an obligation, so that "yes" or
# "required" alone, which occur in most records, cannot stand as evidence.
MIN_QUOTE_CHARS = 15
MIN_QUOTE_WORDS = 3

_FOLD = str.maketrans(
    {
        0x2018: "'",  # left single quotation mark
        0x2019: "'",  # right single quotation mark
        0x201C: '"',  # left double quotation mark
        0x201D: '"',  # right double quotation mark
        0x2013: "-",  # en dash
        0x2014: "-",  # em dash
        0x00A0: " ",  # no-break space
    }
)


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_FOLD).casefold()
    # Underscores join a registry's codes ("cc_by_nc"); a quote may give them as spaces.
    text = text.replace("_", " ")
    return " ".join(text.split())


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def document_text(document: dict[str, Any]) -> str:
    """Every string in the document, normalised, one per line: what a quote is searched in."""
    return "\n".join(normalise(s) for s in _strings(document))


def quote_problem(quote: str, document: dict[str, Any]) -> str | None:
    """Why `quote` cannot stand as evidence from `document`, or None if it can. A quote is found
    within one string of the document, never across two."""
    wanted = normalise(quote).strip(" .\"'…")
    if len(wanted) < MIN_QUOTE_CHARS or len(wanted.split()) < MIN_QUOTE_WORDS:
        return "the quote is too short to state an obligation"
    if not any(wanted in line for line in document_text(document).splitlines()):
        return "the quote is not in the record"
    return None


IDENTIFIER = re.compile(r"\bFAIRsharing\.[0-9A-Za-z-]+", re.IGNORECASE)


def names_other_identifier(text: str, allowed: set[str]) -> bool:
    """Whether `text` names a FAIRsharing identifier outside `allowed`."""
    return explain.names_other_identifier(text, allowed, IDENTIFIER)
