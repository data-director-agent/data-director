"""Shortlisting: score each retrieved repository against the needs, by the rules in
`ranking.yaml`. Deterministic; a model never chooses which repositories are offered.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from dd_agent_advisor_repository import assess, dfg
from dd_agent_advisor_repository.classes import Answer, RepositoryNeeds
from dd_agent_advisor_repository.records import Re3dataRecord
from dd_agent_advisor_repository.retrieve import Hit, Query

RANKING = Path(__file__).with_name("ranking.yaml")

THEME = "theme"
DATA_KIND = "data kind"
AFFILIATION = "affiliation"

# Kinds of fit, ordered by `ranking.yaml`'s `order`.
DISCIPLINE = "discipline"
INSTITUTIONAL = "institutional"
GENERALIST = "generalist"


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
    institution operates them. A term given as both a theme and a kind of data is a theme.

    A theme or kind of data asks for up to `text_hits` hits, so that each is graded against the
    best; only the first `search_limit` are retrieved on the strength of their text."""
    cfg = config()
    graded, limit = int(cfg["text_hits"]), int(cfg["search_limit"])
    themes = _terms(needs.themes)
    kinds = [k for k in _terms(needs.data_kinds) if k not in themes]
    out = [Query(text=t, limit=graded, label=THEME) for t in themes]
    out += [Query(text=k, limit=graded, label=DATA_KIND) for k in kinds]
    if needs.affiliation is not None:
        out.append(Query(text=needs.affiliation.name, limit=limit, label=AFFILIATION))
    return out


@dataclass(frozen=True)
class TextMatch:
    """A registry search hit: its place among a query's hits, and its grade, from
    `theme_match.text_base` for the weakest hit to 1 for the best, by BM25 score."""

    grade: float
    place: int
    of: int


@dataclass
class Matches:
    """What each theme and kind of data found, by re3data id, and the DFG subjects each theme
    names."""

    themes: dict[str, dict[str, TextMatch]] = field(default_factory=dict)
    data_kinds: dict[str, dict[str, TextMatch]] = field(default_factory=dict)
    # Each theme's DFG subject codes (`dfg.resolve`); empty when it names none.
    subjects: dict[str, list[str]] = field(default_factory=dict)
    # The name of each DFG code, for `ranked_by`.
    names: dict[str, str] = field(default_factory=dict)

    def add(self, query: Query, hits: list[Hit]) -> None:
        """Grade a query's hits by BM25 score relative to the best of them."""
        if query.label == THEME:
            into = self.themes
        elif query.label == DATA_KIND:
            into = self.data_kinds
        else:
            return
        base = float(config()["theme_match"]["text_base"])
        best = max((h.lexical_score for h in hits), default=0.0)
        for place, hit in enumerate(hits, start=1):
            share = hit.lexical_score / best if best > 0 else 1.0
            grade = round(base + (1 - base) * share, 4)
            into.setdefault(hit.record.re3data_id, {}).setdefault(
                query.text, TextMatch(grade, place, len(hits))
            )

    def text_grade(self, rid: str, theme: str) -> float:
        found = self.themes.get(rid, {}).get(theme)
        return found.grade if found else 0.0


def resolve(themes: list[str], names: dict[str, str], matches: Matches) -> None:
    """Note in `matches` the DFG subjects each theme names."""
    for theme in themes:
        matches.subjects[theme] = dfg.resolve(theme, names)
        matches.names.update({c: names[c] for c in matches.subjects[theme]})
        for code in matches.subjects[theme]:
            matches.names.update({a: names[a] for a in dfg.ancestors(code) if a in names})


def by_subject(theme: str, records: list[Re3dataRecord], matches: Matches) -> list[Re3dataRecord]:
    """The repositories filed under a theme's subjects that are worth retrieving: those that
    also match the theme's text first, then the most specialised (filed under fewest subjects),
    up to `search_limit`."""
    limit = int(config()["search_limit"])
    unique = {r.re3data_id: r for r in records}.values()
    return sorted(
        unique,
        key=lambda r: (-matches.text_grade(r.re3data_id, theme), len(r.subjects), r.re3data_id),
    )[:limit]


@dataclass(frozen=True)
class Ranked:
    record: Re3dataRecord
    score: float
    # Why it is where it is, one sentence per signal; shown on the candidate as `ranked_by`.
    reasons: tuple[str, ...]
    # The kind of fit, one of `ranking.yaml`'s `order`, which ranks before the score.
    fit: str = DISCIPLINE
    # Whether it matches any theme, by its text or its DFG subjects.
    on_theme: bool = False


def _quoted(terms: set[str]) -> str:
    return ", ".join(f'"{t}"' for t in sorted(terms))


def _subject(code: str, matches: Matches) -> str:
    return f'"{matches.names.get(code, code)}" ({code})'


