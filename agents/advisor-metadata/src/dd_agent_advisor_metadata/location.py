"""Where the data were collected is asked in two steps (#1073, docs/specs/drafting.md, invariant 9).

A precise location can expose people, private land or protected species, and whether it may be
published is a decision for a person (the landowner, the principal investigator or an ecologist),
not a value to fill in. So the librarian does not ask for the place until that is decided:

1. While nothing says whether the location may be published, it asks that, and at what precision,
   and leaves the place `null`. The question targets the location's entry in the record
   (`geoLocations[0]`), so its identifier is stable and its answer is never placed in the record.
   Where the inventory has fields whose names suggest a location, the question names them.
2. Once a person has decided, it asks for the place at the precision agreed. A decision is either
   the project's `sensitivity` facts about locations, which stand over an answer, or the answer a
   person recorded to the first question.

A location that is to be withheld is left `null` and asked about no more, and the outcome's
statement says so and why.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from dd_agent_advisor_metadata.questions import Gap, question_id
from dd_inventory.hints import HintKind, load_rules
from dd_sdk.contract.facts import FactKind, LocationPrecision, ProjectFact, SensitivityDecision
from dd_sdk.contract.models import FileInventory

# Whole lower-case words of a field name that suggest a location: the File Archivist's
# `coordinates` rule (`dd_inventory.hints`), so that both name the same fields.
LOCATION_WORDS = next(r.words for r in load_rules() if r.kind == HintKind.COORDINATES)
_WORD = re.compile(r"[a-z]+")
# An answer to the first question that withholds the location begins with "withhold", as the
# question asks.
_WITHHOLD = re.compile(r"^\W*(withhold|withheld)\b", re.IGNORECASE)
# From the finest precision to the coarsest; where decisions differ, the coarsest stands.
_PRECISIONS = list(LocationPrecision)


@dataclass(frozen=True, slots=True)
class Decision:
    """Whether the location may be published: `withheld`, or the precision agreed, in words, and
    where the decision was recorded."""

    withheld: bool
    precision: str
    source: str


def entry_path(gap: Gap) -> str:
    """The path of the list entry a gap is in: `geoLocations[0]` for
    `geoLocations[0].geoLocationPlace`."""
    return gap.path.rsplit(".", 1)[0] if "." in gap.path else gap.path


def located_fields(inventory: FileInventory | None) -> dict[str, list[str]]:
    """The fields of each file whose names suggest a location, by file path."""
    found: dict[str, list[str]] = {}
    for file in inventory.inventory_files if inventory is not None else []:
        names = [f.name for f in file.file_fields if LOCATION_WORDS & _words(f.name)]
        if names:
            found[file.file_path] = names
    return found


def _words(name: str) -> set[str]:
    return set(_WORD.findall(name.lower()))


def decided(
    decisions: Iterable[ProjectFact], located: Mapping[str, Sequence[str]]
) -> Decision | None:
    """What the project's people decided about publishing its locations, or None while any
    location is undecided or none was decided. A sensitivity fact is about a location when it
    gives a precision, or its subject is a file or field that suggests one."""
    fields = {name for names in located.values() for name in names}
    about = [
        f
        for f in decisions
        if f.fact_kind == FactKind.SENSITIVITY
        and (
            f.location_precision is not None
            or f.sensitive_subject in located
            or f.sensitive_subject in fields
            or LOCATION_WORDS & _words(f.sensitive_subject or "")
        )
    ]
    if not about or any(f.sensitivity_decision == SensitivityDecision.UNDECIDED for f in about):
        return None
    shared = [f for f in about if f.sensitivity_decision != SensitivityDecision.WITHHOLD]
    subjects = ", ".join(sorted({f.sensitive_subject or "" for f in about}))
    source = f"the project's decision on {subjects}"
    if not shared:
        return Decision(withheld=True, precision="", source=source)
    coarsest = max(
        (_PRECISIONS.index(f.location_precision or LocationPrecision.EXACT) for f in shared),
    )
    return Decision(withheld=False, precision=_PRECISIONS[coarsest].value, source=source)


def answered(answer: str | None) -> Decision | None:
    """The decision a person recorded as their answer to the first question, if they did."""
    if answer is None or not answer.strip():
        return None
    text = answer.strip()
    return Decision(withheld=bool(_WITHHOLD.match(text)), precision=text, source="your answer")


def first_question(located: Mapping[str, Sequence[str]], prompt: str) -> str:
    """The first question, naming the fields that suggest a location where there are any."""
    if not located:
        return prompt
    named = "; ".join(f"{path} ({', '.join(names)})" for path, names in sorted(located.items()))
    return f"{prompt} The inventory has fields that suggest locations: {named}."


def second_question(decision: Decision, prompt: str) -> str:
    return f"{prompt} The precision agreed: {decision.precision}."


def withheld_sentence(decision: Decision) -> str:
    return (
        "The place where the data were collected is left empty and not asked for: it is "
        f"withheld, as recorded in {decision.source}."
    )


def asks_first(gap: Gap) -> str:
    """The identifier of the first question about the gap's location."""
    return question_id(entry_path(gap))
