"""The tokeniser behind a registry snapshot's lexical (BM25) search.

Words are lower-cased runs of letters and digits; one-character words and stop words are dropped.
Each agent passes the stop words its registry needs, starting from `STOP_WORDS`, so that a word
every record of that registry uses ("data", "policy") does not decide a match. Queries and records
must be tokenised alike.
"""

from __future__ import annotations

import re
from collections.abc import Collection

_TOKEN = re.compile(r"[a-z0-9]+")

STOP_WORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "of",
        "and",
        "or",
        "for",
        "to",
        "in",
        "on",
        "with",
        "by",
        "from",
        "at",
        "as",
        "is",
        "are",
        "be",
        "this",
        "that",
        "its",
        "it",
    }
)


def fold(token: str) -> str:
    """A plural as its singular, so that "science" finds a record that says only "sciences"
    (#741). A light rule rather than a stemmer: `-ies` to `-y`, and a final `s` dropped unless
    the word ends in `ss`, `us` or `is`. Queries and records fold alike, so a word it gets wrong
    (`series` to `serie`) still matches itself."""
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def tokenise(
    text: str, stop: Collection[str] = STOP_WORDS, *, fold_plurals: bool = False
) -> list[str]:
    """The words of `text` a lexical search compares, in order."""
    words = [t for t in _TOKEN.findall(text.lower()) if t not in stop and len(t) > 1]
    return [fold(t) for t in words] if fold_plurals else words