def _theme(theme: str, record: Re3dataRecord, matches: Matches) -> tuple[float, list[str]]:
    """How well a repository matches one theme, from 0 to 1, and why.

    Where the theme names a DFG subject and the record lists subjects, `subject_share` of the
    grade is how near the repository is filed to that subject, and the rest is its text match.
    Otherwise the text match is the whole grade: a rule whose input is missing does not count
    against the repository."""
    rid = record.re3data_id
    cfg = config()["theme_match"]
    reasons: list[str] = []
    text = matches.themes.get(rid, {}).get(theme)
    if text is not None:
        reasons.append(
            f'Ranks {text.place} of {text.of} in a text search of re3data for "{theme}".'
        )
    text_grade = text.grade if text else 0.0
    targets = matches.subjects.get(theme, [])
    listed = dfg.codes(record.subjects)
    if not targets or not listed:
        return text_grade, reasons
    near = dfg.nearest(targets, listed)
    subject_grade = 0.0
    if near is not None:
        subject_grade = float(cfg["subject_grades"][near.steps])
        if near.steps == 0:
            reasons.insert(
                0,
                f"Filed under the DFG subject {_subject(near.target, matches)}, which "
                f'"{theme}" names.',
            )
        else:
            above = "just above" if near.steps == 1 else f"{near.steps} levels above"
            reasons.insert(
                0,
                f"Filed under the DFG subject {_subject(near.listed, matches)}, {above} "
                f'{_subject(near.target, matches)}, which "{theme}" names.',
            )
    share = float(cfg["subject_share"])
    return share * subject_grade + (1 - share) * text_grade, reasons


def rank(
    matches: Matches, records: dict[str, Re3dataRecord], needs: RepositoryNeeds
) -> list[Ranked]:
    """Every retrieved repository that reaches the floor, capped, and the researcher's
    institution's repositories as a fallback beyond the cap: ordered by kind of fit (by default
    the dataset's discipline, then the institution's, then generalist), and within a kind best
    score first.

    A repository's discipline is judged from the themes alone, by its text (BM25, relative to
    the best hit) and by where re3data files it in the DFG classification. The kinds of data add
    a little, never enough on their own, since a kind of data such as "images" is found in
    repositories of every discipline. Affiliation adds no score: an institution's repository
    that matches the discipline is ranked as any other, and one that does not is offered as the
    fallback, in case no more specific destination suits the data (#441).
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
        on_theme = False
        if rid in general:
            score += weights["generalist"]
            reasons.append("A generalist repository, which takes data from any discipline.")
        elif themes:
            graded = {t: _theme(t, record, matches) for t in themes}
            matched = {t for t, (grade, _) in graded.items() if grade > 0}
            if matched:
                on_theme = True
                score += weights["theme"] * sum(g for g, _ in graded.values()) / len(themes)
                noun = "theme" if len(matched) == 1 else "themes"
                reasons.append(
                    f"Matches the {noun} {_quoted(matched)} ({len(matched)} of {len(themes)} "
                    "given)."
                )
                for theme in sorted(matched):
                    reasons.extend(graded[theme][1])
        found = matches.data_kinds.get(rid, {})
        if (matched := set(found)) and rid not in general:
            score += weights["data_kind"] * sum(m.grade for m in found.values()) / len(kinds)
            noun = "kind" if len(matched) == 1 else "kinds"
            reasons.append(f"Matches the {noun} of data {_quoted(matched)}.")
        access_unmet = assess.access_met(record, needs.access) is False
        if access_unmet:
            score += weights["access_unmet"]
        score = round(score, 4)
        if score >= cfg["confidence_floor"]:
            fit = GENERALIST if rid in general else DISCIPLINE
            if home is not None:
                reasons.append(f"Operated by {home.name}, the researcher's institution.")
        elif home is not None and not access_unmet:
            fit = INSTITUTIONAL
            reasons.append(
                f"Operated by {home.name}, the researcher's institution, and offered as a "
                "fallback: a repository of the dataset's discipline, or one a funder, journal or "
                "project requires, may suit the data better."
            )
        else:
            continue
        if access_unmet:
            reasons.append(f"Does not list {needs.access} access, which the data needs.")
        ranked.append(Ranked(record, score, tuple(reasons), fit, on_theme))
    # The cap applies only to repositories the researcher's institution does not operate, so
    # naming an institution adds its repositories and never displaces another (#441).
    cap = int(cfg["max_candidates"])
    ours = [r for r in ranked if assess.affiliated(r.record, needs.affiliation) is not None]
    others = sorted((r for r in ranked if r not in ours), key=_order)[:cap]
    return sorted(others + ours, key=_order)


def _order(r: Ranked) -> tuple[int, float, bool, bool, str]:
    """By kind of fit, then best score; at an equal score, commercial operators and then
    deposit fees last."""
    return (
        [str(f) for f in config()["order"]].index(r.fit),
        -r.score,
        assess.commercial(r.record) == Answer.YES,
        assess.fee_required(r.record) == Answer.YES,
        r.record.name.casefold(),
    )
