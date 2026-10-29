"""What a policy record says about each obligation, and where matched policies differ.

Every obligation is read from a curated field of the record, or from its relations, by a fixed
rule; none is written by a model. Where the record is silent the strength is `unstated`, and the
value the curators recorded, such as "no", is kept beside it. A strength of `unstated` is not
evidence that the policy asks nothing.

FAIRsharing's policy records have no field for embargoes or for when data must be shared, and
the API returns no relations from a policy to the databases and standards it names, so those
obligations are `unstated` unless a relation is present. TODO(#302, #331)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from dd_agent_policy.classes import (
    Obligation,
    ObligationKind,
    PolicyContext,
    RepositoryRef,
    Strength,
)
from dd_agent_policy.records import PolicyRecord

# A curated value, as FAIRsharing records it, and the strength it states.
STRENGTHS = {
    "required": Strength.REQUIRED,
    "yes": Strength.REQUIRED,
    "suggested": Strength.RECOMMENDED,
    "recommended": Strength.RECOMMENDED,
}
# The clause field each obligation is read from: (clause, value key).
FIELDS = {
    ObligationKind.DEPOSIT: ("sharing_data", "mandated_data_sharing"),
    ObligationKind.DATA_AVAILABILITY_STATEMENT: ("data_availability_statement", "required"),
    ObligationKind.LICENCE: ("licences_for_outputs", "required"),
}
# Relations to records in these FAIRsharing registries state repository and standard obligations.
RELATED = {
    ObligationKind.REPOSITORY: "database",
    ObligationKind.STANDARD: "standard",
}
RELATION_STRENGTHS = {"requires": Strength.REQUIRED, "recommends": Strength.RECOMMENDED}
SUBJECT_AGNOSTIC = "subject agnostic"


def _from_field(record: PolicyRecord, kind: ObligationKind) -> Obligation:
    clause, key = FIELDS[kind]
    value = record.clause(clause).values.get(key)
    strength = STRENGTHS.get((value or "").casefold(), Strength.UNSTATED)
    return Obligation(kind=kind, strength=strength, recorded_as=value)


def _from_relations(record: PolicyRecord, kind: ObligationKind) -> Obligation:
    registry = RELATED[kind]
    found = {
        RELATION_STRENGTHS[r.relation]
        for r in record.relations
        if (r.registry or "").casefold() == registry and r.relation in RELATION_STRENGTHS
    }
    for strength in (Strength.REQUIRED, Strength.RECOMMENDED):
        if strength in found:
            return Obligation(kind=kind, strength=strength)
    return Obligation(kind=kind, strength=Strength.UNSTATED)


def obligations(record: PolicyRecord) -> list[Obligation]:
    """One obligation per kind, in the order of `ObligationKind`."""
    out: list[Obligation] = []
    for kind in ObligationKind:
        if kind in FIELDS:
            out.append(_from_field(record, kind))
        elif kind in RELATED:
            out.append(_from_relations(record, kind))
        else:
            out.append(Obligation(kind=kind, strength=Strength.UNSTATED))
    return out


def mandated(record: PolicyRecord) -> list[RepositoryRef]:
    """The repositories the policy requires, as FAIRsharing relates them."""
    return [
        RepositoryRef(name=r.name)
        for r in record.relations
        if (r.registry or "").casefold() == "database" and r.relation == "requires"
    ]


def _year(publication_date: str | None) -> int | None:
    return int(publication_date[:4]) if publication_date else None


def notes(record: PolicyRecord, context: PolicyContext) -> list[str]:
    out: list[str] = []
    subjects = [s.casefold() for s in record.subjects]
    disciplines = [d.casefold() for d in context.disciplines]
    if (
        subjects
        and disciplines
        and SUBJECT_AGNOSTIC not in subjects
        and not any(d in s or s in d for d in disciplines for s in subjects)
    ):
        out.append(
            f"FAIRsharing lists the policy's subjects as {', '.join(record.subjects)}, which do "
            "not include the discipline given."
        )
    year = _year(context.publication_date)
    if year is not None and record.year_creation and int(record.year_creation) > year:
        out.append(
            f"FAIRsharing dates the policy to {record.year_creation}, after the publication date "
            f"given ({context.publication_date}); check which version applied."
        )
    exceptions = record.clause("sharing_data").values.get("exceptions_to_data_sharing")
    if (exceptions or "").casefold() == "yes":
        out.append("The record says the policy allows exceptions to sharing.")
    dmp = record.clause("dmp_development").values
    if STRENGTHS.get(dmp.get("mandated_dmp_creation", "").casefold()) == Strength.REQUIRED:
        timing = dmp.get("timing_of_dmp")
        when = f", {timing}" if timing and timing.casefold() != "n/a" else ""
        out.append(f"The record says a data management plan is required{when}.")
    if record.status and record.status != "ready":
        out.append(f"FAIRsharing gives the record's status as {record.status}.")
    return out


@dataclass(frozen=True)
class Stated:
    """One policy's obligations, for comparing across policies."""

    record: PolicyRecord
    obligations: Sequence[Obligation]


def _label(record: PolicyRecord) -> str:
    return f"{record.name} ({record.fairsharing_id})"


def _phrase(kind: ObligationKind) -> str:
    return kind.value.replace("_", " ")


def conflicts(stated: Sequence[Stated]) -> list[tuple[ObligationKind, list[PolicyRecord], str]]:
    """Kinds of obligation that two or more policies state with different strengths.

    Each is returned with every policy that states it and a description. The agent does not say
    which policy governs; the researcher and their data steward decide.
    """
    out: list[tuple[ObligationKind, list[PolicyRecord], str]] = []
    for kind in ObligationKind:
        by_strength: dict[Strength, list[PolicyRecord]] = {}
        for s in stated:
            for o in s.obligations:
                if o.kind == kind and o.strength != Strength.UNSTATED:
                    by_strength.setdefault(o.strength, []).append(s.record)
        if len(by_strength) < 2:
            continue
        parts = [
            f"{strength.value} by {', '.join(_label(r) for r in records)}"
            for strength, records in sorted(by_strength.items())
        ]
        involved = [r for records in by_strength.values() for r in records]
        description = (
            f"The policies state {_phrase(kind)} differently: {'; '.join(parts)}. "
            "The agent does not decide which applies; a person should."
        )
        out.append((kind, involved, description))
    return out
