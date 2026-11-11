"""advisor.documentation with a model: the README's prose is written from the project's facts
alone, checked before it is used, and never closes a gap (docs/specs/drafting.md)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from dd_agent_advisor_documentation.agent import DocumentationEditor
from dd_agent_advisor_documentation.factory import build
from dd_agent_advisor_documentation.prose import SYSTEM_PROMPT, AnthropicWriter, check
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.contract.models import (
    Derivation,
    Document,
    DraftAnswer,
    DraftRequest,
    Envelope,
    GroundingMode,
    OutcomeStatus,
)
from dd_sdk.credentials import ConfigError
from dd_sdk.testing import FakeModel

SAMPLES = Path(__file__).with_name("data")
MODEL = "claude-test"
GAP = re.compile(r"<!-- dd:gap (q-[0-9a-f]{16}) -->")

OVERVIEW = (
    "The dataset consists of 5 files, two of them tables: `data/readings.csv` and `data/sites.tsv`."
)
FILES = "The tables `data/readings.csv` and `data/sites.tsv` both have a field named `site`."


def sample(name: str) -> DraftRequest:
    return DraftRequest.model_validate_json((SAMPLES / name).read_text(encoding="utf-8"))


class StubClient:
    """An Anthropic client that replies with `reply` and keeps what it was sent."""

    def __init__(self, reply: str | dict[str, Any], stop_reason: str = "end_turn") -> None:
        self.reply = reply if isinstance(reply, str) else json.dumps(reply)
        self.stop_reason = stop_reason
        self.sent: list[dict[str, Any]] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs: Any) -> SimpleNamespace:
        self.sent.append(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self.reply)],
            stop_reason=self.stop_reason,
            usage=SimpleNamespace(input_tokens=100, output_tokens=40),
            model=MODEL,
        )


def draft(
    runs_dir: Path, client: StubClient, asked: DraftRequest | None = None
) -> tuple[Envelope, bool]:
    asked = asked or sample("soil-survey.readme.draft.json")
    editor = DocumentationEditor(writer=AnthropicWriter(client=client, model_id=MODEL))  # type: ignore[arg-type]
    conductor = make_conductor(runs_dir, editor)
    env = conductor.invoke(request("advisor.documentation", asked), acting_for=TEST_PRINCIPAL)
    return env, conductor.grounding_reports[env.invocation_id].passed


def template_draft(runs_dir: Path, asked: DraftRequest) -> Document:
    conductor = make_conductor(runs_dir, DocumentationEditor())
    env = conductor.invoke(request("advisor.documentation", asked), acting_for=TEST_PRINCIPAL)
    return env.payload_as(Document)


def section(text: str, heading: str) -> str:
    return text.split(f"## {heading}\n\n", 1)[1].split("\n\n## ", 1)[0]


@pytest.mark.requirement("R5", "DD-GROUNDING-MODE", "DD-GROUNDED-PAYLOAD")
def test_a_model_writes_prose_from_the_facts_and_the_version_says_so(runs_dir: Path) -> None:
    client = StubClient({"overview": OVERVIEW, "Files": FILES})
    env, grounded = draft(runs_dir, client)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.grounding_mode == GroundingMode.INPUT_ONLY and grounded
    document = env.payload_as(Document)
    assert document.document_derivation == Derivation.MODEL
    text = document.document_text
    assert text.startswith(f"# README\n\n{OVERVIEW}\n\n## ")
    assert section(text, "Files").startswith(FILES + "\n\n| File |")
    assert f"A model ({MODEL}) wrote 2 paragraphs" in env.outcome.statement
    assert env.telemetry.model_id == MODEL


@pytest.mark.requirement("R5")
def test_prose_closes_no_gap_and_keeps_every_question(runs_dir: Path) -> None:
    asked = sample("soil-survey.readme.draft.json")
    template = template_draft(runs_dir, asked)
    env, _ = draft(runs_dir, StubClient({"overview": OVERVIEW, "Files": FILES}), asked)
    document = env.payload_as(Document)
    assert GAP.findall(document.document_text) == GAP.findall(template.document_text)
    assert document.document_questions == template.document_questions
    # Apart from the prose, the draft is the template's.
    assert (
        document.document_text.replace(f"{OVERVIEW}\n\n", "").replace(f"{FILES}\n\n", "")
        == template.document_text
    )


@pytest.mark.requirement("R5")
def test_no_prose_for_a_section_with_no_facts(runs_dir: Path) -> None:
    client = StubClient({"Methods": "The soil was sampled by auger.", "Files": FILES})
    env, _ = draft(runs_dir, client)
    text = env.payload_as(Document).document_text
    assert "auger" not in text
    offered = json.loads(
        client.sent[0]["messages"][0]["content"].split("\n", 1)[0].split(": ", 1)[1]
    )
    assert "Methods" not in offered and "Software requirements" not in offered
    assert "Methods: not a section it was asked to write" in env.outcome.statement


@pytest.mark.parametrize(
    ("paragraph", "why"),
    [
        ("The 12 sites were sampled in 2019.", "names '12'"),
        ("See https://example.org/soil for the protocol.", "names 'https://example.org/soil'"),
        ("Contact soil@example.ac.uk.", "names 'soil@example.ac.uk'"),
        ("The field `moisture` holds soil moisture.", "names 'moisture'"),
        ("## Files\nThe tables.", "not plain prose"),
        ("| a | b |", "not plain prose"),
        ("The tables. <!-- dd:gap q-0000000000000000 -->", "not plain prose"),
        ("- one\n- two", "not plain prose"),
    ],
)
def test_a_paragraph_naming_what_the_facts_do_not_give_is_dropped(paragraph: str, why: str) -> None:
    facts = {"file_count": 5, "files": [{"path": "data/readings.csv"}]}
    prose = check(json.dumps({"Files": paragraph}), facts, ["Files"])
    assert prose.sections == {}
    assert prose.dropped and why in prose.dropped[0]


def test_a_paragraph_naming_only_what_the_facts_give_is_kept() -> None:
    facts = {"file_count": 5, "files": [{"path": "data/readings.csv"}]}
    reply = (
        "```json\n"
        + json.dumps({"Files": "Of the 5 files, `data/readings.csv` is a table."})
        + "\n```"
    )
    prose = check(reply, facts, ["Files"])
    assert prose.sections == {"Files": "Of the 5 files, `data/readings.csv` is a table."}
    assert prose.dropped == ()


@pytest.mark.parametrize(
    ("client", "why"),
    [
        (StubClient("I would rather not."), "not JSON"),
        (StubClient({"overview": OVERVIEW}, stop_reason="refusal"), "declined"),
        (StubClient({"overview": "The 12 sites were sampled in 2019."}), "not used"),
    ],
)
def test_a_draft_with_no_usable_prose_is_a_template_version(
    runs_dir: Path, client: StubClient, why: str
) -> None:
    asked = sample("soil-survey.readme.draft.json")
    env, grounded = draft(runs_dir, client, asked)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED and grounded
    document = env.payload_as(Document)
    assert document.document_derivation == Derivation.TEMPLATE
    assert document.document_text == template_draft(runs_dir, asked).document_text
    assert why in env.outcome.statement


def test_the_model_is_given_the_facts_and_never_the_answers_or_an_earlier_version(
    runs_dir: Path,
) -> None:
    asked = sample("soil-survey.readme-with-record.draft.json")
    template = template_draft(runs_dir, asked)
    question = template.document_questions[0].question_id
    secret = "Answered by the researcher in confidence"
    asked = asked.model_copy(
        update={"draft_answers": [DraftAnswer(answered_question=question, answer_text=secret)]}
    )
    client = StubClient({"overview": None})
    env, _ = draft(runs_dir, client, asked)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED
    assert secret in env.payload_as(Document).document_text
    assert len(client.sent) == 1
    sent = client.sent[0]
    assert sent["system"] == SYSTEM_PROMPT
    content = sent["messages"][0]["content"]
    assert secret not in content
    assert "data/readings.csv" in content and "nitrate_mg_kg" in content
    assert asked.metadata_record is not None
    facts = json.loads(content.split("Facts:\n", 1)[1])
    assert facts["approved_metadata_record"]["title"]
    assert "sha256" not in content
    # The model was asked but wrote nothing usable: a template version, said so.
    assert env.payload_as(Document).document_derivation == Derivation.TEMPLATE
    assert "added none" in env.outcome.statement


def test_the_call_and_its_prompt_are_recorded(runs_dir: Path) -> None:
    env, _ = draft(runs_dir, StubClient({"overview": OVERVIEW}))
    calls = env.telemetry.model_calls
    assert len(calls) == 1 and calls[0].model_id == MODEL
    assert env.telemetry.input_tokens == 100 and env.telemetry.output_tokens == 40


def test_the_writer_calls_any_model_through_the_sdk_seam(runs_dir: Path) -> None:
    model = FakeModel(json.dumps({"overview": OVERVIEW}), model_id=MODEL)
    editor = DocumentationEditor(writer=AnthropicWriter(model=model))
    conductor = make_conductor(runs_dir, editor)
    asked = sample("soil-survey.readme.draft.json")
    env = conductor.invoke(request("advisor.documentation", asked), acting_for=TEST_PRINCIPAL)
    assert env.payload_as(Document).document_text.startswith(f"# README\n\n{OVERVIEW}\n\n")
    assert model.sent[0].system == SYSTEM_PROMPT
    assert [c.model_id for c in env.telemetry.model_calls] == [MODEL]


def test_the_factory_defaults_to_the_template_and_declares_a_configured_model() -> None:
    assert build({}).spec.models == ()
    with pytest.raises(ConfigError):
        build({"DD_DOCUMENTATION_WRITER": "anthropic"})
    with pytest.raises(ConfigError):
        build({"DD_DOCUMENTATION_WRITER": "oracle"})
    agent = build(
        {"DD_DOCUMENTATION_WRITER": "anthropic", "ANTHROPIC_API_KEY": "k", "DD_MODEL_ID": MODEL}
    )
    (use,) = agent.spec.models
    assert (use.provider, use.model, use.hosting) == ("anthropic", MODEL, "hosted")
