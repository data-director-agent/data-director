"""Which core slots an agent's own input class asks the conductor to fill from its project, and
which class of project content each holds (docs/specs/projects.md, invariants 6 and 8). The
conductor fills them by slot name (`dd_harness.project_facts.give`), never by the class's name."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dd_sdk.agent import AgentSpec

# The classes of project content an agent's own class may be given (invariant 8).
DOCUMENTATION = "documentation"
DECISIONS = "decisions"
# The core input classes whose slots the conductor fills from a project by name.
DRAFT_REQUEST = "DraftRequest"
FILE_INVENTORY = "FileInventory"
MESSAGE = "Message"
CORE_CLASSES = frozenset({DRAFT_REQUEST, FILE_INVENTORY, MESSAGE})
# The core slots an agent's own input class may mix in, which the conductor fills by name
# (`GivenProjectDocuments`, `GivenProjectDecisions`, `GivenProjectRepository`,
# `GivenProjectMetadataRecord`, `GivenProjectPlan`) without the harness naming the class.
AGENT_INPUT_SLOTS = (
    "project_documents",
    "project_decisions",
    "project_repository",
    "project_metadata_draft",
    "project_metadata_approved",
    "project_plan_approved",
)
AGENT_CONTENT_SLOTS = (
    ("project_documents", DOCUMENTATION),
    ("project_decisions", DECISIONS),
    ("project_repository", DECISIONS),
    ("project_metadata_draft", DOCUMENTATION),
    ("project_metadata_approved", DOCUMENTATION),
    ("project_plan_approved", DOCUMENTATION),
)


def chosen(recorded: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """The repository a researcher chose, as a `ChosenRepository`, from what the project's
    summary says of the repository chosen last; None while none is chosen. Only its name and
    identifier: its warnings and when it was chosen are for the person, not an agent."""
    if recorded is None:
        return None
    return {
        "chosen_repository_name": recorded["repository_name"],
        "chosen_repository_id": recorded["repository_id"],
        **({"chosen_re3data_id": recorded["re3data_id"]} if recorded.get("re3data_id") else {}),
    }


def agent_slots(spec: AgentSpec | None, schema_class: Any) -> frozenset[str]:
    """The core slots (`AGENT_INPUT_SLOTS`) the card's schema for an agent's own input class
    declares, from the mixins `GivenProjectDocuments`, `GivenProjectDecisions`,
    `GivenProjectRepository`, `GivenProjectMetadataRecord` and `GivenProjectPlan`; empty for a
    core class, which
    `give` fills by name, or one the agent does not accept."""
    if spec is None or schema_class in CORE_CLASSES:
        return frozenset()
    accepted = spec.accepted(str(schema_class))
    declared = set(accepted.json_schema.get("properties", {})) if accepted else set()
    return frozenset(declared & set(AGENT_INPUT_SLOTS))
