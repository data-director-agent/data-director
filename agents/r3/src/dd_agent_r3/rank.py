"""Bespoke candidate ranking for R3.

Rules follow the standards-advisor contract: a rule whose inputs are missing returns `None`
(skipped), never `0.0`, so a record ranks the same whichever route fetched it. Thresholds
and weights live in `ranking.yaml` beside this module and are read once.

Vocabulary versus ontology (R3's one explicit distinction) is decided lexically from the
record's name and description, with `classification_derivation=lexical`. FAIRsharing's
curated subtype would be better (`registry`), but the public record route does not expose it.
TODO: read the subtype from the authenticated API when a record supplies one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from dd_agent_r3.fairsharing.records import MODEL_AND_FORMAT, TERMINOLOGY, Record
from dd_agent_r3.retrieve import Hit, Query
from dd_sdk.contract.models import DatasetProfile, Derivation, RecommendationKind

RANKING_CONFIG = Path(__file__).with_name("ranking.yaml")

# Frictionless field types that ISO 8601 covers (R3.4).
TEMPORAL_TYPES = frozenset({"date", "datetime", "time", "duration", "year", "yearmonth"})
ISO_8601_QUERY = "ISO 8601 date time format"
# A field-level date/time recommendation must be *about* dates and times by name, not merely
# score on the tokens "date", "time" or "format" somewhere in a long description. Without this
# filter BM25 happily proposes hypermedia and cruise-report standards for a date column.
_TEMPORAL_NAME = re.compile(r"8601|\bdate[- ]?time\b|\bdate and time\b|\btimestamp", re.IGNORECASE)


def is_temporal_standard(record: Record) -> bool:
    return bool(_TEMPORAL_NAME.search(f"{record.name} {record.abbreviation or ''}"))


_ONTOLOGY_WORDS = re.compile(r"\bontolog(y|ies)\b|\bOBO\b|\bOWL\b", re.IGNORECASE)
_VOCABULARY_WORDS = re.compile(
    r"\b(controlled vocabulary|vocabulary|thesaurus|thesauri|taxonomy|code list|"
    r"classification|SKOS)\b",
    re.IGNORECASE,
)


@cache
def config() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(RANKING_CONFIG.read_text(encoding="utf-8"))
    return data


@dataclass(frozen=True)
class Ranked:
    hit: Hit
    kind: RecommendationKind
    target: str
    score: float
    classification_derivation: Derivation | None
    query: Query
    reasons: tuple[str, ...]


# --- Query construction -----------------------------------------------------------------------


def build_queries(profile: DatasetProfile) -> list[Query]:
    """What to ask the registry, from the profile alone. Empty when the profile has nothing to
    search on, which the agent turns into abstained(insufficient_input)."""
    cfg = config()
    subject_terms = [*profile.themes, *profile.keywords]
    title_tokens = (profile.title or "").split()[: cfg["title_tokens"]]
    subject_text = " ".join([*subject_terms, *title_tokens]).strip()
    queries: list[Query] = []
    if subject_text:
        queries.append(
            Query(subject_text, record_type=TERMINOLOGY, limit=cfg["limit"], label="terminologies")
        )
        queries.append(
            Query(subject_text, record_type=MODEL_AND_FORMAT, limit=cfg["limit"], label="formats")
        )
    for media_type in profile.media_types:
        label = media_type.split("/")[-1].replace("+", " ")
        queries.append(
            Query(
                label,
                record_type=MODEL_AND_FORMAT,
                limit=cfg["limit"],
                label=f"format:{media_type}",
            )
        )
    temporal = [f for f in profile.fields if (f.field_type or "").lower() in TEMPORAL_TYPES]
    if temporal:
        queries.append(
            Query(
                ISO_8601_QUERY, record_type=MODEL_AND_FORMAT, limit=3, label="field-format:temporal"
            )
        )
    return queries


# --- Rules (None = skipped) -------------------------------------------------------------------


def rule_lexical(hit: Hit, max_score: float) -> float | None:
    if max_score <= 0:
        return None
    return hit.lexical_score / max_score


def rule_subject_overlap(record: Record, profile: DatasetProfile) -> float | None:
    if not record.subjects and not record.domains:
        return None
    wanted = {t.lower() for t in [*profile.themes, *profile.keywords]}
    if not wanted:
        return None
    have = {s.lower() for s in [*record.subjects, *record.domains]}
    overlap = sum(1 for w in wanted if any(w in h or h in w for h in have))
    return overlap / len(wanted)


def rule_status(record: Record) -> float | None:
    if record.status is None:
        return None
    cfg = config()["status_weights"]
    weight: float | None = cfg.get(record.status)
    return weight


# --- Classification ---------------------------------------------------------------------------


def classify_terminology(record: Record) -> tuple[RecommendationKind, Derivation]:
    text = f"{record.name} {record.description or ''}"
    if _ONTOLOGY_WORDS.search(text):
        return RecommendationKind.ONTOLOGY, Derivation.LEXICAL
    if _VOCABULARY_WORDS.search(text):
        return RecommendationKind.CONTROLLED_VOCABULARY, Derivation.LEXICAL
    return RecommendationKind.TERMINOLOGY_UNCLASSIFIED, Derivation.LEXICAL


def kind_for(query: Query, record: Record) -> tuple[RecommendationKind, Derivation | None, str]:
    if query.label.startswith("field-format"):
        return RecommendationKind.FIELD_FORMAT, None, "field"
    if record.record_type == TERMINOLOGY:
        kind, derivation = classify_terminology(record)
        return kind, derivation, "dataset"
    return RecommendationKind.DATA_FORMAT, None, "dataset"


# --- Ranking ----------------------------------------------------------------------------------


def rank(query: Query, hits: list[Hit], profile: DatasetProfile) -> list[Ranked]:
    cfg = config()
    weights = cfg["weights"]
    max_lex = max((h.lexical_score for h in hits), default=0.0)
    ranked: list[Ranked] = []
    for hit in hits:
        record = hit.record
        if record.status == "deprecated":
            continue  # excluded outright, not merely penalised
        if query.label.startswith("field-format") and not is_temporal_standard(record):
            continue  # see is_temporal_standard
        parts: list[tuple[str, float, float]] = []  # (name, weight, value)
        lex = rule_lexical(hit, max_lex)
        if lex is not None:
            parts.append(("lexical", weights["lexical"], lex))
        overlap = rule_subject_overlap(record, profile)
        if overlap is not None:
            parts.append(("subject_overlap", weights["subject_overlap"], overlap))
        status = rule_status(record)
        if status is not None:
            parts.append(("status", weights["status"], status))
        if not parts:
            continue
        total_w = sum(w for _, w, _ in parts)
        score = sum(w * v for _, w, v in parts) / total_w
        kind, derivation, _ = kind_for(query, record)
        reasons = tuple(f"{n}={v:.2f}" for n, _, v in parts)
        if record.status == "in_development":
            reasons = (*reasons, "in_development: emerging standard (R3.5)")
        ranked.append(
            Ranked(
                hit=hit,
                kind=kind,
                target="dataset",
                score=round(score, 4),
                classification_derivation=derivation,
                query=query,
                reasons=reasons,
            )
        )
    ranked.sort(key=lambda r: (-r.score, r.hit.record.fairsharing_id))
    return ranked


def qualifying(ranked: list[Ranked]) -> list[Ranked]:
    floor = float(config()["confidence_floor"])
    return [r for r in ranked if r.score >= floor]
