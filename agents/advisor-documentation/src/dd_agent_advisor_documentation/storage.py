"""The institution's storage services, offered as a suggestion to a Data Management Plan's
storage question (docs/specs/drafting.md, invariant 7).

In a project or not, the conductor gives a drafter the storage services the deployment's profile
names as its institution's (`DraftRequest.institution_storage`, `GivenInstitutionStorage`). They
say what is available, not what this project will use, so they are never placed in the plan:
`offer` puts them beside the open question of the section on storage and backup, composed by rule
from what the profile vouches for (`suggestion_derivation` `template`, `suggested_from`
`institution`). A person's own words come first: a question that already carries a suggestion
keeps it.
"""

from __future__ import annotations

from collections.abc import Sequence

from dd_dmp_template import SECTIONS
from dd_sdk.contract.facts import FactKind, InstitutionStorage, ProjectFact
from dd_sdk.contract.models import DocumentQuestion, DraftRequest
from dd_sdk.contract.questions import SUGGESTED_FROM_INSTITUTION, Derivation

# The template's section the services are offered to, by its id rather than its heading's words.
HEADING = next(s.heading for s in SECTIONS if s.id == "storage-backup")


def offer(questions: Sequence[DocumentQuestion], asked: DraftRequest) -> list[DocumentQuestion]:
    """`questions`, the open question on storage and backup offered the institution's services."""
    text = suggestion(asked.institution_storage, asked.project_decisions)
    if text is None:
        return list(questions)
    return [
        q.model_copy(
            update={
                "suggested_answer": text,
                "suggestion_derivation": Derivation.TEMPLATE,
                "suggested_from": SUGGESTED_FROM_INSTITUTION,
            }
        )
        if q.gap_section == HEADING and q.gap_part is None and q.suggested_answer is None
        else q
        for q in questions
    ]


def offered(questions: Sequence[DocumentQuestion]) -> bool:
    return any(q.suggested_from == SUGGESTED_FROM_INSTITUTION for q in questions)


def suggestion(
    storage: Sequence[InstitutionStorage], decisions: Sequence[ProjectFact]
) -> str | None:
    """The services as one answer to edit, or None when the profile names none. With sensitive
    data identified in the project, those approved for them come first and the others say so."""
    if not storage:
        return None
    sensitive = any(f.fact_kind == FactKind.SENSITIVITY for f in decisions)
    ordered = sorted(storage, key=lambda s: not s.approved_for_sensitive) if sensitive else storage
    lines = [f"- {_line(s, sensitive=sensitive)}" for s in ordered]
    return "The data will be kept on the institution's storage:\n\n" + "\n".join(lines)


def _line(entry: InstitutionStorage, *, sensitive: bool) -> str:
    said = [entry.storage_name]
    if entry.approved_for_sensitive:
        said.append("approved for personal or sensitive data")
    elif sensitive:
        said.append("not stated to be approved for sensitive data")
    if entry.storage_backup:
        said.append(f"backup: {entry.storage_backup}")
    return "; ".join(said) + "."
