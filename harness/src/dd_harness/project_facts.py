"""What the conductor puts into an agent's input from the project the run belongs to
(docs/specs/projects.md, invariant 6).

Three core classes are filled. Within a project:

- a `DraftRequest`'s `inventory`, `requirements`, `metadata_record`, `draft_answers`,
  `shared_answers`, `researchers` and `project_documents` are the project's own: whatever the
  caller sent is replaced, and a slot the project has no value for is removed, so that an agent is
  never given facts a caller, or a model, made up. The metadata record is the version a person
  approved last, since a drafter treats it as supplied. The answers are the latest a person
  recorded to each question of the project's documents of the kind asked for
  (docs/specs/drafting.md, invariant 6): a drafter marks an answer `supplied`, so no caller may
  send one. The `shared_answers` are the latest answers a person recorded for documents of other
  kinds to questions on a value every kind gives the same way (`shared_field`), which a drafter
  may only offer as suggestions. The `project_documents` are the documents a researcher attached,
  each with its text, from which a drafter's model may suggest answers. The `current_version` is
  the latest version of the project's document of that kind drafted or revised last, or of the one
  `redraft_document` names, so a drafter that revises it makes that document's next version. A
  `redraft_document` that is not the project's, or is of another kind, is refused (`refusal`);
  outside a project it is removed, since it names a project document;
- a plain `FileInventory` is the project's inventory, when it holds one;
- a `Message`'s `project_inventory` says what the project's inventory is, so that an orchestrator
  knows the project holds one without being given its files; its `project_entry` and
  `project_progress` say which entry point the researcher chose and how far each step of the
  process flow has gone, derived from the log on every turn (`dd_harness.progress`), and its
  `project_intake` the researcher's answers to the other setup questions, "Not sure" included,
  which no step state shows (`intake_answers`); its `project_title` is the project's latest
  title, and `project_title_by_researcher` whether a person gave it, so that an orchestrator's
  model can name a project nobody has named; its
  `project_documentation` lists the documents a researcher attached, by name, digest, media type
  and size, without their text, so that an orchestrator knows they are there.
  `project_entry_by_researcher` whether the researcher chose the entry point, so that the model
  can record one it worked out from what they said until they do. Its `project_researchers` are
  the facts people in the project kept from their public ORCID records, as a `DraftRequest`'s
  `researchers` are, so that an agent can draft creators, affiliations, subjects and funding
  from what a researcher chose to supply rather than ask for them. They are the project's
  researchers, not whom the run acts for: every run in the project is given the same. Its
  `project_repository` is the repository a researcher chose last (`repository_chosen`), by name
  and re3data identifier, so that an orchestrator knows one is chosen and which (#1168). Its
  `project_inventory` says too when the inventory was added and how many files the one it
  replaced listed, and its `project_drafts` give the latest version of each drafted document,
  its state and whether it was drafted since the inventory was last added, without its text
  (`dd_harness.project_drafts`), so that an orchestrator says what the latest version holds, not
  what it said of an earlier one (#1280).

A `DraftRequest`'s and a `Message`'s `project_decisions` are the facts people in the project
decided about it (`dd_harness.projects.facts`): its funders, the repositories a funder or
institution requires, which files go in, whether sensitive fields or files may be published and
how, and its licence. They are the last decision on each, never what an agent only proposed, and
never the agent's or person's words about why. Outside a project, a `Message`'s are removed; a
`DraftRequest`'s, like its other facts, are the caller's. An agent's own input class that mixes in
`GivenProjectDecisions` or `GivenProjectRepository` is given the decided facts or the chosen
repository by slot name, as one that mixes in `GivenProjectDocuments` is given attached documents.
One that mixes in `GivenProjectMetadataRecord` is given the latest version of the project's
metadata record, whatever its state, and the version a person approved last; both are
documentation, as a `DraftRequest`'s `metadata_record` is, and neither is an attached document.

A `Message`'s project slots are the conductor's alone: outside a project they are removed. Any
other input is left as it was sent. The conductor fills the input before hashing it, so the input
hash covers what the agent was shown.

`given` says which classes of project content (invariant 8) a filled input holds, so that the
conductor can refuse to send `documentation` to an agent that calls a hosted model unless the
profile's `hosted_models` allows it. An inventory, and what it is, are `inventory`. A metadata
record, a version to regenerate, a person's answers and attached documents' text are
`documentation`. A repository's
requirements are the repository's, not the project's, and a `Message`'s entry point and progress
say only which steps of the process flow have gone how far; they are neither. Nor is a project's
title: a name a researcher typed, or a model wrote from what was said in the conversation, which
the model is sent anyway. Nor is a `Message`'s `project_documentation`: it holds a document's
file name, as a researcher gave it in the conversation, and never its text. Nor are its
`project_drafts`: each is a document's kind, version number and state, never its text.
Researcher facts are `researcher`: public, but personal, so they go to a hosted model only where
the profile says. They, and the text of attached documents, add to what an agent is given and
no agent needs them, so where the profile keeps their class from an agent the conductor leaves
them out (`leave_out`) rather than refusing the run; a metadata record, a version or answers
withheld still refuse it, since the conductor classes what is left again. Decided facts are
`decisions`: structured values about the project, which go to a hosted model unless the
profile says otherwise; so is the repository a researcher chose, a decision too. Without them a
drafter would draft as if nothing had been decided, so where the profile keeps them from a drafter
the run is refused; a `Message`'s are left out instead, and so is its chosen repository, so that a
conversation with a hosted orchestrator does not stop once a fact is decided.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from dd_harness.progress import ENTRY_BY_RESEARCHER
from dd_harness.project_drafts import drafts, revision
from dd_harness.projects import TITLE_BY_RESEARCHER
from dd_harness.storage import (
    ProjectDocuments,
    ProjectFacts,
    ProjectHoldings,
    ProjectLifecycle,
    ProjectProgress,
    ProjectRepository,
    ProjectResearchers,
)
from dd_sdk.agent import AgentSpec
from dd_sdk.contract.models import DocumentKind

# The core input classes whose slots the conductor fills from a project.
DRAFT_REQUEST = "DraftRequest"
FILE_INVENTORY = "FileInventory"
MESSAGE = "Message"
CORE_CLASSES = frozenset({DRAFT_REQUEST, FILE_INVENTORY, MESSAGE})
# The core slots an agent's own input class may mix in, which the conductor fills by name
# (`GivenProjectDocuments`, `GivenProjectDecisions`, `GivenProjectRepository`,
# `GivenProjectMetadataRecord`) without the harness naming the class.
AGENT_INPUT_SLOTS = (
    "project_documents",
    "project_decisions",
    "project_repository",
    "project_metadata_draft",
    "project_metadata_approved",
)
# A `Message`'s slots that only the conductor fills.
MESSAGE_PROJECT_SLOTS = (
    "project_inventory",
    "project_entry",
    "project_progress",
    "project_title",
    "project_title_by_researcher",
    "project_documentation",
    "project_entry_by_researcher",
    "project_researchers",
    "project_decisions",
    "project_repository",
    "project_drafts",
    "project_intake",
)

# The classes of project content (docs/specs/projects.md, invariant 8).
INVENTORY = "inventory"
DOCUMENTATION = "documentation"
RESEARCHER = "researcher"
DECISIONS = "decisions"
# The slots that hold researcher facts, of a `Message` and of a `DraftRequest`.
RESEARCHER_SLOTS = ("project_researchers", "researchers")


class FactSource(
    ProjectLifecycle,
    ProjectHoldings,
    ProjectResearchers,
    ProjectRepository,
    ProjectProgress,
    ProjectDocuments,
    ProjectFacts,
    Protocol,
):
    """The areas of a project its facts are read from: every area but its deposits. The
    conductor reads them from one snapshot of the project per invocation (`Projects.snapshot`)."""


# A `DraftRequest`'s slots that hold documentation.
DOCUMENTATION_SLOTS = (
    "metadata_record",
    "current_version",
    "draft_answers",
    "shared_answers",
    "project_documents",
)
# Which slot of a filled input holds which class of project content, by input class.
CONTENT_SLOTS: dict[str, tuple[tuple[str, str], ...]] = {
    MESSAGE: (
        ("project_inventory", INVENTORY),
        ("project_researchers", RESEARCHER),
        ("project_decisions", DECISIONS),
        ("project_repository", DECISIONS),
    ),
    DRAFT_REQUEST: (
        ("inventory", INVENTORY),
        *((slot, DOCUMENTATION) for slot in DOCUMENTATION_SLOTS),
        ("researchers", RESEARCHER),
        ("project_decisions", DECISIONS),
    ),
}
AGENT_CONTENT_SLOTS = (
    ("project_documents", DOCUMENTATION),
    ("project_decisions", DECISIONS),
    ("project_repository", DECISIONS),
    ("project_metadata_draft", DOCUMENTATION),
    ("project_metadata_approved", DOCUMENTATION),
)


def give(
    store: FactSource | None,
    project_id: str | None,
    input_doc: Mapping[str, Any],
    *,
    documents: bool = True,
    spec: AgentSpec | None = None,
) -> dict[str, Any]:
    """`input_doc` with the project's facts put in, for a class that asks for them. With no
    store or no project, only what a caller may never set is removed. Without `documents`, as
    under a profile that refuses attached documents, no attached document is given: neither a
    `Message`'s list of them nor a `DraftRequest`'s text of them."""
    filled = dict(input_doc)
    schema_class = filled.get("schema_class")
    if store is None or project_id is None:
        if schema_class == MESSAGE:
            for slot in MESSAGE_PROJECT_SLOTS:
                filled.pop(slot, None)
        elif schema_class == DRAFT_REQUEST:
            filled.pop("redraft_document", None)
        return filled
    if schema_class == MESSAGE:
        summary = store.summary(project_id)
        where = summary["progress"]
        _put(
            filled,
            {
                "project_inventory": summarise(store, project_id, summary["inventory"]),
                "project_entry": where["entry"],
                # Left out while every step is open, as `project_entry` is until one is chosen.
                "project_progress": [
                    {"step_id": step_id, "step_state": state}
                    for step_id, state in where["steps"].items()
                ]
                or None,
                "project_title": summary["title"],
                # False while the project is untitled too: the model may name it.
                "project_title_by_researcher": summary["title_source"] == TITLE_BY_RESEARCHER,
                # Left out while the project holds none, as `project_inventory` is.
                "project_documentation": (store.documentation(project_id) or None)
                if documents
                else None,
                # Absent until an entry point is recorded, as `project_entry` is.
                "project_entry_by_researcher": (
                    where["entry_source"] == ENTRY_BY_RESEARCHER
                    if where["entry_source"] is not None
                    else None
                ),
                # Left out while nobody in the project kept any.
                "project_researchers": store.researchers(project_id),
                # Left out while nobody in the project decided any.
                "project_decisions": store.decisions(project_id),
                # Left out until a researcher chooses one.
                "project_repository": chosen(summary["repository"]),
                # Left out while the project holds no drafted document.
                "project_drafts": drafts(store.events(project_id)) or None,
                # Left out while no setup question beside the entry question is answered.
                "project_intake": intake_answers(where["decisions"]) or None,
            },
        )
    elif schema_class == DRAFT_REQUEST:
        _put(
            filled,
            {
                "inventory": store.inventory(project_id),
                "requirements": store.requirements(project_id),
                "metadata_record": store.metadata_record(project_id),
                "current_version": _current(store, project_id, filled),
                # Only answers a person recorded may be placed as supplied.
                "draft_answers": _answers(store, project_id, filled.get("document_kind")),
                # Offered as suggestions only, never placed (docs/specs/drafting.md, invariant 7).
                "shared_answers": _answers(
                    store, project_id, filled.get("document_kind"), shared=True
                ),
                "researchers": store.researchers(project_id),
                "project_documents": _documents(store, project_id) if documents else None,
                # Only facts a person decided, never a proposal.
                "project_decisions": store.decisions(project_id),
            },
        )
    elif schema_class == FILE_INVENTORY:
        held = store.inventory(project_id)
        if held is not None:
            return dict(held)
    elif slots := agent_slots(spec, schema_class):
        # An agent's own class that mixes in a core slot is filled by that slot's name.
        _put(filled, _agent_facts(store, project_id, slots, documents=documents))
    return filled


def _agent_facts(
    store: FactSource, project_id: str, slots: frozenset[str], *, documents: bool
) -> dict[str, Any]:
    """The values of the core `slots` an agent's own input class mixes in, None for one the
    project has no value for."""
    facts: dict[str, Any] = {}
    if "project_documents" in slots:
        facts["project_documents"] = _documents(store, project_id) if documents else None
    if "project_decisions" in slots:
        facts["project_decisions"] = store.decisions(project_id)
    if "project_repository" in slots:
        facts["project_repository"] = chosen(store.summary(project_id)["repository"])
    if "project_metadata_draft" in slots:
        facts["project_metadata_draft"] = store.current_version(
            project_id, DocumentKind.METADATA_RECORD
        )
    if "project_metadata_approved" in slots:
        facts["project_metadata_approved"] = store.metadata_record(project_id)
    return facts


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
    `GivenProjectRepository` and `GivenProjectMetadataRecord`; empty for a core class, which
    `give` fills by name, or one the agent does not accept."""
    if spec is None or schema_class in CORE_CLASSES:
        return frozenset()
    accepted = spec.accepted(str(schema_class))
    declared = set(accepted.json_schema.get("properties", {})) if accepted else set()
    return frozenset(declared & set(AGENT_INPUT_SLOTS))


