"""Counts by rule: how many files sit at the top level and in each folder, worked out from the
inventory's paths, and a check that the counts a README's prose states are among them
(docs/specs/drafting.md, invariant 4).

A writer is given these counts with the rest of the facts, so it need not add anything up. What it
writes is still checked: a number written out in words, or a digit next to "file", "folder" or
"table", must be one of the counts the facts give, and a sentence about the top level must give
the number of files there. A paragraph that fails is not used (`prose.check`).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from pathlib import PurePosixPath
from typing import Any

from dd_sdk.contract.models import FileInventory

# The numbers a paragraph may write out in words. "one" is left out: it is as often a pronoun.
_WORDS = {
    word: n
    for n, word in enumerate(
        [
            "zero",
            "one",
            "two",
            "three",
            "four",
            "five",
            "six",
            "seven",
            "eight",
            "nine",
            "ten",
            "eleven",
            "twelve",
            "thirteen",
            "fourteen",
            "fifteen",
            "sixteen",
            "seventeen",
            "eighteen",
            "nineteen",
            "twenty",
        ]
    )
    if n >= 2
}
_NUMBER = r"\d+(?:,\d{3})*|" + "|".join(_WORDS)
# A count written out in words, anywhere.
_WORD_COUNT = re.compile(rf"\b({'|'.join(_WORDS)})\b", re.IGNORECASE)
# A digit, or a word, followed within a few words by what the facts count.
_NOUN_COUNT = re.compile(
    rf"\b({_NUMBER})\b(?:\s+[\w-]+){{0,2}}?\s+(?:files?|folders?|subfolders?|director(?:y|ies)|"
    r"tables?)\b",
    re.IGNORECASE,
)
# Any number, for the top-level check: "one" counts here, since only a count is near the phrase.
_ANY_NUMBER = re.compile(rf"\b({_NUMBER}|one)\b", re.IGNORECASE)
_TOP_LEVEL = re.compile(r"\btop[\s-]level\b", re.IGNORECASE)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
# A code-formatted name, whose digits are a name's and not a count.
_CODE = re.compile(r"`[^`]*`")


def counted(inventory: FileInventory) -> dict[str, Any]:
    """Every count a writer is given: of the inventory's files, their bytes, its tables, and
    (`layout`) its folders and the files at its top level and in each folder."""
    files = inventory.inventory_files
    return {
        "file_count": len(files),
        "total_size_bytes": sum(f.file_size for f in files),
        "table_count": sum(1 for f in files if f.file_fields),
        **layout(f.file_path for f in files),
    }


def layout(paths: Iterable[str]) -> dict[str, Any]:
    """The inventory's folders and the files at its top level, counted from its paths: how many
    files sit at the top level, how many folders there are, and how many files each folder holds,
    its subfolders' included."""
    files = [PurePosixPath(p) for p in paths]
    under: dict[str, int] = {}
    for path in files:
        for parent in path.parents:
            if str(parent) != ".":
                under[str(parent)] = under.get(str(parent), 0) + 1
    return {
        "top_level_file_count": sum(1 for p in files if len(p.parts) == 1),
        "folder_count": len(under),
        "folders": [{"path": f, "file_count": n} for f, n in sorted(under.items())],
    }


def _value(number: str) -> int:
    word = number.lower()
    return 1 if word == "one" else _WORDS.get(word) or int(number.replace(",", ""))


def _counts(facts: Mapping[str, Any]) -> set[int]:
    """Every count the facts give."""
    given = {
        facts[k]
        for k in ("file_count", "table_count", "top_level_file_count", "folder_count")
        if isinstance(facts.get(k), int)
    }
    return given | {f["file_count"] for f in facts.get("folders", ())}


def check_counts(paragraph: str, facts: Mapping[str, Any]) -> str | None:
    """Why the counts a paragraph states are not the facts', or None if they are."""
    if "file_count" not in facts:
        return None
    text = _CODE.sub("``", paragraph)
    counts = _counts(facts)
    for match in [*_WORD_COUNT.finditer(text), *_NOUN_COUNT.finditer(text)]:
        if _value(match.group(1)) not in counts:
            return f"names {match.group(1)!r}, which is not a count the facts give"
    top = facts.get("top_level_file_count")
    for sentence in _SENTENCE.split(text):
        phrase = _TOP_LEVEL.search(sentence)
        numbers = list(_ANY_NUMBER.finditer(sentence))
        if phrase is None or not numbers or not isinstance(top, int):
            continue
        nearest = min(numbers, key=lambda m: abs(m.start() - phrase.start()))
        if _value(nearest.group(1)) != top:
            return (
                f"says {nearest.group(1)!r} at the top level, where the inventory has {top} "
                f"{'file' if top == 1 else 'files'}"
            )
    return None
