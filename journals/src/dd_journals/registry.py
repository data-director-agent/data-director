"""The built journal registry: look a journal up by any of its ISSNs, or search by title.

It reads the SQLite index (`index.py`) read-only, with a connection for each look-up, so that one
`Registry` may be shared between threads and holds nothing in memory but its path.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import closing, contextmanager
from pathlib import Path

from dd_journals.index import build_index, fold
from dd_journals.issn import normal_issn
from dd_journals.records import Journal

__all__ = ["DEFAULT_LIMIT", "PinError", "Registry", "fold"]

DEFAULT_LIMIT = 10
# Past every character, so that `folded < text + _LAST` holds for each title starting with text.
_LAST = "\U0010ffff"

# A title the same as the text (tier 0), then one starting with it (1), then one with words
# starting with each word typed (2); each journal at its best tier.
SEARCH = """
WITH hits (issn_l, tier) AS (
    SELECT issn_l, 0 FROM titles WHERE folded = :text
    UNION ALL
    SELECT issn_l, 1 FROM titles WHERE folded >= :text AND folded < :beyond
    UNION ALL
    SELECT issn_l, 2 FROM words WHERE words MATCH :words
)
SELECT j.doc
FROM (SELECT issn_l, MIN(tier) AS tier FROM hits GROUP BY issn_l) AS h
JOIN journals AS j USING (issn_l)
ORDER BY h.tier, j.works_count DESC, j.issn_l
LIMIT :limit
"""


class PinError(Exception):
    """The registry is missing, or does not match its pin. The message says what to do."""


class Registry:
    """Journals in a SQLite index built by `index.build_index`."""

    def __init__(self, path: Path, expect_sha256: str | None = None) -> None:
        self.path = path
        if not path.is_file():
            raise PinError(f"{path} is not built: run `dd-journals fetch`")
        built_from = self._meta("registry_sha256")
        if expect_sha256 is not None and built_from != expect_sha256:
            raise PinError(f"{path} does not match its pin: run `dd-journals fetch` to rebuild it")
        self.label = self._meta("label") or ""

    @classmethod
    def build(
        cls, journals: Iterable[Journal], path: Path, registry_sha256: str = "", label: str = ""
    ) -> Registry:
        """A registry of `journals`, indexed at `path`."""
        build_index(journals, path, registry_sha256, label)
        return cls(path, registry_sha256)

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        uri = f"{self.path.resolve().as_uri()}?mode=ro"
        try:
            with closing(sqlite3.connect(uri, uri=True)) as db:
                yield db
        except sqlite3.DatabaseError as exc:
            raise PinError(f"{self.path} cannot be read ({exc}): run `dd-journals fetch`") from None

    def _meta(self, key: str) -> str | None:
        with self._db() as db:
            row = db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return str(row[0]) if row else None

    def __len__(self) -> int:
        with self._db() as db:
            return int(db.execute("SELECT count(*) FROM journals").fetchone()[0])

    def get(self, issn: str) -> Journal | None:
        """The journal with this ISSN, print, online or linking, or None."""
        normal = normal_issn(issn)
        if normal is None:
            return None
        with self._db() as db:
            row = db.execute(
                "SELECT doc FROM issns JOIN journals USING (issn_l) WHERE issn = ?", (normal,)
            ).fetchone()
        return Journal.from_dict(json.loads(row[0])) if row else None

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
        # Folded words are letters and digits only, so each is safe in an FTS5 phrase.
        words = " AND ".join(f'"{w}"*' for w in query.split())
        params = {"text": query, "beyond": query + _LAST, "words": words, "limit": limit}
        with self._db() as db:
            rows = db.execute(SEARCH, params).fetchall()
        return [Journal.from_dict(json.loads(row[0])) for row in rows]
