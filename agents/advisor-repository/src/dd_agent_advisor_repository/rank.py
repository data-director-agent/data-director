"""Shortlisting: score each retrieved repository against the needs, by the rules in
`ranking.yaml`. Deterministic; a model never chooses which repositories are offered.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from dd_agent_advisor_repository import assess
from dd_agent_advisor_repository.classes import Answer, RepositoryNeeds
from dd_agent_advisor_repository.records import Re3dataRecord
from dd_agent_advisor_repository.retrieve import Query

RANKING = Path(__file__).with_name("ranking.yaml")

THEME = "theme"
DATA_KIND = "data kind"
AFFILIATION = "affiliation"


@cache
def config() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(RANKING.read_text(encoding="utf-8"))
    return loaded


def generalists() -> list[str]:
    return [str(rid) for rid in config()["generalists"]]


def _terms(values: list[str]) -> list[str]:
    return list(dict.fromkeys(v.strip() for v in values if v.strip()))


def queries(needs: RepositoryNeeds) -> list[Query]:
    """One query per theme and per kind of data, since re3data's search requires every word of a
    query to match, and one for the researcher's institution, whose results count only if that
    institution operates them. A term given as both a theme and a kind of data is a theme."""
    limit = int(config()["search_limit"])
    themes = _terms(needs.themes)
    kinds = [k for k in _terms(needs.data_kinds) if k not in themes]
    out = [Query(text=t, limit=limit, label=THEME) for t in themes]
    out += [Query(text=k, limit=limit, label=DATA_KIND) for k in kinds]
    if needs.affiliation is not None:
        out.append(Query(text=needs.affiliation.name, limit=limit, label=AFFILIATION))
    return out


@dataclass
class Matches:
    """Which theme and data-kind queries found each repository, by re3data id."""

    themes: dict[str, set[str]] = field(default_factory=dict)
    data_kinds: dict[str, set[str]] = field(default_factory=dict)

    def add(self, query: Query, re3data_id: str) -> None:
        if query.label == THEME:
            self.themes.setdefault(re3data_id, set()).add(query.text)
        elif query.label == DATA_KIND:
            self.data_kinds.setdefault(re3data_id, set()).add(query.text)


@dataclass(frozen=True)
class Ranked:
    record: Re3dataRecord
    score: float
    # Why it is where it is, one sentence per signal; shown on the candidate as `ranked_by`.
    reasons: tuple[str, ...]


def _quoted(terms: set[str]) -> str:
    return ", ".join(f'"{t}"' for t in sorted(terms))


def rank(
    matches: Matches, records: dict[str, Re3dataRecord], needs: RepositoryNeeds
) -> list[Ranked]:
    """Every retrieved repository that reaches the floor, best first, capped; those operated by
    the researcher's institution are added beyond the cap and take no other's place.

    A repository's discipline is judged from the themes alone. The kinds of data add a little,
    never enough on their own, since a kind of data such as "images" is found in repositories of
    every discipline. Generalists rank below any repository that matches a theme fully.
    """
    cfg = config()
    weights = cfg["weights"]
    themes = [q.text for q in queries(needs) if q.label == THEME]
    kinds = [q.text for q in queries(needs) if q.label == DATA_KIND]
    general = set(generalists())
    ranked: list[Ranked] = []
    for rid, record in records.items():
        home = assess.affiliated(record, needs.affiliation)
        if "closed" in record.data_upload_types:
            continue  # it takes no deposits, so it cannot be recommended for one
        if assess.members_only(record) and home is None:
            continue  # it takes deposits only from another institution's members
        reasons: list[str] = []
        score = 0.0
        if rid in general:
            score += weights["generalist"]
            reasons.append("A generalist repository, which takes data from any discipline.")
        elif matched := matches.themes.get(rid, set()):
            score += weights["theme"] * len(matched) / len(themes)
            noun = "theme" if len(matched) == 1 else "themes"
            reasons.append(
                f"Matches the {noun} {_quoted(matched)} ({len(matched)} of {len(themes)} given)."
            )
        if (matched := matches.data_kinds.get(rid, set())) and rid not in general:
            score += weights["data_kind"] * len(matched) / len(kinds)
            noun = "kind" if len(matched) == 1 else "kinds"
            reasons.append(f"Matches the {noun} of data {_quoted(matched)}.")
        if home is not None:
            score += weights["affiliation"]
            reasons.append(f"Operated by {home.name}, the researcher's institution.")
            if rid in general or not matches.themes.get(rid):
                reasons.append(
                    "Offered because the researcher's institution operates it, not because it "
                    "matches the dataset's discipline."
                )
        if assess.access_met(record, needs.access) is False:
            score += weights["access_unmet"]
            reasons.append(f"Does not list {needs.access} access, which the data needs.")
        if score >= cfg["confidence_floor"]:
            ranked.append(Ranked(record, round(score, 4), tuple(reasons)))
    # The cap applies only to repositories the researcher's institution does not operate, so
    # naming an institution adds its repositories and never displaces another (#441).
    cap = int(cfg["max_candidates"])
    ours = {
        r.record.re3data_id
        for r in ranked
        if assess.affiliated(r.record, needs.affiliation) is not None
    }
    theirs = [r for r in ranked if r.record.re3data_id in ours]
    others = sorted((r for r in ranked if r.record.re3data_id not in ours), key=_order)[:cap]
    return sorted(others + theirs, key=_order)


def _order(r: Ranked) -> tuple[float, bool, bool, str]:
    """Best score first; at an equal score, commercial operators and then deposit fees last."""
    return (
        -r.score,
        assess.commercial(r.record) == Answer.YES,
        assess.fee_required(r.record) == Answer.YES,
        r.record.name.casefold(),
    )
