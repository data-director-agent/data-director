"""The pause before deposit (docs/specs/deposit.md, invariants 20 to 22).

C2 asks that a deposit pause where possible identifiers are flagged, that a person be alerted and
told what to do, and that the researcher confirm that ethics approval is in place before any
deposit proceeds. `pause` gives the results of that pause, which `dd_harness.deposit.validate`
adds to the project's validation:

- each file a person must decide on before deposit is a violation, until a person decides it. A
  file needs a decision when the stored inventory's personal-data findings name it, when an open
  proposal about whether it goes in or whether it may be published names it, whichever agent
  proposed it, or when the fact that stands about it is `undecided`. A person decides it by
  stating whether it goes in (`file_inclusion`) or whether it may be published (`sensitivity`),
  as a `fact_decided` event (docs/specs/projects.md, invariant 28). The pause reads only the
  inventory and project facts, so it names no agent and reads no agent's payload;
- an inventory, or a part of one, made without the personal-data check is a warning, since
  nothing in it was looked at for personal data (docs/specs/personal-data.md, invariant 2);
- when nothing needs a decision, a note says what was not checked, so that no flag is never read
  as clearance (docs/specs/personal-data.md, invariant 10);
- a violation until a person confirms `DEPOSIT_CHECKS` for the inventory the project holds now,
  and a note naming who confirmed them and when once someone has.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any, Final
from urllib.parse import quote

from dd_harness.projects.deposits import DEPOSIT_CHECKS
from dd_harness.shacl import DD, INFO, VIOLATION, WARNING, Result
from dd_harness.storage import DepositSource
from dd_sdk.contract.facts import FactKind

DECISION_CHECK: Final = DD + "PersonDecisionConstraintComponent"
PERSONAL_DATA_CHECK: Final = DD + "PersonalDataCheckConstraintComponent"
CONFIRMATION_CHECK: Final = DD + "DepositChecksConfirmationConstraintComponent"

# The kinds of fact that decide a file before deposit, and the slot that holds each one's value.
DECIDING: Final = {
    FactKind.FILE_INCLUSION.value: "file_decision",
    FactKind.SENSITIVITY.value: "sensitivity_decision",
}
UNDECIDED: Final = "undecided"
WHERE: Final = {"field name": "field names", "file name": "file name", "text": "text"}

NOTHING_FLAGGED: Final = (
    "Nothing in the inventory was flagged for a person to decide before deposit. This does not "
    "mean the data hold no personal data, sensitive locations or material from others: free text "
    "beyond the files checked, other formats, indirect identifiers, rows beyond the sample and "
    "what files are about were not checked."
)


def pause(
    projects: DepositSource, project_id: str, inventory: Mapping[str, Any]
) -> Iterator[Result]:
    """The results of the pause before deposit for a project that holds `inventory`."""
    standing = projects.decisions(project_id) or []
    decided = {
        subject
        for fact in standing
        if (value := _value(fact)) is not None and value != UNDECIDED
        for subject in _subjects(fact)
    }
    waiting: dict[str, list[str]] = {}
    for subject, reason in _flagged(inventory):
        if subject not in decided:
            waiting.setdefault(subject, []).append(reason)
    for proposal in projects.proposals(project_id):
        fact = proposal["fact"]
        if _value(fact) is not None:
            reason = fact.get("proposed_because") or "A check proposed a decision on it."
            waiting.setdefault(_subject(fact), []).append(reason)
    for fact in standing:
        if _value(fact) == UNDECIDED:
            waiting.setdefault(_subject(fact), []).append("The decision on it is undecided.")
    for subject, reasons in waiting.items():
        yield Result(
            VIOLATION, _waiting(subject, reasons), _file_iri(project_id, subject), DECISION_CHECK
        )
    unchecked = list(_unchecked(inventory))
    for where in unchecked:
        yield Result(
            WARNING,
            f"{where} was made without the check for personal data, so nothing in it was looked "
            "at for personal data. Make the inventory again with the current dd-inventory to "
            "check it.",
            _project_iri(project_id),
            PERSONAL_DATA_CHECK,
        )
    if not waiting and not unchecked:
        yield Result(INFO, NOTHING_FLAGGED, _project_iri(project_id), PERSONAL_DATA_CHECK)
    yield _confirmation(projects, project_id)


def _confirmation(projects: DepositSource, project_id: str) -> Result:
    confirmed = projects.checks_confirmation(project_id)
    if confirmed is None:
        return Result(
            VIOLATION,
            "Nobody has confirmed, for the inventory the project holds now, that "
            + "; that ".join(_lower(s).removesuffix(".") for s in DEPOSIT_CHECKS)
            + ". An owner of the project confirms it before the package is built.",
            _project_iri(project_id),
            CONFIRMATION_CHECK,
        )
    who = confirmed["acted_for"].get("name") or confirmed["acted_for"]["principal_id"]
    return Result(
        INFO,
        f"{who} confirmed the checks before deposit for this inventory at {confirmed['at']}.",
        _project_iri(project_id),
        CONFIRMATION_CHECK,
    )


def _flagged(inventory: Mapping[str, Any]) -> Iterator[tuple[str, str]]:
    """Each place the inventory's personal-data findings name, and why it needs a decision. A
    finding holds no value, so neither does the reason (docs/specs/personal-data.md)."""
    found: dict[str, dict[str, set[str]]] = {}
    for finding in _findings(inventory):
        kinds = found.setdefault(finding["finding_file"], {})
        target = finding["finding_target"]
        place = (
            f"column {finding['finding_column']}"
            if target == "column" and finding.get("finding_column")
            else WHERE.get(target, target)
        )
        kinds.setdefault(finding["finding_kind"], set()).add(place)
    for path, kinds in found.items():
        what = "; ".join(f"{kind} in its {', '.join(sorted(p))}" for kind, p in kinds.items())
        yield (
            path,
            f"Possible personal data was flagged ({what}). The inventory does not include the "
            "values; talk to your data steward or ethics contact about how they should be "
            "handled.",
        )


def _findings(inventory: Mapping[str, Any]) -> Iterator[Mapping[str, Any]]:
    """The inventory's findings and its parts', each once."""
    seen: set[tuple[Any, ...]] = set()
    lists = [inventory.get("inventory_personal_data")]
    lists += [p.get("part_personal_data") for p in inventory.get("inventory_parts") or []]
    for findings in lists:
        for finding in findings or []:
            key = tuple(sorted((k, str(v)) for k, v in finding.items()))
            if key not in seen:
                seen.add(key)
                yield finding


def _unchecked(inventory: Mapping[str, Any]) -> Iterator[str]:
    """What of the inventory was made with no personal-data check: absent is not empty."""
    parts = inventory.get("inventory_parts")
    if parts:
        for part in parts:
            if part.get("part_personal_data") is None:
                yield f"The part of the inventory for {part['part_folder']}"
    elif inventory.get("inventory_personal_data") is None:
        yield "The inventory"


def _value(fact: Mapping[str, Any]) -> str | None:
    """The decision a fact about a file holds, or None for a fact of another kind."""
    slot = DECIDING.get(str(fact.get("fact_kind")))
    return None if slot is None else fact.get(slot)


def _subject(fact: Mapping[str, Any]) -> str:
    return str(fact.get("fact_file_path") or fact.get("sensitive_subject") or fact["fact_subject"])


def _subjects(fact: Mapping[str, Any]) -> set[str]:
    keys = ("fact_subject", "fact_file_path", "sensitive_subject")
    return {str(fact[k]) for k in keys if fact.get(k)}


def _waiting(subject: str, reasons: list[str]) -> str:
    return (
        f"{subject} needs a person's decision before deposit: {' '.join(dict.fromkeys(reasons))} "
        "Decide under Project facts whether it goes in the deposit, or whether it may be "
        "published, generalised or withheld."
    )


def _lower(text: str) -> str:
    return text[:1].lower() + text[1:]


def _project_iri(project_id: str) -> str:
    return f"urn:uuid:{project_id}"


def _file_iri(project_id: str, path: str) -> str:
    return f"urn:uuid:{project_id}#file/{quote(path)}"
