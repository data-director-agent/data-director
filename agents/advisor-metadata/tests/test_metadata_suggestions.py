"""advisor.metadata's model suggests values beside the record's questions, never in the record
(docs/specs/drafting.md, invariant 7): a suggestion becomes part of the record only when a person
records it as their answer."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from test_metadata_agent import sample

from dd_agent_advisor_metadata.agent import MetadataLibrarian
from dd_agent_advisor_metadata.factory import SWITCH, build
from dd_agent_advisor_metadata.suggest import (
    MAX_SUGGESTION,
    Ask,
    ModelSuggester,
    SuggestionReply,
    TemplateSuggester,
    check_suggestions,
)
from dd_agent_advisor_metadata.testing import suggestion_reply
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.contract.models import (
    Derivation,
    Document,
    DocumentQuestion,
    DraftAnswer,
    DraftRequest,
    Envelope,
    OutcomeStatus,
)
from dd_sdk.credentials import ConfigError
from dd_sdk.model_anthropic import AnthropicModel

MODEL = "claude-test"
TITLE = "titles[0].title"
ABSTRACT = "descriptions[0].description"


class StubClient:
    """An Anthropic client that keeps what it was sent and replies with suggestions by
    question, worked out from the questions it was sent by `reply`, or with raw text."""

    def __init__(self, reply: Any) -> None:
        self.reply = reply
        self.sent: list[dict[str, Any]] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs: Any) -> SimpleNamespace:
        self.sent.append(kwargs)
        content = kwargs["messages"][0]["content"]
        asked = json.loads(content.split("\n\nFacts:\n")[0].split(":\n", 1)[1])
        text = self.reply if isinstance(self.reply, str) else suggestion_reply(self.reply(asked))
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=100, output_tokens=40),
            model=MODEL,
        )


def suggest_every(asked: list[dict[str, Any]]) -> dict[str, str | None]:
    return {q["question_id"]: f"Suggested {q['property']}" for q in asked}


def draft(
    runs_dir: Path, client: StubClient | None, asked: DraftRequest | None = None
) -> tuple[Envelope, bool]:
    suggester = (
        TemplateSuggester()
        if client is None
        else ModelSuggester(AnthropicModel(MODEL, client=client))  # type: ignore[arg-type]
    )
    conductor = make_conductor(runs_dir, MetadataLibrarian(suggester=suggester))
    env = conductor.invoke(
        request("advisor.metadata", asked or sample()), acting_for=TEST_PRINCIPAL
    )
    return env, conductor.grounding_reports[env.invocation_id].passed


def by_path(document: Document) -> dict[str | None, DocumentQuestion]:
    return {q.gap_property: q for q in document.document_questions}


@pytest.mark.requirement("DD-GROUNDING-MODE", "DD-GROUNDED-PAYLOAD")
def test_suggestions_are_offered_beside_the_questions_and_never_in_the_record(
    runs_dir: Path,
) -> None:
    template, _ = draft(runs_dir, None)
    client = StubClient(suggest_every)
    env, grounded = draft(runs_dir, client)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert grounded
    document, plain = env.payload_as(Document), template.payload_as(Document)

    # The record's text is the template's, byte for byte, and so is how it came about.
    assert document.document_text == plain.document_text
    assert document.document_derivation == Derivation.TEMPLATE
    assert [q.question_id for q in document.document_questions] == [
        q.question_id for q in plain.document_questions
    ]
    questions = by_path(document)
    assert questions[TITLE].suggested_answer == "Suggested titles"
    assert questions[TITLE].suggestion_derivation == Derivation.MODEL
    assert questions[ABSTRACT].suggested_answer == "Suggested descriptions"
    assert env.telemetry.model_id == MODEL


def test_only_the_properties_the_rule_table_marks_are_offered_to_the_model(
    runs_dir: Path,
) -> None:
    client = StubClient(suggest_every)
    env, _ = draft(runs_dir, client)
    [sent] = client.sent
    content = sent["messages"][0]["content"]
    offered = {
        q["property"] for q in json.loads(content.split("\n\nFacts:\n")[0].split(":\n", 1)[1])
    }
    assert offered <= {"titles", "descriptions", "subjects", "language"}
    questions = by_path(env.payload_as(Document))
    for never in ("creators[0].name", "rightsList[0].rights", "dates[0].date"):
        assert questions[never].suggested_answer is None
    # An entry from a named vocabulary is chosen from it, not suggested (TODO(#703)).
    scheme = next(
        q for p, q in questions.items() if p and "subjects" in p and "Scheme" in q.question_prompt
    )
    assert scheme.suggested_answer is None


def test_the_model_sees_the_inventory_structure_but_never_an_answer(runs_dir: Path) -> None:
    template, _ = draft(runs_dir, None)
    title = by_path(template.payload_as(Document))[TITLE]
    answer = DraftAnswer(answered_question=title.question_id, answer_text="Private working title")
    client = StubClient(suggest_every)
    env, _ = draft(runs_dir, client, sample().model_copy(update={"draft_answers": [answer]}))
    [sent] = client.sent
    content = sent["messages"][0]["content"]
    assert "Private working title" not in content
    assert "data/readings.csv" in content and "nitrate_mg_kg" in content
    # The answered title is placed and no longer asked, so nothing is suggested for it.
    document = env.payload_as(Document)
    assert TITLE not in by_path(document)
    assert json.loads(document.document_text)["titles"] == [{"title": "Private working title"}]


def test_a_confirmed_suggestion_becomes_an_answer(runs_dir: Path) -> None:
    env, _ = draft(runs_dir, StubClient(suggest_every))
    title = by_path(env.payload_as(Document))[TITLE]
    assert title.suggested_answer is not None
    confirmed = DraftAnswer(answered_question=title.question_id, answer_text=title.suggested_answer)
    again, _ = draft(
        runs_dir,
        StubClient(suggest_every),
        sample().model_copy(update={"draft_answers": [confirmed]}),
    )
    record = json.loads(again.payload_as(Document).document_text)
    assert record["titles"] == [{"title": "Suggested titles"}]


def test_a_reply_that_does_not_match_is_not_used(runs_dir: Path) -> None:
    template, _ = draft(runs_dir, None)
    env, _ = draft(runs_dir, StubClient("not JSON"))
    assert env.outcome.status == OutcomeStatus.SUCCEEDED
    document = env.payload_as(Document)
    assert document.document_questions == template.payload_as(Document).document_questions


def asks(*paths: str) -> list[Ask]:
    return [Ask(f"q-{i:016x}", path, path.split("[")[0], "?") for i, path in enumerate(paths)]


def replied(answers: Mapping[str, str | None]) -> SuggestionReply:
    return SuggestionReply.model_validate_json(suggestion_reply(answers))


def test_an_invented_identifier_or_an_unasked_question_is_dropped() -> None:
    offered = asks(TITLE, ABSTRACT, "subjects[0].subject")
    title, abstract, subject = (a.question_id for a in offered)
    facts = {"files": [{"path": "data/readings.csv"}]}
    reply = replied(
        {
            title: "Soil readings",
            abstract: "See https://example.org/soil for the methods.",
            subject: "soil\n- chemistry",
            "q-" + "f" * 16: "Unasked",
        }
    )
    got = check_suggestions(reply, facts, offered)
    assert dict(got.answers) == {title: "Soil readings"}
    assert len(got.dropped) == 3
    long = check_suggestions(replied({title: "x" * (MAX_SUGGESTION + 1)}), facts, offered)
    assert not long.answers and long.dropped


def test_the_template_build_suggests_nothing_and_needs_no_key() -> None:
    agent = build({SWITCH: "template"})
    assert isinstance(agent.suggester, TemplateSuggester)
    assert agent.spec.models == ()


def test_the_model_suggester_is_on_by_default_and_says_how_to_run_without_it() -> None:
    with pytest.raises(ConfigError, match=f"{SWITCH}=template"):
        build({})
    agent = build({"ANTHROPIC_API_KEY": "sk-test"})
    assert isinstance(agent.suggester, ModelSuggester)
    assert agent.spec.models


def test_the_model_suggester_is_declared_on_the_card() -> None:
    agent = build({SWITCH: "model", "DD_MODEL_ID": MODEL, "ANTHROPIC_API_KEY": "sk-test"})
    assert isinstance(agent.suggester, ModelSuggester)
    (use,) = agent.spec.models
    assert (use.provider, use.model) == ("anthropic", MODEL)


def test_an_unknown_suggester_is_a_configuration_error() -> None:
    with pytest.raises(ConfigError):
        build({SWITCH: "gpt"})
