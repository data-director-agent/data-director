"""What a writer is told about a project: the facts a README is drafted from, and, for its
prose, the researcher's answers by section (docs/specs/drafting.md, invariant 4)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from dd_agent_advisor_documentation.counts import counted
from dd_agent_advisor_documentation.drafted import file_format
from dd_agent_advisor_documentation.outline import Outlined
from dd_agent_advisor_documentation.record import (
    _collected,
    _creators,
    _from_record,
    _title,
    _values,
)
from dd_agent_advisor_documentation.suggestions import with_documents
from dd_agent_advisor_documentation.values import field_facts
from dd_sdk.contract.models import DraftRequest, FileInventory, RepositoryRequirements

# The key under which a writer is given the approved metadata record's values.
RECORD_FACTS = "approved_metadata_record"
# The keys under which the README's writer is given the researcher's answers, by section heading,
# and the project's decisions, once the researcher has answered a section.
RESEARCHER_ANSWERS = "researcher_answers"
# The key that tells a writer the data are not collected yet, when there is no inventory.
DATA_COLLECTED = "data_collected"
PROJECT_DECISIONS = "project_decisions"


def _prose_facts(
    inventory: FileInventory | None,
    requirements: RepositoryRequirements | None,
    record: Mapping[str, Any] | None,
    asked: DraftRequest,
    outline: Sequence[Outlined],
) -> dict[str, Any]:
    """What the writer is told for the README's prose: the facts, and, when the researcher has
    answered a section, their answers by heading, the project's decisions and the documents they
    attached, so that the section can be written from them (docs/specs/drafting.md, invariant 4).
    """
    facts = _facts(inventory, requirements, record)
    given = {p.section.heading: p.answer for p in outline if p.answer is not None}
    if not given:
        return facts
    facts[RESEARCHER_ANSWERS] = given
    if asked.project_decisions:
        facts[PROJECT_DECISIONS] = [
            d.model_dump(mode="json", exclude_none=True) for d in asked.project_decisions
        ]
    return with_documents(facts, asked)


def _facts(
    inventory: FileInventory | None,
    requirements: RepositoryRequirements | None,
    record: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """What a writer is told: the facts the README is drafted from, and nothing else. A field's
    description is left out: a definition is the researcher's to give (docs/specs/drafting.md).
    With no inventory, the data are not collected yet (#1017): the writer is told so, and given
    no files and no counts."""
    facts: dict[str, Any] = (
        {**counted(inventory), "files": _files(inventory)}
        if inventory is not None and inventory.inventory_files
        else {DATA_COLLECTED: False}
    )
    if record is not None:
        year = record.get("publicationYear")
        given = {
            "title": _title(record),
            "creators": _creators(record),
            "funders": _values(record, "fundingReferences", "funderName"),
            "dates_collected": _collected(record),
            "geographic_locations": _values(record, "geoLocations", "geoLocationPlace"),
            "abstract": _from_record("record_abstract", record),
            "licence": _from_record("record_rights", record),
            "publication_year": str(year) if isinstance(year, int | str) and str(year) else None,
        }
        facts[RECORD_FACTS] = {k: v for k, v in given.items() if v}
    if requirements is not None and requirements.licences:
        facts["repository"] = {
            "name": requirements.repository_name,
            "licences_offered": list(requirements.licences),
        }
    return facts


def _files(inventory: FileInventory) -> list[dict[str, Any]]:
    return [
        {
            "path": f.file_path,
            "format": file_format(f.file_media_type, f.file_pronom_ids),
            "size_bytes": f.file_size,
            **({"fields": [field_facts(c) for c in f.file_fields]} if f.file_fields else {}),
        }
        for f in inventory.inventory_files
    ]
