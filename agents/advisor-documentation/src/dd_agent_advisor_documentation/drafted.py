"""A README section's text drafted by rule from one project fact (`from` in `readme.yaml`,
docs/specs/drafting.md): the inventory's files, the licences the repository offers, the approved
metadata record's values, or the standards, vocabularies and formats people in the project chose
(`standard` project facts, docs/specs/projects.md, #1391)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from dd_agent_advisor_documentation.record import _from_record
from dd_sdk.contract.facts import DATASET_TARGET, FactKind, ProjectFact
from dd_sdk.contract.models import DraftRequest

FIELD = "field:"


def drafted(source: str, asked: DraftRequest, record: Mapping[str, Any] | None) -> str | None:
    """A section's text drafted from `source`, or None if there is nothing to draft."""
    if source.startswith("record_"):
        return _from_record(source, record) if record is not None else None
    if source == "files" and asked.inventory is not None:
        rows = [
            (
                f"`{f.file_path}`",
                file_format(f.file_media_type, f.file_pronom_ids),
                str(f.file_size),
            )
            for f in asked.inventory.inventory_files
        ]
        return table(("File", "Format", "Size (bytes)"), rows)
    requirements = asked.requirements
    if source == "licences":
        if requirements is None or not requirements.licences:
            return None
        offered = ", ".join(f"`{licence}`" for licence in requirements.licences)
        return f"{requirements.repository_name} offers these licences: {offered}."
    if source == "standards":
        return standards(asked.project_decisions)
    return None


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


def file_format(media_type: str | None, pronom_ids: list[str]) -> str:
    known = media_type or "unknown"
    return f"{known} ({', '.join(pronom_ids)})" if pronom_ids else known


def table(header: tuple[str, ...], rows: Sequence[tuple[str, ...]]) -> str:
    def line(cells: tuple[str, ...]) -> str:
        return "| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |"

    return "\n".join([line(header), line(tuple("---" for _ in header)), *map(line, rows)])
