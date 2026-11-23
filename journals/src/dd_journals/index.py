"""The SQLite index `Registry` reads: built locally from the journals, never pinned itself.

The pinned file is `journals.jsonl`; this index is derived from it on each machine, so that a
look-up needs neither the whole registry in memory nor time to load it. It records which
`journals.jsonl` it was built from (`meta.registry_sha256`), and a reader refuses an index built
from anything else. Tables:

- `journals`: each journal's line of `journals.jsonl`, by ISSN-L, with its count of works;
- `issns`: every ISSN, to the ISSN-L of its journal (the lowest ISSN-L where two claim one);
- `titles`: each journal's titles, folded (`fold`), to find a title that is or starts with the
  text;
- `words`: an FTS5 table of each journal's folded titles together, to find every word typed.
"""

from __future__ import annotations

import json
import sqlite3
import unicodedata
from collections.abc import Iterable
from pathlib import Path

from dd_journals.records import Journal

_KEEP = frozenset("abcdefghijklmnopqrstuvwxyz0123456789")

SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE journals (issn_l TEXT PRIMARY KEY, works_count INTEGER NOT NULL, doc TEXT NOT NULL);
CREATE TABLE issns (issn TEXT PRIMARY KEY, issn_l TEXT NOT NULL);
CREATE TABLE titles (issn_l TEXT NOT NULL, folded TEXT NOT NULL);
CREATE VIRTUAL TABLE words USING fts5(issn_l UNINDEXED, text, prefix='1 2 3');
"""
INDEXES = "CREATE INDEX titles_folded ON titles (folded);"


def fold(text: str) -> str:
    """`text` as titles are compared: accents, case and punctuation set aside, "&" read as "and",
    and a leading "The" dropped."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    spaced = "".join(c if c in _KEEP else " " for c in plain.lower().replace("&", " and "))
    words = spaced.split()
    if len(words) > 1 and words[0] == "the":
        words = words[1:]
    return " ".join(words)


def folded_titles(journal: Journal) -> list[str]:
    """The journal's titles, folded, each once, in order: title, alternates, abbreviation."""
    names = (journal.title, *journal.alternate_titles, journal.abbreviated_title or "")
    return list(dict.fromkeys(t for n in names if (t := fold(n))))


def build_index(
    journals: Iterable[Journal], path: Path, registry_sha256: str, label: str = ""
) -> int:
    """Write the index of `journals` to `path`, replacing any there; how many it holds."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".part")
    partial.unlink(missing_ok=True)
    count = 0
    with sqlite3.connect(partial) as db:
        db.executescript(SCHEMA)
        for journal in sorted(journals, key=lambda j: j.issn_l):
            doc = json.dumps(journal.as_dict(), ensure_ascii=False, sort_keys=True)
            db.execute(
                "INSERT INTO journals VALUES (?, ?, ?)",
                (journal.issn_l, journal.works_count, doc),
            )
            db.executemany(
                "INSERT OR IGNORE INTO issns VALUES (?, ?)",
                [(issn, journal.issn_l) for issn in journal.issns],
            )
            titles = folded_titles(journal)
            db.executemany(
                "INSERT INTO titles VALUES (?, ?)", [(journal.issn_l, t) for t in titles]
            )
            db.execute("INSERT INTO words VALUES (?, ?)", (journal.issn_l, " ".join(titles)))
            count += 1
        db.executescript(INDEXES)
        db.executemany(
            "INSERT INTO meta VALUES (?, ?)",
            [("registry_sha256", registry_sha256), ("label", label), ("journals", str(count))],
        )
    db.close()
    partial.replace(path)
    return count
