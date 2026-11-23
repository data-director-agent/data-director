"""The built journal registry: look a journal up by any of its ISSNs, or search by title."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from dd_journals.issn import normal_issn
from dd_journals.records import Journal

DEFAULT_LIMIT = 10
_NOT_WORD = re.compile(r"[^0-9a-z]+")


class PinError(Exception):
    """The registry is missing, or does not match its pin. The message says what to do."""


def fold(text: str) -> str:
    """`text` as titles are compared: accents, case and punctuation set aside, "&" read as "and",
    and a leading "The" dropped."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    words = _NOT_WORD.sub(" ", plain.lower().replace("&", " and ")).split()
    if len(words) > 1 and words[0] == "the":
        words = words[1:]
    return " ".join(words)


@dataclass(frozen=True)
class _Entry:
    journal: Journal
    titles: tuple[str, ...]
    words: frozenset[str] = field(default_factory=frozenset)


def _entry(journal: Journal) -> _Entry:
    names = (journal.title, *journal.alternate_titles, journal.abbreviated_title or "")
    titles = tuple(dict.fromkeys(t for n in names if (t := fold(n))))
    words = frozenset(w for t in titles for w in t.split())
    return _Entry(journal, titles, words)


def _tier(entry: _Entry, query: str, query_words: list[str]) -> int | None:
    """How well a title matches: 0 the same, 1 starting with the query, 2 every word of the query
    starting a word of the title; None for no match."""
    if query in entry.titles:
        return 0
    if any(t.startswith(query) for t in entry.titles):
        return 1
    if all(any(w.startswith(q) for w in entry.words) for q in query_words):
        return 2
    return None


class Registry:
    """Journals held in memory, from `journals.jsonl` or any iterable of `Journal`."""

    def __init__(self, journals: Iterable[Journal]) -> None:
        self._entries = [_entry(j) for j in sorted(journals, key=lambda j: j.issn_l)]
        self._by_issn: dict[str, Journal] = {}
        for entry in self._entries:
            for issn in entry.journal.issns:
                # Sorted by ISSN-L, so an ISSN two journals claim always goes to the same one.
                self._by_issn.setdefault(issn, entry.journal)

    @classmethod
    def load(cls, path: Path, sha256: str | None = None) -> Registry:
        """The registry built at `path`, checked against `sha256` when it is given."""
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            raise PinError(f"{path} is not built: run `dd-journals fetch`") from None
        if sha256 is not None and hashlib.sha256(data).hexdigest() != sha256:
            raise PinError(f"{path} does not match its pin: run `dd-journals fetch` to rebuild it")
        lines = data.decode("utf-8").splitlines()
        return cls(Journal.from_dict(json.loads(line)) for line in lines if line)

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, issn: str) -> Journal | None:
        """The journal with this ISSN, print, online or linking, or None."""
        normal = normal_issn(issn)
        return self._by_issn.get(normal) if normal else None

    def search(self, text: str, limit: int = DEFAULT_LIMIT) -> list[Journal]:
        """Journals for what a person typed: the journal with that ISSN, or journals whose title
        matches. A title that is the same comes first, then one that starts with the text, then
        one with words starting with each word typed. Within each, journals with more works come
        first, then by ISSN-L, so the same text always gives the same list."""
        if (journal := self.get(text)) is not None:
            return [journal]
        query = fold(text)
        if not query or limit < 1:
            return []
        query_words = query.split()
        ranked: list[tuple[int, int, str, Journal]] = []
        for entry in self._entries:
            tier = _tier(entry, query, query_words)
            if tier is not None:
                journal = entry.journal
                ranked.append((tier, -journal.works_count, journal.issn_l, journal))
        ranked.sort(key=lambda r: r[:3])
        return [r[3] for r in ranked[:limit]]