def refusal(
    store: FactSource | None, project_id: str | None, filled: Mapping[str, Any]
) -> str | None:
    """Why the conductor refuses to run `filled`, an input `give` returned for `project_id`: a
    `DraftRequest` naming a `redraft_document` that is not the project's, or is of another kind.
    None if nothing is refused."""
    named = filled.get("redraft_document")
    if store is None or project_id is None or named is None:
        return None
    try:
        store.current_version(project_id, DocumentKind(str(filled.get("document_kind"))), named)
    except ValueError as exc:  # ProjectError, or a kind that is not one
        return f"redraft_document {named!r}: {exc}"
    return None


def given(
    store: FactSource | None, project_id: str | None, filled: Mapping[str, Any]
) -> frozenset[str]:
    """The classes of project content in `filled`, an input `give` returned for `project_id`.
    Empty outside a project."""
    if store is None or project_id is None:
        return frozenset()
    schema_class = filled.get("schema_class")
    if schema_class == FILE_INVENTORY:
        return frozenset({INVENTORY}) if store.inventory(project_id) is not None else frozenset()
    # An agent's own class holds what its mixins ask for (`give`).
    slots = CONTENT_SLOTS.get(str(schema_class), AGENT_CONTENT_SLOTS)
    return frozenset(kind for slot, kind in slots if filled.get(slot))


