"""Build `journals.jsonl` from the gzipped JSON Lines parts of an OpenAlex Sources snapshot.

Only journals with an ISSN-L are kept, projected to `Journal`. OpenAlex sometimes has two source
records for one ISSN-L; they become one journal, described by the record with more works (then
the lower OpenAlex identifier), with the ISSNs of both. Lines are written with sorted keys, sorted
by ISSN-L, so the same parts always build the same bytes.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterable, Iterator
from dataclasses import replace
from pathlib import Path

from dd_journals.records import Journal, from_openalex


def journals_in(part: Path) -> Iterator[Journal]:
    """Each journal with an ISSN-L in one gzipped part of the snapshot."""
    with gzip.open(part, "rt", encoding="utf-8") as lines:
        for line in lines:
            if line.strip() and (journal := from_openalex(json.loads(line))) is not None:
                yield journal


def _merge(kept: Journal, other: Journal) -> Journal:
    first, second = sorted((kept, other), key=lambda j: (-j.works_count, j.openalex_id))
    return replace(first, issns=tuple(sorted(set(first.issns) | set(second.issns))))


def merged(journals: Iterable[Journal]) -> list[Journal]:
    """One journal per ISSN-L, sorted by ISSN-L."""
    by_issn_l: dict[str, Journal] = {}
    for journal in journals:
        kept = by_issn_l.get(journal.issn_l)
        by_issn_l[journal.issn_l] = journal if kept is None else _merge(kept, journal)
    return [by_issn_l[k] for k in sorted(by_issn_l)]


def serialise(journals: Iterable[Journal]) -> bytes:
    """The journals as `journals.jsonl`: one sorted-key JSON object per line."""
    lines = (json.dumps(j.as_dict(), ensure_ascii=False, sort_keys=True) + "\n" for j in journals)
    return "".join(lines).encode("utf-8")


def build(parts: Iterable[Path]) -> tuple[bytes, list[Journal]]:
    """`journals.jsonl` built from the snapshot's parts, and the journals it holds."""
    journals = merged(j for part in parts for j in journals_in(part))
    return serialise(journals), journals


def parse(data: bytes) -> list[Journal]:
    """The journals in `journals.jsonl`."""
    return [Journal.from_dict(json.loads(line)) for line in data.decode().splitlines() if line]
