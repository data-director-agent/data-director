"""Notes from the harness about the project, which open the current message (`agent.py`): what
its inventory is and whether it replaced an earlier one, the researcher's answers to the setup
questions, what the project is called, what people
in it chose or decided, which documents are attached and whether a plan among them has been read
for a repository, and the latest version of each drafted document (docs/specs/orchestration.md).

Each note is written from the slots the conductor fills on a `Message` (docs/specs/projects.md),
never from the conversation, so it is current on every turn, however new or long the
conversation is. A value a person typed, such as a name, is quoted, so the model reads it as data.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Final

from dd_agent_orchestrator_model.own_tools import ENTRY_TOOL, NAME_TOOL
from dd_agent_orchestrator_model.provisional import chose_provisional
from dd_sdk.contract.facts import FactKind, InventoryFormat, ProjectFact
from dd_sdk.contract.models import DraftSummary, GroundingMode, Message
from dd_sdk.intake import NOT_SURE, YES
from dd_sdk.intake import question as intake_question
from dd_sdk.process_flow import entry as flow_entry
from dd_sdk.process_flow import progress, suggested_next

LEAD = "[From the harness, not the researcher] "


def _files(count: int) -> str:
    return "1 file" if count == 1 else f"{count} files"


def _format(group: InventoryFormat) -> str:
    named = group.format_media_type or "media type not told"
    if group.format_pronom_ids:
        named += " (PRONOM " + ", ".join(group.format_pronom_ids) + ")"
    return f"{named}, {_files(group.format_file_count)}"


def record_notes(
    message: Message, manifest: Sequence[Mapping[str, Any]] = ()
) -> tuple[str | None, ...]:
    """The notes written from the project record, in the order they open the message.
    `manifest` is the harness's, from which the documents note says who reads attached text."""
    return (
        intake_note(message),
        name_note(message),
        decisions_note(message),
        documents_note(message, manifest),
        drafts_note(message),
        provisional_note(message),
    )


def progress_note(message: Message, manifest: Sequence[Mapping[str, Any]] = ()) -> str | None:
    """What the harness says of where the project is in the process flow, or None outside a
    project. Names steps by id, as the prompt's flow does, and the suggested next step: one an
    agent in the harness's `manifest` serves, where there is one (#1377)."""
    if message.project_progress is None and message.project_entry is None:
        return None
    start = flow_entry(message.project_entry) if message.project_entry is not None else None
    states = {p.step_id: p.step_state.value for p in message.project_progress or []}
    if start is None:
        where = (
            "no entry point has been recorded, so where the researcher is is not known: if they "
            f"have said, record it with {ENTRY_TOOL}; if not, ask which entry point applies"
        )
    elif message.project_entry_by_researcher is False:
        where = (
            f"you recorded entry point {start.number} ({start.text}) from what the researcher "
            "said; they can change it"
        )
    else:
        where = (
            f"the researcher chose entry point {start.number} ({start.text}) in the setup "
            "questions or the phase tracker"
        )
    by_state = {
        state: [step_id for step_id, s in states.items() if s == state]
        for state in ("done", "started", "skipped")
    }
    shown = (
        "; ".join(f"{state}: {', '.join(ids)}" for state, ids in by_state.items() if ids)
        or "no step is started, done or skipped yet"
    )
    suggested = suggested_next(progress(start, states, manifest), start)
    if suggested is not None:
        nxt = f" Suggested next: [{suggested.step.id}]."
    elif start is None:
        nxt = " No step is suggested until the entry point is known."
    else:
        nxt = " Every step from the entry point is done or skipped."
    return LEAD + f"For this project, {where}. The project record shows {shown}.{nxt}"


# The intake's question about a Data Management Plan (`dd_sdk.intake`), and the labels of its
# answers that the note acts on.
_DMP = "intake.dmp"


def _label(question_id: str, value: str) -> str:
    return next(o.label for o in intake_question(question_id).options if o.value == value)


