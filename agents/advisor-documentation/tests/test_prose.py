"""advisor.documentation with a model: the README's prose is written from the project's facts
alone, checked before it is used, and never closes a gap (docs/specs/drafting.md)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from dd_agent_advisor_documentation.agent import RESEARCHER_ANSWERS, DocumentationEditor
from dd_agent_advisor_documentation.factory import build
from dd_agent_advisor_documentation.prose import SYSTEM_PROMPT, ModelWriter, ProseReply, check
from dd_agent_advisor_documentation.suggestions import SUGGEST_PROMPT, SUGGEST_README_PROMPT
from dd_agent_advisor_documentation.testing import prose_reply, redraft, suggestion_reply
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
from dd_sdk.model_anthropic import AnthropicModel
from dd_sdk.testing import FakeModel

SAMPLES = Path(__file__).with_name("data")
MODEL = "claude-test"
GAP = re.compile(r"<!-- dd:gap (q-[0-9a-f]{16}) -->")

OVERVIEW = (
    "The dataset consists of 5 files, two of them tables: `data/readings.csv` and `data/sites.tsv`."
)
FILES = "The tables `data/readings.csv` and `data/sites.tsv` both have a field named `site`."


def sample(name: str) -> DraftRequest:
    """A sample request; a README's as a project's second run makes it, so that the editor
    writes the README rather than asking first (`first_sample` is the first run's)."""
    return redraft(first_sample(name))


def first_sample(name: str) -> DraftRequest:
    return DraftRequest.model_validate_json((SAMPLES / name).read_text(encoding="utf-8"))


class StubClient:
    """An Anthropic client that keeps what it was sent and replies with `reply`: to the prose
    call, as paragraphs by heading; to a data dictionary's suggestion call, as suggestions by
    question; or as the raw text to either. A README's suggestion call is given `suggestions`,
    none by default."""

    def __init__(
        self,
        reply: str | dict[str, Any],
        stop_reason: str = "end_turn",
        suggestions: dict[str, str | None] | None = None,
    ) -> None:
        self.reply = reply
        self.suggestions = suggestions
        self.stop_reason = stop_reason
        self.sent: list[dict[str, Any]] = []
        self.messages = SimpleNamespace(create=self._create)

    def _text(self, system: str) -> str:
        if system == SUGGEST_README_PROMPT and self.suggestions is not None:
            return suggestion_reply(self.suggestions)
        if isinstance(self.reply, str):
            return self.reply
        if system == SYSTEM_PROMPT:
            return prose_reply(self.reply)
        return suggestion_reply(self.reply if system == SUGGEST_PROMPT else {})

    def _create(self, **kwargs: Any) -> SimpleNamespace:
        self.sent.append(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self._text(kwargs["system"]))],
            stop_reason=self.stop_reason,
            usage=SimpleNamespace(input_tokens=100, output_tokens=40),
            model=MODEL,
        )


def draft(
    runs_dir: Path, client: StubClient, asked: DraftRequest | None = None
) -> tuple[Envelope, bool]:
    asked = asked or sample("soil-survey.readme.draft.json")
    editor = DocumentationEditor(writer=ModelWriter(AnthropicModel(MODEL, client=client)))  # type: ignore[arg-type]
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
    prose = check(
        ProseReply.model_validate_json(prose_reply({"Files": paragraph})), facts, ["Files"]
    )
    assert prose.sections == {}
    assert prose.dropped and why in prose.dropped[0]


def test_a_paragraph_naming_only_what_the_facts_give_is_kept() -> None:
    facts = {"file_count": 5, "files": [{"path": "data/readings.csv"}]}
    reply = prose_reply({"Files": "Of the 5 files, `data/readings.csv` is a table."})
    prose = check(ProseReply.model_validate_json(reply), facts, ["Files"])
    assert prose.sections == {"Files": "Of the 5 files, `data/readings.csv` is a table."}
    assert prose.dropped == ()


def test_a_paragraph_written_twice_is_used_once() -> None:
    reply = ProseReply.model_validate_json(
        json.dumps(
            {
                "overview": None,
                "sections": [
                    {"section": "Files", "paragraph": "The tables."},
                    {"section": "Files", "paragraph": "Again."},
                ],
            }
        )
    )
    prose = check(reply, {}, ["Files"])
    assert prose.sections == {"Files": "The tables."}
    assert len(prose.dropped) == 1


