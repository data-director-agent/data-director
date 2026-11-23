"""What the Standards Librarian takes from the project record (#1529, docs/specs/projects.md).

In a project the conductor gives the profile the facts people decided (`project_decisions`). A
value the input leaves empty is filled from them, so that a researcher is not asked again for
what the project already holds:

- the decided field of study (`field_of_study`) becomes the profile's subject (`themes`), which
  the registry is searched on and records are matched against;
- the decided description of the data (`data_description`), or else the summary of the project
  (`project_summary`), becomes its `description`, which the explainer's model reads.

In a project the conductor also gives the project's inventory (`project_file_inventory`, #1540).
Empty media types are filled with the distinct media types its files were identified as, and empty
fields with its tables' fields, each name once.

A value the input gives always stands. Nothing is inferred: free-text formats are never turned
into media types, which are exact. Each value taken is said, so the result shows which came from
the record.
"""

from __future__ import annotations

import json

from dd_agent_advisor_standards.classes import DatasetProfile
from dd_sdk.contract.facts import FactKind, ProjectFact
from dd_sdk.contract.inventory import FileInventory


def filled(profile: DatasetProfile) -> tuple[DatasetProfile, list[str]]:
    """`profile` with its empty subject and description filled from the decided facts, its empty
    media types and fields from the inventory, and a few words on each value taken."""
    decided = {f.fact_kind: f for f in profile.project_decisions}
    update: dict[str, object] = {}
    taken: list[str] = []
    field = decided.get(FactKind.FIELD_OF_STUDY)
    if not (profile.themes or profile.keywords) and field is not None and field.field_name:
        update["themes"] = [field.field_name]
        taken.append(f"subject: the decided field of study {json.dumps(field.field_name)}")
    if not profile.description:
        described = _description(decided)
        if described is not None:
            update["description"], what = described
            taken.append(f"description: the decided {what}")
    if profile.project_file_inventory is not None:
        _from_inventory(profile, profile.project_file_inventory, update, taken)
    return (profile.model_copy(update=update) if update else profile), taken


def _description(decided: dict[FactKind, ProjectFact]) -> tuple[str, str] | None:
    """The description of the data, or else of the project, and which it is."""
    data = decided.get(FactKind.DATA_DESCRIPTION)
    if data is not None and data.data_collected:
        formats = f" Formats: {data.data_formats}." if data.data_formats else ""
        return f"{data.data_collected}{formats}", "description of the data"
    summary = decided.get(FactKind.PROJECT_SUMMARY)
    if summary is not None and summary.summary_text:
        return summary.summary_text, "summary of the project"
    return None


def _from_inventory(
    profile: DatasetProfile,
    inventory: FileInventory,
    update: dict[str, object],
    taken: list[str],
) -> None:
    """Fill the empty media types and fields from the inventory."""
    files = inventory.inventory_files
    types = sorted({f.file_media_type for f in files if f.file_media_type})
    if not profile.media_types and types:
        update["media_types"] = types
        taken.append(f"media types: {len(types)} from the inventory")
    fields = list({field.name: field for f in files for field in f.file_fields}.values())
    if not profile.fields and fields:
        update["fields"] = fields
        taken.append(f"fields: {len(fields)} from the inventory's tables")


def said(taken: list[str]) -> str:
    """The statement's sentence on the values taken from the record; empty when none was."""
    return f" From the project record: {'; '.join(taken)}." if taken else ""
