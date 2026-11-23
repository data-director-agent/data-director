"""A section's text drafted by rule from one project fact (`from` in `readme.yaml` and `plan.py`,
docs/specs/drafting.md): the inventory's files, the licences the repository offers, the approved
metadata record's values, the standards, vocabularies and formats people in the project chose
(`standard` project facts, docs/specs/projects.md, #1391), and, for a Data Management Plan, the
funders, repository, licence and handling of sensitive data people decided. Before the data
exist, it is also drafted from what people decided about the project at "Describe your project"
(`setup.project`): what it is for, its field and period (`project`), and the data it expects to
produce (`planned_data`). Each is placed as a person decided it: supplied, never inferred
(invariant 2)."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from dd_agent_advisor_documentation.record import _from_record
from dd_sdk.contract.facts import DATASET_TARGET, FactKind, ProjectFact
from dd_sdk.contract.models import DraftRequest

FIELD = "field:"


def drafted(source: str, asked: DraftRequest, record: Mapping[str, Any] | None) -> str | None:
    """A section's text drafted from `source`, or None if there is nothing to draft."""
    if source.startswith("record_"):
        return _from_record(source, record) if record is not None else None
    if source in _FROM_REQUEST:
        return _FROM_REQUEST[source](asked)
    if source in _FROM_DECISIONS:
        return _FROM_DECISIONS[source](asked.project_decisions)
    return decided(source, asked.project_decisions)


def files(asked: DraftRequest) -> str | None:
    """The inventory's files as a table of path, format and size; None without an inventory."""
    if asked.inventory is None:
        return None
    rows = [
        (f"`{f.file_path}`", file_format(f.file_media_type, f.file_pronom_ids), str(f.file_size))
        for f in asked.inventory.inventory_files
    ]
    return table(("File", "Format", "Size (bytes)"), rows)


def licences(asked: DraftRequest) -> str | None:
    """The licences the chosen repository offers; None when it names none."""
    requirements = asked.requirements
    if requirements is None or not requirements.licences:
        return None
    offered = ", ".join(f"`{licence}`" for licence in requirements.licences)
    return f"{requirements.repository_name} offers these licences: {offered}."


def _funder(fact: ProjectFact) -> str:
    return f"- {fact.fact_funder_name}"


def _licence(fact: ProjectFact) -> str:
    return f"- `{fact.licence_id}`"


def _sensitive(fact: ProjectFact) -> str:
    decision = fact.sensitivity_decision
    handled = _HANDLING[decision.value] if decision is not None else _HANDLING["undecided"]
    return f"- {fact.sensitive_subject}: {handled}"


# How each decided fact a Data Management Plan draws on is placed: the kind of fact, the sentence
# that introduces the list, and each fact's line.
_DECIDED: dict[str, tuple[FactKind, str, Callable[[ProjectFact], str]]] = {
    "funders": (FactKind.FUNDER, "The project is funded by:", _funder),
    "licence": (FactKind.LICENCE, "The data will be shared under this licence:", _licence),
    "sensitivity": (
        FactKind.SENSITIVITY,
        "These sensitive data were identified, and it was decided how each is handled:",
        _sensitive,
    ),
}
_HANDLING = {
    "publish": "published as it is",
    "generalise": "generalised before it is shared",
    "withhold": "withheld",
    "undecided": "not yet decided",
}


def decided(source: str, decisions: Sequence[ProjectFact]) -> str | None:
    """The decided facts of the kind `source` names, one line each; None when none is decided or
    the source is not a decided fact's."""
    if source not in _DECIDED:
        return None
    kind, intro, line = _DECIDED[source]
    lines = [line(f) for f in decisions if f.fact_kind == kind]
    return f"{intro}\n\n" + "\n".join(lines) if lines else None


def project(decisions: Sequence[ProjectFact]) -> str | None:
    """What the project is for, its field and when it runs, as decided; None if none is."""
    lines = []
    for fact in decisions:
        if fact.fact_kind == FactKind.PROJECT_SUMMARY and fact.summary_text:
            lines.append(fact.summary_text)
        elif fact.fact_kind == FactKind.FIELD_OF_STUDY:
            lines.append(f"Field of study: {fact.field_name}.")
        elif fact.fact_kind == FactKind.PROJECT_PERIOD:
            end = f" to {fact.period_end}" if fact.period_end else ""
            lines.append(f"The project runs from {fact.period_start}{end}.")
    return "\n\n".join(lines) or None


def planned(decisions: Sequence[ProjectFact]) -> str | None:
    """The data the project expects to produce, one line each, as decided; None if none is."""
    lines = []
    for fact in decisions:
        if fact.fact_kind != FactKind.PLANNED_DATA:
            continue
        details = [
            f"{label}: {value}"
            for label, value in (
                ("collected by", fact.planned_collection_method),
                ("formats", fact.planned_format),
                ("volume", fact.planned_volume),
            )
            if value
        ]
        extra = f" ({'; '.join(details)})" if details else ""
        lines.append(f"- **{fact.fact_subject}**: {fact.planned_description}{extra}")
    if not lines:
        return None
    return "The project expects to produce these data:\n\n" + "\n".join(lines)


def repository(asked: DraftRequest) -> str | None:
    """The repository chosen, and any a funder, journal or institution requires; None if none."""
    lines = []
    if asked.requirements is not None:
        lines.append(f"The data will be deposited in {asked.requirements.repository_name}.")
    for fact in asked.project_decisions:
        if fact.fact_kind == FactKind.REQUIRED_REPOSITORY:
            required_by = ", ".join(fact.fact_required_by)
            by = f" by {required_by}" if required_by else ""
            lines.append(f"{fact.fact_repository_name} is required{by}.")
    return " ".join(lines) or None


def standards(decisions: Sequence[ProjectFact]) -> str | None:
    """The standards chosen, one line each, with what each is chosen for and a link where there
    is one; None when none was chosen."""
    lines = [
        f"- {_named(fact)}: {_target(fact.standard_target)}"
        for fact in decisions
        if fact.fact_kind == FactKind.STANDARD
    ]
    if not lines:
        return None
    return "The data follow these standards, vocabularies and formats:\n\n" + "\n".join(lines)


def _named(fact: ProjectFact) -> str:
    name = fact.standard_name or fact.fact_subject
    return f"[{name}]({fact.standard_id})" if fact.standard_id else name


def _target(target: str | None) -> str:
    if target is None or target == DATASET_TARGET:
        return "the dataset"
    return f"the field `{target.removeprefix(FIELD)}`"


# The sources drafted from the request as a whole, and those drafted from the decided facts alone.
_FROM_REQUEST: dict[str, Callable[[DraftRequest], str | None]] = {
    "files": files,
    "licences": licences,
    "repository": repository,
}
_FROM_DECISIONS: dict[str, Callable[[Sequence[ProjectFact]], str | None]] = {
    "standards": standards,
    "project": project,
    "planned_data": planned,
}


def file_format(media_type: str | None, pronom_ids: list[str]) -> str:
    known = media_type or "unknown"
    return f"{known} ({', '.join(pronom_ids)})" if pronom_ids else known


def table(header: tuple[str, ...], rows: Sequence[tuple[str, ...]]) -> str:
    def line(cells: tuple[str, ...]) -> str:
        return "| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |"

    return "\n".join([line(header), line(tuple("---" for _ in header)), *map(line, rows)])
