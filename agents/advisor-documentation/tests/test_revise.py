"""advisor.documentation revising a README as a person asked (docs/specs/drafting.md,
invariant 12): only prose changes, every gap and value a person gave is kept, and what the model
writes is checked against the facts, the README and the request."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from dd_agent_advisor_documentation.agent import DocumentationEditor
from dd_agent_advisor_documentation.prose import SYSTEM_PROMPT, ModelWriter
from dd_agent_advisor_documentation.revise import REVISE_PROMPT, blocks
from dd_agent_advisor_documentation.testing import prose_reply, redraft, suggestion_reply
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.contract.models import (
    CurrentVersion,
    Derivation,
    Document,
    DocumentKind,
    DraftRequest,
    Envelope,
    OutcomeStatus,
    ReasonCode,
    VersionState,
)
from dd_sdk.model import ModelRequest
from dd_sdk.testing import FakeModel

SAMPLES = Path(__file__).with_name("data")
GAP = re.compile(r"<!-- dd:gap (q-[0-9a-f]{16}) -->")
FILES = "The dataset holds the tables `data/readings.csv` and `data/sites.tsv`, among other files."
SHORTER = "The tables are `data/readings.csv` and `data/sites.tsv`."
ASK = "Shorten the Files paragraph, and say that sampling was monthly from 2019 to 2021."


def asked() -> DraftRequest:
    return redraft(
        DraftRequest.model_validate_json(
            (SAMPLES / "soil-survey.readme-with-record.draft.json").read_text(encoding="utf-8")
        )
    )


def invoke(runs: Path, model: FakeModel, draft: DraftRequest) -> Envelope:
    conductor = make_conductor(runs, DocumentationEditor(writer=ModelWriter(model)))
    return conductor.invoke(request("advisor.documentation", draft), acting_for=TEST_PRINCIPAL)


@pytest.fixture
def current(tmp_path: Path) -> Document:
    """A README drafted with a paragraph of prose in its Files section."""
    model = FakeModel(
        lambda r: prose_reply({"Files": FILES}) if r.system == SYSTEM_PROMPT else "{}"
    )
    return invoke(tmp_path / "first", model, asked()).payload_as(Document)


def revising(current: Document, instruction: str = ASK, **change: Any) -> DraftRequest:
    """The request a project makes once a person asked for `current` to be revised."""
    draft = asked()
    assert draft.current_version is not None
    version = CurrentVersion(
        version_ref=draft.current_version.version_ref,
        document_title="README",
        media_type="text/markdown",
        document_text=current.document_text,
        version_state=VersionState.PROPOSED,
        revision_request=instruction,
    )
    return draft.model_copy(update={"revise": True, "current_version": version, **change})


def replying(
    paragraphs: Mapping[str, str] | None = None, added: Mapping[str, str] | None = None
) -> FakeModel:
    """A model that revises as given, by the text of the paragraph it changes, and suggests
    nothing."""

    def reply(sent: ModelRequest) -> str:
        if sent.system != REVISE_PROMPT:
            return suggestion_reply({})
        content = sent_text(sent)
        offered = json.loads(
            content.split("Paragraphs you may change: ")[1].split("\n\nSections you may add")[0]
        )
        by_text = {p["text"]: p["paragraph"] for p in offered}
        return json.dumps(
            {
                "paragraphs": [
                    {"paragraph": by_text.get(old, old), "text": new}
                    for old, new in (paragraphs or {}).items()
                ],
                "added": [{"section": s, "text": t} for s, t in (added or {}).items()],
            }
        )

    return FakeModel(reply)


def sent_text(sent: ModelRequest) -> str:
    """The text of the one user message a revision sends."""
    (message,) = sent.messages
    assert isinstance(message, Mapping)
    return str(message["content"])


@pytest.mark.requirement("R5")
def test_a_revision_changes_only_prose_and_keeps_every_gap(
    tmp_path: Path, current: Document
) -> None:
    methods = "Sampling was monthly from 2019 to 2021."
    model = replying({FILES: SHORTER}, {"Methods": methods})

    env = invoke(tmp_path / "runs", model, revising(current))

    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    revised = env.payload_as(Document)
    assert SHORTER in revised.document_text and FILES not in revised.document_text
    # A number the person's request gives counts as given by them.
    assert methods in revised.document_text
    assert GAP.findall(revised.document_text) == GAP.findall(current.document_text)
    assert {q.question_id for q in revised.document_questions} == set(
        GAP.findall(current.document_text)
    )
    kept = [b.text for b in blocks(current.document_text, ()) if not b.revisable]
    assert all(block in revised.document_text for block in kept)
    assert revised.revises is not None
    assert revised.document_derivation == Derivation.MODEL
    assert revised.document_stage == "draft"


@pytest.mark.requirement("R5")
def test_the_model_is_given_the_request_as_its_instruction_and_the_readme_as_data(
    tmp_path: Path, current: Document
) -> None:
    model = replying({FILES: SHORTER})
    invoke(tmp_path / "runs", model, revising(current))
    sent = model.sent[0]
    assert sent.system == REVISE_PROMPT
    content = sent_text(sent)
    assert content.startswith(f"The researcher's request:\n{ASK}")
    assert f"<readme>\n{current.document_text}</readme>" in content


@pytest.mark.requirement("R5")
@pytest.mark.parametrize(
    "invented",
    [
        "The tables `data/readings.csv` and `data/sites.tsv` hold 4000 rows.",
        "See https://example.org/protocol for the tables.",
        "## Files\n\nA heading of its own.",
    ],
)
def test_a_paragraph_that_names_what_nothing_gives_keeps_the_current_text(
    tmp_path: Path, current: Document, invented: str
) -> None:
    env = invoke(tmp_path / "runs", replying({FILES: invented}), revising(current))
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.INSUFFICIENT_INPUT
    assert env.payload is None


@pytest.mark.requirement("R5")
def test_a_value_a_person_gave_and_a_gap_are_never_offered(current: Document) -> None:
    draft = revising(current)
    assert draft.current_version is not None
    record_description = next(
        b.text
        for b in blocks(current.document_text, ())
        if b.section == "Description" and not b.text.startswith("#")
    )
    found = blocks(current.document_text, [record_description])
    revisable = [b.text for b in found if b.revisable]
    assert FILES in revisable
    assert record_description not in revisable
    assert not any("dd:gap" in text or text.startswith(("#", "|", "- ")) for text in revisable)


@pytest.mark.requirement("R5")
def test_a_gap_or_a_table_cannot_be_rewritten(tmp_path: Path, current: Document) -> None:
    gap = next(b.text for b in blocks(current.document_text, ()) if "dd:gap" in b.text)
    env = invoke(tmp_path / "runs", replying({gap: "Sampling was monthly."}), revising(current))
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert "not a paragraph it was offered" in (env.outcome.statement or "")


@pytest.mark.requirement("R5")
def test_without_a_model_nothing_is_revised(tmp_path: Path, current: Document) -> None:
    conductor = make_conductor(tmp_path / "runs", DocumentationEditor())
    env = conductor.invoke(
        request("advisor.documentation", revising(current)), acting_for=TEST_PRINCIPAL
    )
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.CAPABILITY_NOT_IMPLEMENTED
    assert env.payload is None


@pytest.mark.requirement("R5")
def test_only_a_readme_with_a_change_asked_of_it_is_revised(
    tmp_path: Path, current: Document
) -> None:
    model = replying({FILES: SHORTER})
    other_kind = revising(current, document_kind=DocumentKind.DATA_DICTIONARY)
    unasked = revising(current).model_copy(update={"current_version": asked().current_version})
    for draft, reason in (
        (other_kind, ReasonCode.OUTSIDE_AGENT_SCOPE),
        (unasked, ReasonCode.INSUFFICIENT_INPUT),
    ):
        env = invoke(tmp_path / "runs", model, draft)
        assert env.outcome.status == OutcomeStatus.ABSTAINED
        assert env.outcome.reason_code == reason
    assert model.sent == []
