"""What the conductor puts into an agent's input from the project the run belongs to
(docs/specs/projects.md, invariant 6).

Only the core `DraftRequest` is filled. Within a project its `inventory` and `requirements` are
the project's own: whatever the caller sent is replaced, and a slot the project has no value for
is removed, so that an agent is never given facts a caller, or a model, made up. `current_version`
is removed until regeneration is filled from the project, TODO(#394). Any other input is left as
it was sent. The conductor fills the input before hashing it, so the input hash covers what the
agent was shown.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dd_harness.projects import ProjectStore

# The core input class whose slots the conductor fills from a project.
DRAFT_REQUEST = "DraftRequest"


def give(store: ProjectStore, project_id: str, input_doc: Mapping[str, Any]) -> dict[str, Any]:
    """`input_doc` with the project's facts put in, for a class that asks for them."""
    filled = dict(input_doc)
    if filled.get("schema_class") != DRAFT_REQUEST:
        return filled
    facts = {
        "inventory": store.inventory(project_id),
        "requirements": store.requirements(project_id),
        "current_version": None,
    }
    for slot, value in facts.items():
        if value is None:
            filled.pop(slot, None)
        else:
            filled[slot] = value
    return filled
