"""What the conductor puts into an agent's input before anything is hashed or stored: the
project's facts (`project_facts.give`), none of its attached documents under a profile that
refuses them, and the repositories the profile names as its institution's
(`institution_repositories.fill`) for an agent whose class asks for them
(docs/specs/projects.md, invariant 6; docs/specs/policy-and-identity.md)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dd_harness import institution_repositories, project_facts
from dd_harness.policy import Profile
from dd_harness.project_facts import FactSource
from dd_sdk.agent import AgentSpec


def give(
    profile: Profile,
    store: FactSource | None,
    project_id: str | None,
    input_doc: Mapping[str, Any],
    spec: AgentSpec | None,
) -> dict[str, Any]:
    """`input_doc` with what the project and the profile give the agent."""
    filled = project_facts.give(
        store, project_id, input_doc, documents=not profile.refuses_documents, spec=spec
    )
    return institution_repositories.fill(profile, filled, spec)
