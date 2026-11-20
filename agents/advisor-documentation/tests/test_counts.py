"""advisor.documentation's counts: the files at the top level and in each folder are counted by
rule, given to the model, and a paragraph that states another count is not used
(docs/specs/drafting.md, invariant 4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_prose import StubClient, draft, sample, template_draft

from dd_agent_advisor_documentation.counts import check_counts, layout
from dd_agent_advisor_documentation.prose import ProseReply, check
from dd_agent_advisor_documentation.testing import prose_reply
from dd_sdk.contract.models import Document, DraftRequest, OutcomeStatus

# The shape of sample-data dataset E's inherited folder: two files at the top level, the rest in
# subfolders, one of them nested (#1281).
INHERITED = [
    "interview_log.csv",
    "methods_note_email.txt",
    "transcripts/p01.txt",
    "transcripts/p02.txt",
    "transcripts/audio/p01.wav",
    "consent/forms.pdf",
]
FACTS = {"file_count": len(INHERITED), "table_count": 1, **layout(INHERITED)}


def test_the_files_at_the_top_level_and_in_each_folder_are_counted_by_rule() -> None:
    counted = layout(INHERITED)
    assert counted["top_level_file_count"] == 2
    assert counted["folders"] == [
        {"path": "consent", "file_count": 1},
        {"path": "transcripts", "file_count": 3},
        {"path": "transcripts/audio", "file_count": 1},
    ]
    assert counted["folder_count"] == len(counted["folders"])


@pytest.mark.parametrize(
    "paragraph",
    [
        "There are 4 files in subfolders and three more at the top level.",
        "Three files sit at the top level of the folder.",
        "The folder holds seven files.",
        "Of these, 5 tables share a field.",
    ],
)
def test_a_count_the_facts_do_not_give_is_not_used(paragraph: str) -> None:
    assert check_counts(paragraph, FACTS) is not None
    prose = check(ProseReply.model_validate_json(prose_reply({"overview": paragraph})), FACTS, [])
    assert prose.overview is None and len(prose.dropped) == 1


@pytest.mark.parametrize(
    "paragraph",
    [
        "The dataset has 6 files: two at the top level and the rest in 3 folders.",
        "Of the six files, 2 sit at the top level.",
        "The `transcripts` folder holds three files, one of them in `transcripts/audio`.",
        "Each one of the 6 files is listed below.",
    ],
)
def test_a_count_the_facts_give_is_kept(paragraph: str) -> None:
    assert check_counts(paragraph, FACTS) is None


def test_the_model_is_given_the_counts_and_a_miscount_falls_back_to_the_template(
    runs_dir: Path,
) -> None:
    asked = sample("soil-survey.readme.draft.json")
    assert asked.inventory is not None
    # The sample's five files, moved to the first five of the inherited folder's paths.
    files = asked.inventory.inventory_files
    renamed = [
        f.model_copy(update={"file_path": p}) for f, p in zip(files, INHERITED, strict=False)
    ]
    inventory = asked.inventory.model_copy(update={"inventory_files": renamed})
    asked = DraftRequest.model_validate(
        {**asked.model_dump(mode="json"), "inventory": inventory.model_dump(mode="json")}
    )
    miscount = "The folder has 5 files, two in subfolders and three more at the top level."
    client = StubClient({"overview": miscount})
    env, _ = draft(runs_dir, client, asked)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    facts = json.loads(client.sent[0]["messages"][0]["content"].split("Facts:\n", 1)[1])
    assert facts["top_level_file_count"] == 2
    document = env.payload_as(Document)
    assert miscount not in document.document_text
    assert document.document_text == template_draft(runs_dir, asked).document_text
    assert "overview: says 'three' at the top level" in env.outcome.statement