def left_out(filled: Mapping[str, Any]) -> frozenset[str]:
    """The classes of project content in `filled` left out, rather than refused, where the
    profile keeps them from an agent: researcher facts always, a `Message`'s decided facts and
    chosen repository, which an orchestrator does not need to draft anything, and a
    `DraftRequest`'s attached documents, from which a drafter only suggests answers."""
    if filled.get("schema_class") == MESSAGE:
        return frozenset({RESEARCHER, DECISIONS})
    return frozenset({RESEARCHER, DOCUMENTATION})


def leave_out(filled: Mapping[str, Any], classes: frozenset[str]) -> dict[str, Any]:
    """`filled` without the content of `classes` that `left_out` says may be left out: its
    researcher facts, a `Message`'s decided facts and chosen repository, and a `DraftRequest`'s
    attached documents but none of its other documentation."""
    kept = dict(filled)
    out = classes & left_out(filled)
    if RESEARCHER in out:
        for slot in RESEARCHER_SLOTS:
            kept.pop(slot, None)
    if DECISIONS in out:
        kept.pop("project_decisions", None)
        kept.pop("project_repository", None)
    if DOCUMENTATION in out:
        kept.pop("project_documents", None)
    return kept


def _documents(store: FactSource, project_id: str) -> list[dict[str, Any]]:
    """Each document the project holds, with its text, as a `ProjectDocument`."""
    found = []
    for summary in store.documentation(project_id):
        text = store.documentation_text(project_id, summary["documentation_digest"])
        if text is not None:
            found.append({**summary, "documentation_text": text})
    return found


