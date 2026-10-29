"""What a repository's records say about each Phase 3 question, and how it compares with the needs.

Every judgement here is read from a registry field or compared with the needs by a fixed rule;
none is written by a model. Where the records are silent the answer is `unstated`, never a guess:
in particular a record that lists no deposit fee does not show that there is none.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dd_agent_repository.classes import AccessNeed, Affiliation, Answer, RepositoryNeeds
from dd_agent_repository.records import DatabaseRecord, Institution, Re3dataRecord, bare_ror

# The responsibilities that make an institution the repository's operator, not its supplier.
OPERATING = frozenset({"general", "funding"})


def assigns_pids(record: Re3dataRecord) -> Answer:
    systems = {s.lower() for s in record.pid_systems}
    if not systems:
        return Answer.UNSTATED
    return Answer.NO if systems == {"none"} else Answer.YES


def _operates(institution: Institution) -> bool:
    # An institution with no responsibility listed is taken as an operator.
    return not institution.responsibilities or bool(OPERATING & set(institution.responsibilities))


def commercial(record: Re3dataRecord) -> Answer:
    """Yes when a commercial institution operates it; no when the operators are all typed and
    none is commercial. A commercial technical supplier is a note, not an operator."""
    operators = [i for i in record.institutions if _operates(i)]
    if any(i.type == "commercial" for i in operators):
        return Answer.YES
    if operators and all(i.type for i in operators):
        return Answer.NO
    return Answer.UNSTATED


def fee_required(record: Re3dataRecord) -> Answer:
    return Answer.YES if "feeRequired" in record.data_upload_restrictions else Answer.UNSTATED


def affiliated(record: Re3dataRecord, affiliation: Affiliation | None) -> Institution | None:
    """The operating institution that is the researcher's, by ROR where both have one, else by
    exact name ignoring case."""
    if affiliation is None:
        return None
    ror = bare_ror(affiliation.ror) if affiliation.ror else None
    name = affiliation.name.casefold().strip()
    for institution in record.institutions:
        if not _operates(institution):
            continue
        if ror and institution.ror:
            if institution.ror == ror:
                return institution
        elif institution.name.casefold().strip() == name:
            return institution
    return None


_ACCESS_PHRASE = {
    AccessNeed.OPEN: "Open access",
    AccessNeed.EMBARGOED: "Embargoed access",
    AccessNeed.RESTRICTED: "Restricted access",
}


def access_met(record: Re3dataRecord, need: AccessNeed | None) -> bool | None:
    """Whether the access the data needs is listed; None when nothing is needed or listed."""
    if need is None or not record.data_access_types:
        return None
    return need.value in record.data_access_types


@dataclass
class Assessment:
    meets: list[str] = field(default_factory=list)
    misses: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def assess(
    record: Re3dataRecord, database: DatabaseRecord | None, needs: RepositoryNeeds
) -> Assessment:
    out = Assessment()

    # Access, as decided in Phase 2.
    if needs.access is not None:
        phrase = _ACCESS_PHRASE[needs.access]
        met = access_met(record, needs.access)
        if met is None:
            out.misses.append("Access options are not stated.")
        elif met:
            out.meets.append(f"{phrase} is offered.")
        else:
            out.misses.append(f"{phrase} is not listed.")

    # Who may deposit.
    home = affiliated(record, needs.affiliation)
    if home is not None:
        out.meets.append(f"Operated by {home.name}, the researcher's institution.")
    if "closed" in record.data_upload_types:
        out.misses.append("Deposits are closed.")
    if "institutional membership" in record.data_upload_restrictions:
        if home is not None:
            out.meets.append("Deposit is open to members of the researcher's institution.")
        else:
            out.misses.append("Deposit requires membership of the institutions that run it.")

    # Persistent identifiers (R7).
    pids = assigns_pids(record)
    systems = [s for s in record.pid_systems if s.lower() != "none"]
    if pids == Answer.YES:
        out.meets.append(
            f"Assigns persistent identifiers ({', '.join(systems)}); re3data does not say "
            "whether this is automatic."
        )
    elif pids == Answer.NO:
        out.misses.append("re3data lists no persistent identifier system.")
    else:
        out.misses.append("Persistent identifier assignment is not stated.")

    # Costs.
    if fee_required(record) == Answer.YES:
        out.notes.append("A deposit fee may be charged; re3data gives no amount.")
    if "feeRequired" in record.data_access_restrictions:
        out.notes.append("Some data may be available to users only for a fee.")
    for supplier in record.institutions:
        if supplier.type == "commercial" and not _operates(supplier):
            out.notes.append(f"A commercial organisation, {supplier.name}, supplies the platform.")

    # Certification, which carries no weight in ranking.
    if record.certificates:
        named = sorted({c for c in record.certificates if c.lower() != "other"})
        out.notes.append(
            f"Certification listed: {', '.join(named)}."
            if named
            else "re3data lists a certificate without naming it."
        )

    # What FAIRsharing's curators add.
    if database is not None:
        if database.status == "deprecated":
            out.misses.append("FAIRsharing lists it as deprecated.")
        if database.deposition_notes:
            out.notes.append(f"FAIRsharing on deposits: {database.deposition_notes}")
        if database.pre_publication_review == "yes":
            out.notes.append("Offers access for pre-publication review.")
    return out