def test_a_fenced_reply_from_an_unconstrained_endpoint_is_still_used(runs_dir: Path) -> None:
    env, _ = draft(runs_dir, StubClient(f"```json\n{prose_reply({'overview': OVERVIEW})}\n```"))
    document = env.payload_as(Document)
    assert document.document_derivation == Derivation.MODEL
    assert document.document_text.startswith(f"# README\n\n{OVERVIEW}\n\n")


def test_the_reply_is_constrained_to_the_schema(runs_dir: Path) -> None:
    client = StubClient({"overview": OVERVIEW})
    draft(runs_dir, client)
    assert all(sent["output_config"]["format"]["type"] == "json_schema" for sent in client.sent)


@pytest.mark.parametrize(
    ("client", "why"),
    [
        (StubClient("I would rather not."), "did not match its schema"),
        (StubClient(json.dumps({"overview": OVERVIEW})), "did not match its schema"),
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


def test_the_model_is_given_the_facts_and_never_a_part_answer_or_an_earlier_version(
    runs_dir: Path,
) -> None:
    """A part of General information is a value placed as given (a date, a name), so the model is
    not given its answer; only a section answered as a whole is written in the model's words."""
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
    assert template.document_questions[0].gap_part is not None
    # One call for the prose, one for the suggested answers; neither is given the answer.
    assert len(client.sent) == 2
    assert all(secret not in sent["messages"][0]["content"] for sent in client.sent)
    sent = client.sent[0]
    assert sent["system"] == SYSTEM_PROMPT
    content = sent["messages"][0]["content"]
    assert "data/readings.csv" in content and "nitrate_mg_kg" in content
    assert asked.metadata_record is not None
    facts = json.loads(content.split("Facts:\n", 1)[1])
    assert facts["approved_metadata_record"]["title"]
    assert "sha256" not in content
    # The model was asked but wrote nothing usable: a template version, said so.
    assert env.payload_as(Document).document_derivation == Derivation.TEMPLATE
    assert "added none" in env.outcome.statement


METHODS_ANSWER = "Cores were taken at 10 cm depth and dried at 40 C before sieving."
METHODS_PROSE = (
    "Soil cores were taken at a depth of 10 cm, then dried at 40 C and sieved before analysis."
)


def answered_methods(runs_dir: Path) -> DraftRequest:
    asked = sample("soil-survey.readme.draft.json")
    template = template_draft(runs_dir, asked)
    (methods,) = [q for q in template.document_questions if q.gap_section == "Methods"]
    answer = DraftAnswer(answered_question=methods.question_id, answer_text=METHODS_ANSWER)
    return asked.model_copy(update={"draft_answers": [answer]})


@pytest.mark.requirement("R5")
def test_a_section_answered_is_written_by_the_model_from_the_answer(runs_dir: Path) -> None:
    asked = answered_methods(runs_dir)
    client = StubClient({"Methods": METHODS_PROSE})
    env, _ = draft(runs_dir, client, asked)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    document = env.payload_as(Document)
    assert section(document.document_text, "Methods").strip() == METHODS_PROSE
    assert METHODS_ANSWER not in document.document_text
    assert document.document_derivation == Derivation.MODEL
    assert "Methods" not in {q.gap_section for q in document.document_questions}
    # The model was offered Methods, and given the answer to write it from.
    prose_call = next(s for s in client.sent if s["system"] == SYSTEM_PROMPT)
    facts = json.loads(prose_call["messages"][0]["content"].split("Facts:\n", 1)[1])
    assert facts[RESEARCHER_ANSWERS] == {"Methods": METHODS_ANSWER}
    assert '"Methods"' in prose_call["messages"][0]["content"].split("Facts:", 1)[0]


def test_a_paragraph_that_strays_from_the_answer_leaves_the_answer_as_given(
    runs_dir: Path,
) -> None:
    asked = answered_methods(runs_dir)
    strays = "Soil cores were taken at a depth of 15 cm and dried."
    env, _ = draft(runs_dir, StubClient({"Methods": strays}), asked)
    text = env.payload_as(Document).document_text
    assert section(text, "Methods").strip() == METHODS_ANSWER
    assert "15" in env.outcome.statement


def test_with_no_section_answered_the_model_is_given_no_answers(runs_dir: Path) -> None:
    client = StubClient({"overview": None})
    draft(runs_dir, client)
    prose_call = next(s for s in client.sent if s["system"] == SYSTEM_PROMPT)
    facts = json.loads(prose_call["messages"][0]["content"].split("Facts:\n", 1)[1])
    assert RESEARCHER_ANSWERS not in facts


def test_each_call_and_its_prompt_are_recorded(runs_dir: Path) -> None:
    env, _ = draft(runs_dir, StubClient({"overview": OVERVIEW}))
    calls = env.telemetry.model_calls
    # The prose and the suggested answers: two calls, their tokens summed.
    assert [c.model_id for c in calls] == [MODEL, MODEL]
    assert len({c.prompt_digest for c in calls}) == 2
    assert env.telemetry.input_tokens == 200 and env.telemetry.output_tokens == 80


def test_the_writer_calls_any_model_through_the_sdk_seam(runs_dir: Path) -> None:
    model = FakeModel(
        lambda r: (
            prose_reply({"overview": OVERVIEW})
            if r.system == SYSTEM_PROMPT
            else suggestion_reply({})
        ),
        model_id=MODEL,
    )
    editor = DocumentationEditor(writer=ModelWriter(model))
    conductor = make_conductor(runs_dir, editor)
    asked = sample("soil-survey.readme.draft.json")
    env = conductor.invoke(request("advisor.documentation", asked), acting_for=TEST_PRINCIPAL)
    assert env.payload_as(Document).document_text.startswith(f"# README\n\n{OVERVIEW}\n\n")
    assert model.sent[0].system == SYSTEM_PROMPT
    assert [c.model_id for c in env.telemetry.model_calls] == [MODEL, MODEL]


def test_the_factory_defaults_to_a_model_and_declares_it() -> None:
    (use,) = build({"ANTHROPIC_API_KEY": "k"}).spec.models
    assert (use.provider, use.hosting) == ("anthropic", "hosted")
    assert build({"DD_DOCUMENTATION_WRITER": "template"}).spec.models == ()
    with pytest.raises(ConfigError, match="DD_DOCUMENTATION_WRITER=template"):
        build({})
    with pytest.raises(ConfigError):
        build({"DD_DOCUMENTATION_WRITER": "anthropic"})
    with pytest.raises(ConfigError):
        build({"DD_DOCUMENTATION_WRITER": "oracle"})
    agent = build(
        {"DD_DOCUMENTATION_WRITER": "anthropic", "ANTHROPIC_API_KEY": "k", "DD_MODEL_ID": MODEL}
    )
    (use,) = agent.spec.models
    assert (use.provider, use.model, use.hosting) == ("anthropic", MODEL, "hosted")


@pytest.mark.parametrize(
    ("settings", "declared"),
    [
        (
            {"DD_MODEL_PROVIDER": "openai", "DD_MODEL_ID": "m-1", "OPENAI_API_KEY": "k"},
            ("openai", "m-1", "hosted"),
        ),
        (
            {
                "DD_MODEL_PROVIDER": "openai-compatible",
                "DD_MODEL_ID": "llama",
                "DD_MODEL_BASE_URL": "http://localhost:11434/v1",
            },
            ("localhost:11434", "llama", "local"),
        ),
    ],
)
def test_the_model_can_come_from_another_provider(
    settings: dict[str, str], declared: tuple[str, str, str]
) -> None:
    pytest.importorskip("openai")
    agent = build({"DD_DOCUMENTATION_WRITER": "model", **settings})
    assert [(m.provider, m.model, m.hosting) for m in agent.spec.models] == [declared]


def test_the_older_anthropic_setting_names_only_anthropic() -> None:
    with pytest.raises(ConfigError):
        build(
            {
                "DD_DOCUMENTATION_WRITER": "anthropic",
                "DD_MODEL_PROVIDER": "openai",
                "DD_MODEL_ID": "m-1",
                "OPENAI_API_KEY": "k",
            }
        )
