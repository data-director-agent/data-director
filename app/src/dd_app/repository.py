"""A researcher's choice of repository, taken from `advisor.repository`'s shortlist
(docs/specs/deposit.md, docs/specs/app.md).

The request names a stored run and one of its candidates, by the candidate's re3data identifier.
Nothing else about the repository is typed: its name and the metadata standards its re3data
record declares are read from the evidence the run kept, which the harness checked when the run
was stored. Resolving the choice against the deployment's requirement sets and recording it are
the harness's (`dd_harness.requirements`, `ProjectStorage.choose_repository`).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from dd_harness.projects import REPOSITORY_CHOSEN
from dd_harness.requirements import RE3DATA_ID
from dd_harness.storage import ProjectStorage
from dd_sdk.contract.models import UUID7_PATTERN

# The agent whose shortlist a repository is chosen from.
REPOSITORY_ADVISOR = "advisor.repository"
INVOCATION_ID = re.compile(UUID7_PATTERN)
# What `GET /api/projects/{id}/repository` says of the choice, from its event in the log.
VIEWED = (
    "re3data_id",
    "repository_name",
    "declared_standards",
    "requirement_sets",
    "digest",
    "warnings",
)
# What a choice request may give; anything else, such as who chose, is refused.
CHOICE_FIELDS = frozenset({"invocation_id", "re3data_id"})


class ChoiceRequestError(ValueError):
    """A choice that names no candidate of an `advisor.repository` run of this project. Nothing
    is recorded."""


@dataclass(frozen=True)
class Candidate:
    """What the run's evidence says of the chosen repository."""

    re3data_id: str
    repository_name: str
    declared_standards: tuple[str, ...]


def parse_choice(body: object) -> tuple[str, str]:
    """The run and the candidate a `POST /api/projects/{id}/repository` body names. Raises
    `ChoiceRequestError` for a body of the wrong shape."""
    if not isinstance(body, dict):
        raise ChoiceRequestError("The body must be an object.")
    if extra := sorted(set(body) - CHOICE_FIELDS):
        raise ChoiceRequestError(
            f"A choice gives only {sorted(CHOICE_FIELDS)}, not {extra}. "
            "Everything else about the repository comes from the run's evidence."
        )
    invocation_id, re3data_id = body.get("invocation_id"), body.get("re3data_id")
    if not isinstance(invocation_id, str) or not INVOCATION_ID.fullmatch(invocation_id):
        raise ChoiceRequestError("`invocation_id` must name the run that gave the shortlist.")
    if not isinstance(re3data_id, str) or not RE3DATA_ID.fullmatch(re3data_id):
        raise ChoiceRequestError("`re3data_id` must be a re3data identifier (r3d + 9 digits).")
    return invocation_id, re3data_id


def candidate(envelope: Mapping[str, Any] | None, project_id: str, re3data_id: str) -> Candidate:
    """The candidate `re3data_id` in the stored run `envelope`, as its evidence describes it.
    Raises `ChoiceRequestError` unless the run is `advisor.repository`'s, in this project, and
    shortlists that repository with its re3data record as evidence."""
    if envelope is None:
        raise ChoiceRequestError("There is no such run.")
    if envelope.get("agent_id") != REPOSITORY_ADVISOR:
        raise ChoiceRequestError(f"A repository is chosen from a run of {REPOSITORY_ADVISOR}.")
    if envelope.get("project_id") != project_id:
        raise ChoiceRequestError("That run is not in this project.")
    payload = envelope.get("payload") or {}
    candidates: Sequence[Mapping[str, Any]] = payload.get("candidates") or []
    cited = {g.get("source_id") for c in candidates for g in c.get("grounded_on") or []}
    if re3data_id not in cited:
        raise ChoiceRequestError(f"The run does not shortlist {re3data_id}.")
    for item in envelope.get("evidence") or []:
        content = item.get("content")
        if item.get("source_id") == re3data_id and isinstance(content, Mapping):
            name = content.get("name")
            standards = content.get("metadata_standards") or []
            if isinstance(name, str) and isinstance(standards, list):
                return Candidate(re3data_id, name, tuple(str(s) for s in standards))
    raise ChoiceRequestError(f"The run kept no re3data record for {re3data_id}.")


def view(store: ProjectStorage, project_id: str) -> dict[str, Any] | None:
    """`GET /api/projects/{id}/repository`: the repository chosen last, the requirement sets it
    resolved to by version and digest, the warnings from resolving it, and the merged
    requirements. None if none has been chosen. Raises `UnknownProjectError` for an unknown
    project."""
    chosen = [e for e in store.events(project_id) if e["event"] == REPOSITORY_CHOSEN]
    if not chosen:
        return None
    latest = chosen[-1]
    return {
        **{key: latest[key] for key in VIEWED},
        "chosen_at": latest["at"],
        "chosen_by": latest["acted_for"],
        "requirements": store.requirements(project_id),
    }
