"""Shortlisting: score each retrieved repository against the needs, by the rules in
`ranking.yaml`. Deterministic; a model never chooses which repositories are offered.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from dd_agent_advisor_repository import assess, dfg
from dd_agent_advisor_repository.classes import Answer, RepositoryNeeds
from dd_agent_advisor_repository.records import Re3dataRecord
from dd_sdk.registry import Hit, Query

RANKING = Path(__file__).with_name("ranking.yaml")

THEME = "theme"
DATA_KIND = "data kind"
AFFILIATION = "affiliation"

# Kinds of fit, ordered by `ranking.yaml`'s `order`.
DISCIPLINE = "discipline"
INSTITUTIONAL = "institutional"
GENERALIST = "generalist"


# The questions `ranking.yaml`'s `tie_break` may ask of a record.
TIE_BREAKS: dict[str, Callable[[Re3dataRecord], Answer]] = {
    "commercial": assess.commercial,
    "fee_required": assess.fee_required,
    "assigns_pids": assess.assigns_pids,
}


@cache
def config() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(RANKING.read_text(encoding="utf-8"))
    check(loaded)
    return loaded


def check(cfg: dict[str, Any]) -> None:
    """Raise ValueError if the reserved places or the tie-break cannot be applied as written."""
    reserve = cfg.get("reserve") or {}
    if unknown := set(reserve) - set(cfg["order"]):
        raise ValueError(f"reserve names kinds of fit not in order: {sorted(unknown)}")
    if sum(int(n) for n in reserve.values()) > int(cfg["max_candidates"]):
        raise ValueError("reserve keeps more places than max_candidates allows")
    for question, preferred in (cfg.get("tie_break") or {}).items():
        if question not in TIE_BREAKS:
            raise ValueError(f"tie_break asks an unknown question: {question}")
        if Answer(preferred) == Answer.UNSTATED:
            raise ValueError(f"tie_break must prefer yes or no for {question}")


def generalists() -> list[str]:
    """The generalist repositories, in `ranking.yaml`'s order of preference."""
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

    def add(self, query: Query, hits: list[Hit[Re3dataRecord]]) -> None:
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
            into.setdefault(hit.record.identifier, {}).setdefault(
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
    unique = {r.identifier: r for r in records}.values()
    return sorted(
        unique,
        key=lambda r: (-matches.text_grade(r.identifier, theme), len(r.subjects), r.identifier),
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
    # The part of the score that an inferred country added: left out when the cap is applied,
    # so that naming an institution reorders the shortlist and removes nothing (#441).
    nudge: float = 0.0


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
    rid = record.identifier
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


@dataclass(frozen=True)
class _Ranking:
    """What ranking each repository in one run shares (`rank`): the needs, the matches, the
    themes and kinds of data asked for, the generalists, and the researcher's country."""

    matches: Matches
    needs: RepositoryNeeds
    themes: list[str]
    kinds: list[str]
    general: set[str]
    # The researcher's country as given, else as re3data records their institution's.
    country: str | None
    whose: str
    inferred: bool


def _relevance(rid: str, record: Re3dataRecord, run: _Ranking) -> tuple[float, list[str], bool]:
    """A repository's score from the themes and the kinds of data, why, and whether it matches
    a theme."""
    weights = config()["weights"]
    reasons: list[str] = []
    score = 0.0
    on_theme = False
    if rid in run.general:
        score += weights["generalist"]
        reasons.append("A generalist repository, which takes data from any discipline.")
    elif run.themes:
        graded = {t: _theme(t, record, run.matches) for t in run.themes}
        matched = {t for t, (grade, _) in graded.items() if grade > 0}
        if matched:
            on_theme = True
            score += weights["theme"] * sum(g for g, _ in graded.values()) / len(run.themes)
            noun = "theme" if len(matched) == 1 else "themes"
            reasons.append(
                f"Matches the {noun} {_quoted(matched)} ({len(matched)} of {len(run.themes)} "
                "given)."
            )
            for theme in sorted(matched):
                reasons.extend(graded[theme][1])
    found = run.matches.data_kinds.get(rid, {})
    if (matched := set(found)) and rid not in run.general:
        score += weights["data_kind"] * sum(m.grade for m in found.values()) / len(run.kinds)
        noun = "kind" if len(matched) == 1 else "kinds"
        reasons.append(f"Matches the {noun} of data {_quoted(matched)}.")
    return score, reasons, on_theme


def _ranked(rid: str, record: Re3dataRecord, run: _Ranking) -> Ranked | None:
    """One repository as ranked, or None when it cannot be offered."""
    cfg = config()
    weights = cfg["weights"]
    needs = run.needs
    home = assess.affiliated(record, needs.affiliation)
    if "closed" in record.data_upload_types:
        return None  # it takes no deposits, so it cannot be recommended for one
    if assess.members_only(record) and home is None:
        return None  # it takes deposits only from another institution's members
    score, reasons, on_theme = _relevance(rid, record, run)
    access_unmet = assess.access_met(record, needs.access) is False
    if access_unmet:
        score += weights["access_unmet"]
    score = round(score, 4)
    nudge = 0.0
    if score >= cfg["confidence_floor"]:
        fit = GENERALIST if rid in run.general else DISCIPLINE
        # After the floor, so the country reorders matches and never makes one (#741).
        if (local := assess.in_country(record, run.country)) is not None:
            score = round(score + weights["country"], 4)
            nudge = weights["country"] if run.inferred else 0.0
            reasons.append(f"Operated in {run.country}, {run.whose}, by {local.name}.")
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
        return None
    if access_unmet:
        reasons.append(f"Does not list {needs.access} access, which the data needs.")
    return Ranked(record, score, tuple(reasons), fit, on_theme, nudge)


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
    fallback, in case no more specific destination suits the data (#441). The researcher's
    country, as given or else as re3data records the institution's, adds a little to a repository
    that already matches, so that one operated there ranks above an equal or slightly closer
    match elsewhere (#741).
    """
    # The researcher's country as given, else as re3data records their institution's.
    country, whose, inferred = needs.country, "the researcher's country", False
    if country is None:
        country = assess.home_country(records.values(), needs.affiliation)
        whose, inferred = "the country of the researcher's institution", True
    run = _Ranking(
        matches=matches,
        needs=needs,
        themes=[q.text for q in queries(needs) if q.label == THEME],
        kinds=[q.text for q in queries(needs) if q.label == DATA_KIND],
        general=set(generalists()),
        country=country,
        whose=whose,
        inferred=inferred,
    )
    ranked = [
        found for rid, record in records.items() if (found := _ranked(rid, record, run)) is not None
    ]
    # The cap applies only to repositories the researcher's institution does not operate, so
    # naming an institution adds its repositories and never displaces another (#441).
    ours = [r for r in ranked if assess.affiliated(r.record, needs.affiliation) is not None]
    others = _cap(
        sorted(
            (r for r in ranked if r not in ours),
            key=lambda r: _order(replace(r, score=r.score - r.nudge)),
        )
    )
    return _say_ties(sorted(others + ours, key=_order))


def _cap(ranked: list[Ranked]) -> list[Ranked]:
    """The first `max_candidates` of `ranked`, in its order, except that `reserve`'s places for
    each kind of fit are kept for that kind when it has repositories to fill them, so that
    matches of one kind never crowd out every match of another (#1169). A repository that is
    listed only because of its reserved place says so."""
    cfg = config()
    cap = int(cfg["max_candidates"])
    reserve = {str(k): int(n) for k, n in (cfg.get("reserve") or {}).items()}
    kept: set[int] = set()
    for fit, places in reserve.items():
        kept.update([i for i, r in enumerate(ranked) if r.fit == fit][:places])
    kept.update([i for i in range(len(ranked)) if i not in kept][: cap - len(kept)])
    out: list[Ranked] = []
    for i in sorted(kept):
        r = ranked[i]
        if i >= cap:  # listed only because of its kind's reserved place
            places = reserve[r.fit]
            kept_for = "a place" if places == 1 else f"{places} places"
            why = (
                f"Listed in {kept_for} of {cap} that the shortlist keeps for a {r.fit} "
                "repository, so that there is an option however many repositories match the "
                "discipline."
            )
            r = replace(r, reasons=(*r.reasons, why))
        out.append(r)
    return out


def _say_ties(ranked: list[Ranked]) -> list[Ranked]:
    """Add a reason to each repository that shares its kind of fit and score with others on the
    shortlist, so the order among them is not read as a preference (#741)."""
    groups: dict[tuple[str, float], int] = {}
    for r in ranked:
        groups[(r.fit, r.score)] = groups.get((r.fit, r.score), 0) + 1
    out: list[Ranked] = []
    for r in ranked:
        others = groups[(r.fit, r.score)] - 1
        if others:
            noun = "other" if others == 1 else "others"
            why = (
                "they are listed by the stated order of preference among generalists: free to "
                "deposit, not-for-profit, assigning DOIs and publicly funded first."
                if r.fit == GENERALIST
                else "their order is not a preference."
            )
            tied = f"Ranked equal with {others} {noun} on this shortlist; {why}"
            r = replace(r, reasons=(*r.reasons, tied))
        out.append(r)
    return out


def _order(r: Ranked) -> tuple[int, float, tuple[int, ...], int, str]:
    """By kind of fit, then best score; at an equal score, by `tie_break` (the preferred answer
    first, unstated next, the other last), then by the generalists' order of preference, and
    last by name, so that the order is the same on every run."""
    cfg = config()
    tie = tuple(
        _preference(TIE_BREAKS[question](r.record), Answer(preferred))
        for question, preferred in (cfg.get("tie_break") or {}).items()
    )
    general = generalists()
    rid = r.record.identifier
    return (
        [str(f) for f in cfg["order"]].index(r.fit),
        -r.score,
        tie,
        general.index(rid) if rid in general else len(general),
        r.record.name.casefold(),
    )


def _preference(answer: Answer, preferred: Answer) -> int:
    if answer == Answer.UNSTATED:
        return 1
    return 0 if answer == preferred else 2