def intake_note(message: Message) -> str | None:
    """The researcher's answers to the setup questions beside the entry question, which the
    researcher gave before the conversation began, or None if they answered none. No step state
    shows a "Not sure", or any answer about a plan, so without this note the model is not told of
    them, and denies them when the researcher says they answered (#341). When the researcher said
    they have a Data Management Plan and the project holds no attached document, the note asks the
    model to invite them to attach it first, since the drafters and the plan check read it."""
    answers = message.project_intake or []
    if not answers:
        return None
    said = "; ".join(
        f"{json.dumps(a.intake_question_prompt)}: {', '.join(a.intake_answer_labels)}"
        for a in answers
    )
    note = LEAD + (
        "The researcher answered the setup questions before or during the conversation. Their "
        f"answers, beside the entry point: {said}. Treat these as given: do not ask them again. "
        f"{json.dumps(_label(_DMP, NOT_SURE))} means not yet known: ask about it only when a "
        "step needs it."
    )
    dmp = next((a for a in answers if a.intake_question_id == _DMP), None)
    if (
        dmp is not None
        and _label(_DMP, YES) in dmp.intake_answer_labels
        and not message.project_documentation
    ):
        note += (
            " They have a Data Management Plan and have attached no document to the project: "
            "before asking what the plan may already say, invite them to attach it, as the "
            "drafters and the Data Management Plan check read an attached plan's text."
        )
    return note


def _when(at: datetime) -> str:
    return at.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def inventory_note(message: Message) -> str | None:
    """What the harness says of the project's inventory, or None if the project holds none: how
    many files, what kinds and how many tables, so that the model states the kinds of data for the
    researcher to confirm instead of asking for them (#1287). When it replaced an earlier one, as
    when the researcher leaves files out in Edit inventory, the note says so and how many files
    the earlier one listed, so the model does not tell the researcher that what they changed has
    not taken effect (#1280)."""
    held = message.project_inventory
    if held is None:
        return None
    note = (
        LEAD + "The project holds an inventory of the dataset: "
        f"{_files(held.inventory_file_count)}, made {_when(held.inventory_made_at)} by "
        f"{held.inventory_tool} {held.inventory_tool_version}."
    )
    if held.inventory_revised_from_file_count is not None:
        added = f" at {_when(held.inventory_added_at)}" if held.inventory_added_at else ""
        note += (
            f" It was added{added} in place of an earlier inventory of "
            f"{_files(held.inventory_revised_from_file_count)}, as when the researcher leaves "
            "files out in Edit inventory: that change has taken effect, and a draft made since "
            "follows this inventory."
        )
    if held.inventory_formats:
        kinds = "; ".join(_format(group) for group in held.inventory_formats)
        note += f" By media type: {kinds}."
    if held.inventory_table_count == 1:
        note += " 1 file is a table whose fields it lists."
    elif held.inventory_table_count:
        note += f" {held.inventory_table_count} files are tables whose fields it lists."
    if held.inventory_limitations:
        note += " Its limitations: " + "; ".join(held.inventory_limitations) + "."
    return (
        note + " The harness puts it into the input of any agent that takes an inventory: leave "
        "`inventory` out, and send an empty input to an agent that takes only an inventory."
    )


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
            f"({'re3data' if chosen.chosen_re3data_id else 'DataCite'} "
            f"{chosen.chosen_repository_id})"
        )
    said.extend(_fact(fact) for fact in message.project_decisions or [])
    if not said:
        return None
    return LEAD + (
        "From the project record, the researcher chose, and people in the project decided: "
        + "; ".join(said)
        + ". Each stands until the researcher changes it in their project."
    )


def _persona(entry: Mapping[str, Any]) -> str:
    title = str(entry.get("title") or "")
    return f"the {title}" if title else str(entry.get("agent_id"))


def _readers(manifest: Sequence[Mapping[str, Any]]) -> str:
    """Which agents read the text of attached documents and for what, as each card declares
    (`reads_attached`), and that every other agent cannot (#1326): so the model never lets the
    researcher believe an agent that reads only web addresses, such as a policy check, used one.
    Agents the orchestrator cannot ask, itself and other delegation agents, are left out."""
    askable = [
        e
        for e in sorted(manifest, key=lambda e: str(e.get("agent_id")))
        if e.get("grounding_mode") != GroundingMode.DELEGATION.value
    ]
    readers = [f"{_persona(e)} ({e['reads_attached']})" for e in askable if e.get("reads_attached")]
    others = [_persona(e) for e in askable if not e.get("reads_attached")]
    if not readers:
        return (
            " No agent in this deployment reads their text: each is told only their names. When "
            "the researcher expects an agent to use one, say so, and ask for the text they want "
            "used, or a web address."
        )
    said = " Their text is read only by " + "; ".join(readers) + "."
    if others:
        said += (
            " Every other agent (" + ", ".join(others) + ") cannot read them. When the researcher "
            "expects one of those to use a document, say so when you ask it, name the agents "
            "that can read it, and ask for a web address or the words they want used."
        )
    return said


