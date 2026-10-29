"""Shortlisting: score each retrieved repository against the needs, by the rules in
`ranking.yaml`. Deterministic; a model never chooses which repositories are offered.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from dd_agent_advisor_repository import assess
from dd_agent_advisor_repository.classes import Answer, RepositoryNeeds
from dd_agent_advisor_repository.records import Re3dataRecord
from dd_agent_advisor_repository.retrieve import Hit, Query

RANKING = Path(__file__).with_name("ranking.yaml")


@cache
def config() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(RANKING.read_text(encoding="utf-8"))
    return loaded


def queries(needs: RepositoryNeeds) -> list[Query]:
    """One subject query per theme and per kind of data, since re3data's search requires every
    word of a query to match, and one for the researcher's institution, whose results count only
    if that institution operates them."""
    limit = int(config()["search_limit"])
    terms = dict.fromkeys(t.strip() for t in [*needs.themes, *needs.data_kinds] if t.strip())
    out = [Query(text=term, limit=limit, label="subject") for term in terms]
    if needs.affiliation is not None:
        out.append(Query(text=needs.affiliation.name, limit=limit, label="affiliation"))
    return out


def fit(hits: list[Hit]) -> dict[str, float]:
    """Each hit's lexical score scaled so that the query's best hit is 1."""
    top = max((h.lexical_score for h in hits), default=0.0)
    return {h.record.re3data_id: h.lexical_score / top for h in hits if top > 0}


@dataclass(frozen=True)
class Ranked:
    record: Re3dataRecord
    score: float
    reasons: tuple[str, ...]


def rank(
    subject_scores: dict[str, float],
    records: dict[str, Re3dataRecord],
    needs: RepositoryNeeds,
) -> list[Ranked]:
    """Every retrieved repository that reaches the floor, best first, capped; those operated by
    the researcher's institution are kept beyond the cap.

    `subject_scores` maps a re3data id to its best fit across the subject queries, each scaled so
    that its best hit is 1 (`fit`); records found only through the affiliation query have none.
    """
    cfg = config()
    weights = cfg["weights"]
    ranked: list[Ranked] = []
    for rid, record in records.items():
        reasons: list[str] = []
        score = 0.0
        if (fit := subject_scores.get(rid, 0.0)) > 0:
            score += weights["subject"] * fit
            reasons.append(f"subject fit {fit:.2f}")
        if assess.affiliated(record, needs.affiliation) is not None:
            score += weights["affiliation"]
            reasons.append("operated by the researcher's institution")
        if assess.access_met(record, needs.access) is False:
            score += weights["access_unmet"]
            reasons.append(f"{needs.access} access not listed")
        if "closed" in record.data_upload_types:
            continue  # it takes no deposits, so it cannot be recommended for one
        if score >= cfg["confidence_floor"]:
            ranked.append(Ranked(record, round(score, 4), tuple(reasons)))
    ranked.sort(
        key=lambda r: (
            -r.score,
            assess.commercial(r.record) == Answer.YES,
            r.record.name.casefold(),
        )
    )
    # The cap does not apply to the researcher's own institution's repositories.
    cap = int(cfg["max_candidates"])
    return ranked[:cap] + [
        r for r in ranked[cap:] if assess.affiliated(r.record, needs.affiliation) is not None
    ]
