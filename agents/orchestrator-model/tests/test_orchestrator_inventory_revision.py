"""After the researcher leaves files out in Edit inventory, the model is told so, and told the
latest version of each draft, so that it does not say a file is still listed when the latest
draft has dropped it (#1280).

Edit inventory adds a new inventory without the files left out (`inventory/browser/src/omit.ts`);
the next draft follows it. The model knew of the first draft only from its own earlier reply, so
each turn now opens with notes from the project record: the inventory replaced an earlier one,
and which version of each draft is the latest and whether it follows the current inventory."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from test_orchestrator import ScriptedModel, call, say
from test_orchestrator_naming import turn

from dd_agent_example_hello.agent import HelloWorld
from dd_agent_orchestrator_model.agent import ModelOrchestrator
from dd_agent_orchestrator_model.notes import drafts_note, inventory_note
from dd_agent_orchestrator_model.prompt import SYSTEM_PROMPT
from dd_harness.conductor import Conductor
from dd_harness.projects import ProjectStore
from dd_harness.testing import TEST_PRINCIPAL, DocumentStub, make_conductor
from dd_sdk.contract.models import (
    DocumentKind,
    DraftSummary,
    FileInventory,
    IdentificationMethod,
    InventoryFile,
    InventorySummary,
    Message,
    OutcomeStatus,
    VersionState,
)

pytestmark = pytest.mark.requirement("DD-CONVERSATION")

DRAFTER = "stub_document__DraftRequest"
CONSENT = "consent/signed_consent_form.pdf"
DUPLICATE = "transcripts/P01 (copy).txt"
KEPT = "transcripts/P01.txt"
LEFT_OUT = (
    "Before this inventory was added, the researcher left out 2 files. That they are not listed "
    "here does not mean they are not in the dataset."
)


def inventory(*paths: str, limitations: list[str] | None = None) -> dict[str, Any]:
    made = FileInventory(
        inventory_tool="dd-inventory",
        inventory_tool_version="0.1.0",
        inventory_made_at=datetime(2026, 11, 20, tzinfo=UTC),
        inventory_files=[
            InventoryFile(
                file_path=path,
                file_size=10,
                file_sha256="a" * 64,
                file_media_type="text/plain",
                file_pronom_ids=["x-fmt/111"],
                file_identified_by=IdentificationMethod.EXTENSION,
            )
            for path in paths
        ],
        inventory_limitations=limitations or [],
    )
    return made.model_dump(mode="json", exclude_none=True)


def in_project(tmp_path: Path, model: Any) -> tuple[Conductor, ProjectStore, str, str]:
    """A conductor running the orchestrator and a README drafter over a project that holds a
    three-file inventory, and a conversation in it."""
    conductor = make_conductor(
        tmp_path / "runs", ModelOrchestrator(model), HelloWorld(), DocumentStub()
    )
    projects = ProjectStore(tmp_path / "projects")
    conductor.projects = projects
    project = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test", title="Interviews")
    projects.add_inventory(
        project, inventory(CONSENT, DUPLICATE, KEPT), acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    started = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="test")
    return conductor, projects, project, started


def opening(sent: dict[str, Any]) -> str:
    """The current message the model was sent, with the harness's notes."""
    return str(sent["messages"][-1]["content"])


def drafted(sent: dict[str, Any]) -> dict[str, Any]:
    """The draft a drafter returned, as the model was sent it in a tool result."""
    [result] = sent["messages"][-1]["results"]
    payload: dict[str, Any] = json.loads(result["content"])["payload"]
    return payload


def test_after_files_are_left_out_the_next_turn_shows_the_new_inventory_and_draft(
    tmp_path: Path,
) -> None:
    readme = {"document_kind": "readme"}
    model = ScriptedModel(
        [
            call((DRAFTER, readme)),
            say("Here is a README. It lists the signed consent form: untick it."),
            call((DRAFTER, readme)),
            say("Here is the README again, from the inventory you saved."),
            say("The README is at version 2."),
        ]
    )
    conductor, projects, project, conversation_id = in_project(tmp_path, model)

    first = turn(conductor, conversation_id, "Draft a README.")
    assert first.outcome.status == OutcomeStatus.SUCCEEDED, first.outcome.statement
    assert "files=3" in drafted(model.sent[1])["document_text"]
    # Before anything is drafted there is no note of drafts, and the inventory is the first.
    assert "drafted document" not in opening(model.sent[0])
    assert "earlier inventory" not in opening(model.sent[0])

    # Edit inventory: the consent form and the duplicate are unticked and the inventory saved.
    projects.add_inventory(
        project, inventory(KEPT, limitations=[LEFT_OUT]), acted_for=TEST_PRINCIPAL, caused_by="t"
    )
    second = turn(conductor, conversation_id, "Please redraft the documents.")
    assert second.outcome.status == OutcomeStatus.SUCCEEDED, second.outcome.statement
    told = opening(model.sent[2])
    assert "The project holds an inventory of the dataset: 1 file" in told
    assert "in place of an earlier inventory of 3 files" in told
    assert "that change has taken effect" in told
    assert LEFT_OUT in told
    assert "readme v1 (proposed, drafted before the current inventory was added" in told
    # Nothing the researcher left out is named by the harness.
    assert CONSENT not in told and DUPLICATE not in told
    # Within the turn, the model has the new draft's text, version 2 of the same document.
    redraft = drafted(model.sent[3])
    assert "files=1" in redraft["document_text"]
    assert redraft["revises"]["version"] == 1

    third = turn(conductor, conversation_id, "Does the README still list the consent form?")
    assert third.outcome.status == OutcomeStatus.SUCCEEDED, third.outcome.statement
    told = opening(model.sent[4])
    assert "readme v2 (proposed, drafted from the current inventory)" in told
    assert "readme v1" not in told
    (document,) = projects.documents(project)
    assert [v["version"] for v in document["versions"]] == [1, 2]


def test_a_first_inventory_says_nothing_of_a_revision() -> None:
    held = InventorySummary(
        inventory_digest="d" * 64,
        inventory_file_count=3,
        inventory_tool="dd-inventory",
        inventory_tool_version="0.1.0",
        inventory_made_at=datetime(2026, 11, 20, tzinfo=UTC),
        inventory_added_at=datetime(2026, 11, 20, 9, tzinfo=UTC),
    )
    note = inventory_note(Message(message_text="Hi", project_inventory=held))
    assert note is not None
    assert "3 files" in note and "earlier inventory" not in note


@pytest.mark.parametrize(
    ("since", "said"),
    [
        (True, "readme v2 (approved, drafted from the current inventory)"),
        (False, "readme v2 (approved, drafted before the current inventory was added"),
        (None, "readme v2 (approved)"),
    ],
)
def test_the_drafts_note_names_the_latest_version_and_whether_it_follows_the_inventory(
    since: bool | None, said: str
) -> None:
    draft = DraftSummary(
        document_kind=DocumentKind.README,
        version=2,
        version_state=VersionState.APPROVED,
        drafted_since_inventory=since,
    )
    note = drafts_note(Message(message_text="Hi", project_drafts=[draft]))
    assert note is not None and said in note
    assert "only from its text in an agent's result in this turn" in note


def test_no_drafts_no_note() -> None:
    assert drafts_note(Message(message_text="Hi")) is None


def test_the_prompt_says_a_revised_inventory_has_taken_effect() -> None:
    assert "the researcher's change has taken effect: never say it has not" in SYSTEM_PROMPT
    assert "never from your memory of an earlier version" in SYSTEM_PROMPT
