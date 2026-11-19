"""Which repositories a run offers, and how its outcome reads (`agent.RepositoryAgent.run`).

A mandated repository is described instead of a shortlist; one the researcher only asked about
is described beside it, never marked mandated (#1167); so is one the data management plan names
in a commitment the researcher confirmed (#1233).
"""

from __future__ import annotations

from typing import Protocol

from dd_agent_advisor_repository import given, rank
from dd_agent_advisor_repository.classes import (
    CandidateBasis,
    RepositoryCandidate,
    RepositoryNeeds,
)
from dd_agent_advisor_repository.records import Re3dataRecord
from dd_agent_advisor_repository.retrieve import Repositories
from dd_sdk.agent import AgentResult, abstain
from dd_sdk.contract.models import ReasonCode


class Retrieved(Protocol):
    """What a run retrieved, as far as the outcome reports it."""

    ambiguous: dict[str, list[str]]
    aliased: dict[str, str]

    def summary(self) -> str: ...


def ambiguous(names: dict[str, list[str]]) -> str:
    """A sentence for each name given that several re3data records bear, or nothing."""
    return "".join(
        f" {name!r} names several re3data records ({', '.join(ids)}); give the identifier."
        for name, ids in names.items()
    )


# A candidate chosen: its record, why it is offered, its score and the reasons it was ranked by.
Chosen = tuple[Re3dataRecord, CandidateBasis, float | None, tuple[str, ...]]


class Named:
    """The records of the repositories named in the needs, mandated, in the data management
    plan or asked about, and the names for which no single record was found."""

    def __init__(self) -> None:
        self.mandated: list[Re3dataRecord] = []
        self.in_plan: list[Re3dataRecord] = []
        self.asked_about: list[Re3dataRecord] = []
        self.not_found: list[str] = []


def choose(named: Named, ranked: list[rank.Ranked], only_chosen: str | None = None) -> list[Chosen]:
    """The candidates, each once: the mandated repositories, then those the data management
    plan names, then those the researcher asked about, then the rest of the shortlist. A
    repository in the plan or asked about that the shortlist also ranks keeps its score and
    reasons, so the researcher can compare it, but stays marked as the plan's or asked about
    rather than recommended. `only_chosen` is the identifier of a repository
    described only because the researcher chose it (`given.basis`)."""
    by_id = {r.record.re3data_id: r for r in ranked}
    chosen: list[Chosen] = [(r, given.basis(r, only_chosen), None, ()) for r in named.mandated]
    described = [(r, CandidateBasis.IN_PLAN) for r in named.in_plan]
    described += [(r, CandidateBasis.ASKED_ABOUT) for r in named.asked_about]
    for record, basis in described:
        hit = by_id.pop(record.re3data_id, None)
        score, reasons = (hit.score, hit.reasons) if hit else (None, ())
        chosen.append((record, basis, score, reasons))
    for record in named.mandated:
        by_id.pop(record.re3data_id, None)
    chosen += [(r.record, CandidateBasis.RECOMMENDED, r.score, r.reasons) for r in by_id.values()]
    return chosen


def abstention(
    named: Named, got: Retrieved, hits: int, shortlisted: list[str], source: Repositories
) -> AgentResult:
    """Nothing to offer: no repository named was found, and the shortlist, if one was sought,
    retrieved nothing or nothing that qualified."""
    missing = (
        f"No re3data record was found for {', '.join(named.not_found)} ({got.summary()})."
        f"{ambiguous(got.ambiguous)} Check the names, or give the re3data identifiers. "
        if named.not_found
        else ""
    )
    if not shortlisted:
        return abstain(ReasonCode.NO_CANDIDATES_RETRIEVED, missing + source.credit())
    if not hits:
        return abstain(
            ReasonCode.NO_CANDIDATES_RETRIEVED,
            f"re3data ({got.summary()}) returned nothing for: "
            + "; ".join(shortlisted)
            + ". "
            + missing
            + source.credit(),
        )
    return abstain(
        ReasonCode.NO_QUALIFYING_RESOURCE,
        f"{hits} repositories were retrieved ({got.summary()}) but none reached the floor of "
        f"{rank.config()['confidence_floor']} or accepts deposits. Searched: "
        + "; ".join(shortlisted)
        + ". "
        + missing
        + source.credit(),
    )


_BASES = (
    (CandidateBasis.MANDATED, "mandated, described"),
    (CandidateBasis.CHOSEN, "chosen by the researcher, described"),
    (CandidateBasis.IN_PLAN, "named by the researcher's data management plan, described"),
    (CandidateBasis.ASKED_ABOUT, "asked about by the researcher, described"),
    (CandidateBasis.RECOMMENDED, "recommended"),
)


def statement(
    needs: RepositoryNeeds,
    candidates: list[RepositoryCandidate],
    evidence: int,
    got: Retrieved,
    named: Named,
    ranked: list[rank.Ranked],
    shortlisted: list[str],
) -> str:
    """The outcome's statement, up to the closing reminder that the researcher chooses."""
    counts = [
        f"{label}: {n}"
        for basis, label in _BASES
        if (n := sum(c.basis == basis for c in candidates))
    ]
    statement = (
        f"Repositories {'; '.join(counts)}, grounded in {evidence} registry record(s) "
        f"({got.summary()})."
    )
    short = [c for c in candidates if c.basis == CandidateBasis.MANDATED and c.misses]
    if short:
        statement += (
            f" Mandated repositories that do not meet, or do not state, every need: "
            f"{len(short)}; see each candidate's misses."
        )
    if named.in_plan:
        statement += (
            " The repositories the data management plan names are described because a sharing "
            "commitment the researcher confirmed names them; a plan's choice is not a mandate."
        )
    if named.asked_about:
        statement += (
            " The repositories asked about are described because the researcher named them; "
            "no policy given requires them."
        )
    statement += "".join(
        f" {name!r} is not a name re3data gives any record; it was read as {rid} from the "
        "agent's list of other names for repositories."
        for name, rid in got.aliased.items()
    )
    if named.not_found:
        statement += (
            f" No record found for: {', '.join(named.not_found)}.{ambiguous(got.ambiguous)}"
        )
    themes = [q.text for q in rank.queries(needs) if q.label == rank.THEME]
    on_theme = any(r.on_theme and r.fit == rank.DISCIPLINE for r in ranked)
    if shortlisted and not ranked:
        statement += (
            " No repository qualified for the shortlist. Searched: " + "; ".join(shortlisted) + "."
        )
    elif ranked and themes and not on_theme:
        statement += (
            " No discipline-specific repository matched the themes ("
            + "; ".join(themes)
            + "), so only generalist and institutional repositories are offered. The broad "
            "field of study, such as environmental science, may find repositories of the "
            "discipline that a narrow topic does not."
        )
    if not needs.mandated and not shortlisted:
        statement += " No theme, kind of data or affiliation was given, so no shortlist was made."
    if not needs.mandated:
        statement += (
            " No mandated repository was given; a funder, journal or institution may still "
            "require one, so check their policies before choosing a repository."
        )
    return statement