def summarise(
    store: FactSource, project_id: str, recorded: Mapping[str, Any] | None
) -> dict[str, Any] | None:
    """What the project's inventory is, as an `InventorySummary`, or None if it holds none.
    `recorded` is what the project's summary says of the inventory added last: its digest and
    file count are the ones its `inventory_added` event recorded, so the inventory is not hashed
    again on every turn."""
    held = store.inventory(project_id) if recorded is not None else None
    if recorded is None or held is None:
        return None
    summary = {
        "inventory_digest": recorded["digest"],
        "inventory_file_count": recorded["file_count"],
        "inventory_tool": held["inventory_tool"],
        "inventory_tool_version": held["inventory_tool_version"],
        "inventory_made_at": held["inventory_made_at"],
        **revision(store.events(project_id)),
    }
    if held.get("inventory_limitations"):
        summary["inventory_limitations"] = list(held["inventory_limitations"])
    files = held.get("inventory_files") or []
    summary["inventory_formats"] = formats(files)
    summary["inventory_table_count"] = sum(1 for file in files if file.get("file_fields"))
    return summary


def formats(files: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """`files` grouped by media type, as `InventoryFormat`s, the group with the most bytes first:
    the grouping of the app's inventory view (`inventory/browser/src/summary.ts`), so that an agent
    is told the kinds of files a researcher sees there (#1287)."""
    groups: dict[str | None, dict[str, Any]] = {}
    for file in files:
        group = groups.setdefault(
            file.get("file_media_type"), {"count": 0, "bytes": 0, "ids": set()}
        )
        group["count"] += 1
        group["bytes"] += file.get("file_size") or 0
        group["ids"].update(file.get("file_pronom_ids") or [])
    ordered = sorted(groups.items(), key=lambda kv: (-kv[1]["bytes"], -kv[1]["count"]))
    found = []
    for media_type, group in ordered:
        entry: dict[str, Any] = {"format_file_count": group["count"]}
        if media_type is not None:
            entry["format_media_type"] = media_type
        if group["ids"]:
            entry["format_pronom_ids"] = sorted(group["ids"])
        found.append(entry)
    return found


def _current(
    store: FactSource, project_id: str, filled: Mapping[str, Any]
) -> dict[str, Any] | None:
    """The version a drafter regenerates. None for a kind that is not one, which the request's
    validation then refuses, and for a `redraft_document` that `refusal` refuses."""
    try:
        return store.current_version(
            project_id,
            DocumentKind(str(filled.get("document_kind"))),
            filled.get("redraft_document"),
        )
    except ValueError:  # ProjectError, or a kind that is not one
        return None


def _answers(
    store: FactSource, project_id: str, kind: Any, *, shared: bool = False
) -> list[dict[str, Any]] | None:
    """The recorded answers for a drafter of `kind`, or, `shared`, those recorded for documents
    of other kinds on a shared field. None for a kind that is not one, which the request's
    validation then refuses."""
    try:
        document_kind = DocumentKind(kind)
    except ValueError:
        return None
    if shared:
        return store.shared_answers(project_id, document_kind)
    return store.answers(project_id, document_kind)


def intake_answers(decisions: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The intake's answered questions beside the entry question, as `IntakeAnswer`s, from a
    project's decision points (`dd_harness.progress.decisions`): only those asked from the
    project's entry point, so that the model is told only what still bears on its steps."""
    return [
        {
            "intake_question_id": d["question_id"],
            "intake_question_prompt": d["prompt"],
            "intake_answer_labels": d["answer_labels"],
        }
        for d in decisions
        if d["asked"] and d["answer_labels"]
    ]


def _put(filled: dict[str, Any], facts: Mapping[str, Any]) -> None:
    """Set each slot to its value, or remove it where the value is None."""
    for slot, value in facts.items():
        if value is None:
            filled.pop(slot, None)
        else:
            filled[slot] = value
