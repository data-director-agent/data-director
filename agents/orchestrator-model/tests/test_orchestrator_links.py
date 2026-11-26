"""A reply links a source only by an address the model was shown: each delegated result lists its
sources' web addresses for the model to link by, and a link to any other address is shown as plain
text rather than as a citation (docs/specs/orchestration.md, Boundaries and contracts)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from test_orchestrator import ScriptedModel, call, conductor, invoke, say

from dd_agent_orchestrator_model import links
from dd_agent_orchestrator_model.prompt import SYSTEM_PROMPT
from dd_sdk.contract.models import Envelope, EvidenceItem, Reply

pytestmark = pytest.mark.requirement("DD-CONVERSATION")

POLICY = "https://funder.example/policies/data"
SEEN = {POLICY}


def test_the_prompt_asks_for_links_only_to_addresses_it_was_given() -> None:
    assert "cited_sources" in SYSTEM_PROMPT
    assert "never write, complete or guess one" in SYSTEM_PROMPT


def test_a_link_to_a_shown_address_is_kept() -> None:
    text = f"The [funder's policy]({POLICY}) asks for open data, and <{POLICY}> says so."
    assert links.checked(text, SEEN) == text


def test_a_shown_address_matches_despite_a_final_slash_or_full_stop() -> None:
    assert links.checked(f"See {POLICY}/.", SEEN) == f"See {POLICY}/."


def test_a_link_to_an_address_never_shown_keeps_its_label_and_is_not_a_link() -> None:
    made_up = "https://funder.example/made-up"
    checked = links.checked(f"The [funder's policy]({made_up}) asks for open data.", SEEN)
    assert checked == "The funder's policy asks for open data."
    assert made_up not in checked


def test_a_bare_or_angled_address_never_shown_becomes_inline_code() -> None:
    made_up = "https://funder.example/made-up"
    assert links.checked(f"See {made_up}.", SEEN) == f"See `{made_up}`."
    assert links.checked(f"See <{made_up}>.", SEEN) == f"See `{made_up}`."


def test_an_address_in_code_is_left_as_written() -> None:
    text = "Run `curl https://funder.example/made-up` first."
    assert links.checked(text, SEEN) == text


def test_the_addresses_in_text_are_found_without_sentence_punctuation() -> None:
    assert links.addresses_in(f"See ({POLICY}), or {POLICY}/.") == {POLICY}


def _envelope(runs_dir: Path) -> Envelope:
    model = ScriptedModel([say("Which dataset do you mean?")])
    envelope: Envelope = invoke(conductor(runs_dir, model))
    return envelope


def test_a_result_lists_the_web_addresses_of_its_sources_and_not_other_uris(
    runs_dir: Path,
) -> None:
    def item(
        source_id: str, uri: str | None, content: dict[str, Any] | None = None
    ) -> EvidenceItem:
        return EvidenceItem(
            source_id=source_id,
            source_uri=uri,
            canonicalisation="test",
            content_hash="0" * 64,
            content=content,
        )

    cited = _envelope(runs_dir).model_copy(
        update={
            "evidence": [
                item("policy", POLICY, {"title": "Funder data policy"}),
                item("snapshot", "/data/snapshot.jsonl"),
                item("unaddressed", None),
            ]
        }
    )
    assert links.cited_sources(cited) == [
        {"source_id": "policy", "url": POLICY, "title": "Funder data policy"}
    ]
    assert links.shown_addresses([cited]) == SEEN


def test_the_model_is_sent_each_results_sources_beside_its_payload(runs_dir: Path) -> None:
    model = ScriptedModel([call(("example_hello", {"greeted_name": "Ada"})), say("Hello, Ada!")])
    invoke(conductor(runs_dir, model))
    [result] = model.sent[1]["messages"][-1]["results"]
    assert json.loads(result["content"])["cited_sources"] == []


def test_a_reply_that_links_an_address_nobody_gave_it_shows_no_link(runs_dir: Path) -> None:
    made_up = "https://funder.example/made-up"
    model = ScriptedModel([say(f"The [policy]({made_up}) asks for open data.")])
    env = invoke(conductor(runs_dir, model))
    assert env.payload_as(Reply).reply_text == "The policy asks for open data."


def test_a_reply_may_link_an_address_the_researcher_wrote(runs_dir: Path) -> None:
    reply = f"I cannot open [your policy]({POLICY}), but I can ask the policy adviser."
    env = invoke(
        conductor(runs_dir, ScriptedModel([say(reply)])), f"My funder's policy is at {POLICY}"
    )
    assert env.payload_as(Reply).reply_text == reply
