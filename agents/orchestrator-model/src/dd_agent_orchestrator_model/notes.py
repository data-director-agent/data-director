"""Notes from the harness about the project, which open the current message (`agent.py`): what
the project is called, what people in it chose or decided, and which documents are attached
and whether a plan among them has been read for a repository (docs/specs/orchestration.md).

Each note is written from the slots the conductor fills on a `Message` (docs/specs/projects.md),
never from the conversation, so it is current on every turn, however new or long the
conversation is. A value a person typed, such as a name, is quoted, so the model reads it as data.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from dd_agent_orchestrator_model.own_tools import NAME_TOOL
from dd_sdk.contract.facts import FactKind, ProjectFact
from dd_sdk.contract.models import Message

LEAD = "[From the harness, not the researcher] "


def record_notes(message: Message) -> tuple[str | None, ...]:
    """The notes written from the project record, in the order they open the message."""
    return name_note(message), decisions_note(message), documents_note(message)


def name_note(message: Message) -> str | None:
    """What the harness says of the project's name, or None outside a project."""
    if message.project_title_by_researcher is None:
        return None
    if message.project_title is None:
        return LEAD + (
            "The project has no name yet. Once you know what the research or dataset is, name "
            f"it with {NAME_TOOL}."
        )
    if message.project_title_by_researcher:
        return LEAD + f"The researcher named the project {json.dumps(message.project_title)}."
    return LEAD + (
        f"You named the project {json.dumps(message.project_title)}; the researcher has not "
        f"renamed it. Call {NAME_TOOL} again only if the name is wrong."
    )


def decisions_note(message: Message) -> str | None:
    """What the harness says the researcher chose and people in the project decided: the
    repository chosen for deposit and each decided fact, the last decision on each. None when
    the `Message` carries neither, as outside a project, before anything is decided, or where
    the profile keeps decisions from the model; so the note never says that nothing is decided."""
    said = []
    if (chosen := message.project_repository) is not None:
        said.append(
            f"repository chosen for deposit: {json.dumps(chosen.chosen_repository_name)} "
            f"(re3data {chosen.chosen_re3data_id})"
        )
    said.extend(_fact(fact) for fact in message.project_decisions or [])
    if not said:
        return None
    return LEAD + (
        "From the project record, the researcher chose, and people in the project decided: "
        + "; ".join(said)
        + ". Each stands until the researcher changes it in their project."
    )


def documents_note(message: Message) -> str | None:
    """The documents attached to the project, by name, and, while no sharing commitment of a
    data management plan is decided, that no attached plan has been read for a repository
    (#1233): a repository shortlist does not read the documents, so without this the model may
    offer generalists alone, and say nothing of the repository the plan names. None when no
    document is attached."""
    documents = message.project_documentation or []
    if not documents:
        return None
    names = ", ".join(json.dumps(d.documentation_name) for d in documents)
    note = LEAD + f"The researcher attached to the project: {names}."
    if any(f.fact_kind == FactKind.SHARING_COMMITMENT for f in message.project_decisions or []):
        return note
    return note + (
        " No sharing commitment from a data management plan has been confirmed, so no attached "
        "plan has been read for a repository: a repository shortlist does not use it. If one is "
        "a plan, say so when you report a shortlist, and offer the Data Management Plan check, "
        "which reads the plan and proposes its commitments for the researcher to confirm."
    )


def _fact(fact: ProjectFact) -> str:
    """One decided fact, from its structured slots only: never anyone's words about why."""
    return _SAYS[fact.fact_kind](fact)


def _funder(fact: ProjectFact) -> str:
    ids = [i for i in (fact.fact_funder_ror, fact.fact_crossref_funder_id) if i]
    return f"funder: {json.dumps(fact.fact_funder_name)}" + (f" ({', '.join(ids)})" if ids else "")


def _required(fact: ProjectFact) -> str:
    said = f"required repository: {json.dumps(fact.fact_repository_name)}"
    if fact.fact_re3data_id:
        said += f" (re3data {fact.fact_re3data_id})"
    if fact.fact_required_by:
        said += f", required by {', '.join(json.dumps(r) for r in fact.fact_required_by)}"
    return said


def _file(fact: ProjectFact) -> str:
    return f"file {json.dumps(fact.fact_file_path)}: {fact.file_decision}"


def _sensitivity(fact: ProjectFact) -> str:
    said = f"sensitive {json.dumps(fact.sensitive_subject)}: {fact.sensitivity_decision}"
    if fact.location_precision is not None:
        said += f" to {fact.location_precision} precision"
    return said


def _licence(fact: ProjectFact) -> str:
    return f"licence: {fact.licence_id}"


def _commitment(fact: ProjectFact) -> str:
    terms = [
        f"{label} {json.dumps(value)}"
        for label, value in (
            ("in", fact.commitment_repository),
            ("access", fact.commitment_access),
            ("licence", fact.commitment_licence),
        )
        if value
    ]
    said = f"data management plan commits to share {json.dumps(fact.fact_subject)}"
    return said + (f" ({', '.join(terms)})" if terms else "")


_SAYS: dict[FactKind, Callable[[ProjectFact], str]] = {
    FactKind.FUNDER: _funder,
    FactKind.REQUIRED_REPOSITORY: _required,
    FactKind.FILE_INCLUSION: _file,
    FactKind.SENSITIVITY: _sensitivity,
    FactKind.LICENCE: _licence,
    FactKind.SHARING_COMMITMENT: _commitment,
}