def documents_note(message: Message, manifest: Sequence[Mapping[str, Any]] = ()) -> str | None:
    """The documents attached to the project, by name; which agents read their text (`_readers`,
    #1326); and, while no sharing commitment of a data management plan is decided, that no
    attached plan has been read for a repository (#1233): a repository shortlist does not read the
    documents, so without this the model may offer generalists alone, and say nothing of the
    repository the plan names. None when no document is attached."""
    documents = message.project_documentation or []
    if not documents:
        return None
    names = ", ".join(json.dumps(d.documentation_name) for d in documents)
    note = LEAD + f"The researcher attached to the project: {names}."
    if manifest:
        note += _readers(manifest)
    if any(f.fact_kind == FactKind.SHARING_COMMITMENT for f in message.project_decisions or []):
        return note
    return note + (
        " No sharing commitment from a data management plan has been confirmed, so no attached "
        "plan has been read for a repository: a repository shortlist does not use it. If one is "
        "a plan, say so when you report a shortlist, and offer the Data Management Plan check, "
        "which reads the plan and proposes its commitments for the researcher to confirm."
    )


def drafts_note(message: Message) -> str | None:
    """The latest version of each document drafted in the project, its state and whether it was
    drafted since the inventory was last added, so the model speaks of the latest version and not
    of what it said of an earlier one (#1280). None when nothing is drafted."""
    drafts = message.project_drafts or []
    if not drafts:
        return None
    said = "; ".join(_draft(d) for d in drafts)
    return LEAD + (
        f"From the project record, the latest version of each drafted document: {said}. Only "
        "the latest version counts: what you said of an earlier version may no longer hold. A "
        "document an agent drafts in this turn is newer than this record. Say which files a "
        "draft lists only from its text in an agent's result in this turn; otherwise say which "
        "version is the latest and offer to draft it again."
    )


def _draft(draft: DraftSummary) -> str:
    said = f"{draft.document_kind.value} v{draft.version} ({draft.version_state.value}"
    if draft.drafted_since_inventory is True:
        said += ", drafted from the current inventory"
    elif draft.drafted_since_inventory is False:
        said += (
            ", drafted before the current inventory was added, so it may list files that "
            "inventory no longer lists: offer to draft it again"
        )
    return said + ")"


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


def _standard(fact: ProjectFact) -> str:
    target = fact.standard_target or "dataset"
    said = f"standard chosen for the {target.replace(':', ' ')}: {json.dumps(fact.standard_name)}"
    return said + (f" ({fact.standard_id})" if fact.standard_id else "")


_SAYS: dict[FactKind, Callable[[ProjectFact], str]] = {
    FactKind.FUNDER: _funder,
    FactKind.REQUIRED_REPOSITORY: _required,
    FactKind.FILE_INCLUSION: _file,
    FactKind.SENSITIVITY: _sensitivity,
    FactKind.LICENCE: _licence,
    FactKind.SHARING_COMMITMENT: _commitment,
    FactKind.STANDARD: _standard,
}


PROVISIONAL_NOTE: Final = (
    LEAD + "The researcher chose to continue provisionally, for planning only, while participants' "
    "consent and the ethics approval for sharing are not settled. Give the planning advice they "
    "ask for, such as a repository shortlist, a README or a metadata record, and label each as "
    "provisional: say that it depends on participants' consent and the ethics approval covering "
    "sharing, and may change once those are settled. Building and depositing the package stay "
    "blocked until the researcher confirms, in the deposit check before packaging, that consent "
    "and ethics approval are in place: do not suggest either before then, and say why when asked."
)


def provisional_note(message: Message) -> str | None:
    """The note that the researcher chose planning-only advice, or None if they did not."""
    return PROVISIONAL_NOTE if chose_provisional(message) else None
