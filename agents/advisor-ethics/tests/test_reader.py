"""advisor.ethics with a model reader: union only, the checker and the factory
(docs/specs/agents.md, Model-backed personas). Every model is a `FakeModel`; no test needs a key."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from dd_agent_advisor_ethics.agent import PEOPLE_QUESTION, EthicsAdviser, load_keywords
from dd_agent_advisor_ethics.classes import SensitivityContext, SensitivityFlags
from dd_agent_advisor_ethics.factory import build
from dd_agent_advisor_ethics.reader import SYSTEM_PROMPT, ModelReader, TemplateReader
from dd_agent_advisor_ethics.testing import reader_reply
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.contract.models import Derivation, Envelope, GroundingMode, OutcomeStatus
from dd_sdk.credentials import ConfigError
from dd_sdk.model import ModelCallError, ModelRequest
from dd_sdk.testing import FakeModel

CASES = Path(__file__).with_name("cases") / "false_negatives.json"
MODEL = "claude-test"
CONTEXT = SensitivityContext(
    title="Clinic follow-up",
    description="Follow-up visits at a sexual health clinic.",
    fields=["participant_id", "postcode", "hiv_status", "visit_count"],
    involves_people=True,
)
# The keyword table flags `postcode` alone of CONTEXT's fields.
LEXICAL = {"postcode": "direct identifier"}


def invoke(
    runs_dir: Path, model: FakeModel, context: SensitivityContext = CONTEXT
) -> tuple[Envelope, SensitivityFlags]:
    adviser = EthicsAdviser(reader=ModelReader(model))
    conductor = make_conductor(runs_dir, adviser)
    env = conductor.invoke(request("advisor.ethics", context), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert conductor.grounding_reports[env.invocation_id].passed
    return env, env.payload_as(SensitivityFlags)


def by_field(payload: SensitivityFlags) -> dict[str, tuple[str, Derivation]]:
    return {f.field: (f.category, f.derivation) for f in payload.flags}


def test_a_model_flag_is_added_to_the_keyword_flags_and_marked_as_the_models(
    runs_dir: Path,
) -> None:
    model = FakeModel(
        reader_reply([("hiv_status", "special category", "HIV status")], ["Are any minors?"]),
        model_id=MODEL,
    )
    env, payload = invoke(runs_dir, model)
    assert env.grounding_mode == GroundingMode.INPUT_ONLY
    assert by_field(payload) == {
        "postcode": ("direct identifier", Derivation.LEXICAL),
        "hiv_status": ("special category", Derivation.MODEL),
    }
    (added,) = [f for f in payload.flags if f.derivation == Derivation.MODEL]
    assert added.reason and added.matched is None
    assert [q.derivation for q in payload.questions if q.text == "Are any minors?"] == [
        Derivation.MODEL
    ]
    assert payload.dropped == []
    assert env.telemetry.model_id == MODEL
    assert [c.model_id for c in env.telemetry.model_calls] == [MODEL]


def test_a_reply_that_omits_a_keyword_flag_still_yields_it(runs_dir: Path) -> None:
    _, payload = invoke(runs_dir, FakeModel(reader_reply(), model_id=MODEL))
    assert by_field(payload) == {"postcode": ("direct identifier", Derivation.LEXICAL)}


def test_a_model_cannot_recategorise_a_keyword_flag(runs_dir: Path) -> None:
    model = FakeModel(reader_reply([("postcode", "location", "a place")]), model_id=MODEL)
    _, payload = invoke(runs_dir, model)
    assert by_field(payload) == {"postcode": ("direct identifier", Derivation.LEXICAL)}


def test_a_model_flag_alone_asks_about_consent(runs_dir: Path) -> None:
    context = SensitivityContext(fields=["hiv_status", "visit_count"], embargo_intended=False)
    model = FakeModel(reader_reply([("hiv_status", "special category", "HIV status")]))
    _, payload = invoke(runs_dir, model, context)
    assert [(q.text, q.derivation) for q in payload.questions] == [
        (PEOPLE_QUESTION, Derivation.TEMPLATE)
    ]


@pytest.mark.parametrize(
    "flag",
    [
        ("hiv_stat", "special category", "not a field given"),
        ("hiv_status", "medical", "not a category in the table"),
    ],
)
def test_a_flag_naming_an_unknown_field_or_category_is_dropped_and_recorded(
    runs_dir: Path, flag: tuple[str, str, str]
) -> None:
    env, payload = invoke(runs_dir, FakeModel(reader_reply([flag]), model_id=MODEL))
    assert by_field(payload) == {"postcode": ("direct identifier", Derivation.LEXICAL)}
    assert len(payload.dropped) == 1
    assert payload.dropped[0].startswith(flag[0])
    assert payload.dropped[0] in env.outcome.statement


def _unreachable(request: ModelRequest) -> str:
    raise ModelCallError("connection refused")


@pytest.mark.parametrize(
    ("model", "why"),
    [
        (FakeModel(refuse=True, model_id=MODEL), "declined"),
        (FakeModel("I cannot help with that.", model_id=MODEL), "did not match its schema"),
        (FakeModel(json.dumps({"flags": []}), model_id=MODEL), "did not match its schema"),
        (FakeModel(_unreachable, model_id=MODEL), "could not be reached"),
    ],
)
def test_an_unusable_reply_leaves_the_keyword_flags_and_says_why(
    runs_dir: Path, model: FakeModel, why: str
) -> None:
    env, payload = invoke(runs_dir, model)
    assert by_field(payload) == {"postcode": ("direct identifier", Derivation.LEXICAL)}
    assert {q.derivation for q in payload.questions} == {Derivation.TEMPLATE}
    assert why in env.outcome.statement


def test_a_fenced_reply_is_used(runs_dir: Path) -> None:
    reply = reader_reply([("hiv_status", "special category", "HIV status")])
    _, payload = invoke(runs_dir, FakeModel(f"```json\n{reply}\n```", model_id=MODEL))
    assert "hiv_status" in by_field(payload)


def test_the_model_is_given_field_names_and_context_flags_only(runs_dir: Path) -> None:
    model = FakeModel(reader_reply(), model_id=MODEL)
    invoke(runs_dir, model)
    (sent,) = model.sent
    assert sent.system == SYSTEM_PROMPT
    (message,) = sent.messages
    assert isinstance(message, Mapping)
    given = json.loads(message["content"])
    assert set(given) == {
        "fields",
        "involves_people",
        "embargo_intended",
        "categories",
        "already_flagged",
    }
    assert given["fields"] == CONTEXT.fields
    assert given["already_flagged"] == list(LEXICAL)
    assert given["categories"] == list(load_keywords())


def test_the_prompt_forbids_deciding_how_data_are_handled() -> None:
    # C2 (docs/specs/agents.md): the adviser flags and never suggests a treatment.
    assert "# What you never do" in SYSTEM_PROMPT
    assert "anonymisation" in SYSTEM_PROMPT


def test_the_template_reader_declares_no_model() -> None:
    agent = build({"DD_ETHICS_READER": "template"})
    assert isinstance(agent.reader, TemplateReader)
    assert agent.spec.models == ()
    with pytest.raises(ConfigError):
        build({"DD_ETHICS_READER": "oracle"})


def test_the_model_is_on_by_default_and_says_how_to_turn_it_off() -> None:
    with pytest.raises(ConfigError, match="DD_ETHICS_READER=template"):
        build({})


def test_the_factory_declares_a_configured_model() -> None:
    agent = build({"DD_ETHICS_READER": "model", "ANTHROPIC_API_KEY": "k", "DD_MODEL_ID": MODEL})
    assert isinstance(agent.reader, ModelReader)
    (use,) = agent.spec.models
    assert (use.provider, use.model, use.hosting) == ("anthropic", MODEL, "hosted")
    assert build({"DD_ETHICS_READER": "anthropic", "ANTHROPIC_API_KEY": "k"}).spec.models


def test_with_a_model_its_limitations_say_where_the_names_go(runs_dir: Path) -> None:
    _, with_model = invoke(runs_dir, FakeModel(reader_reply(), model_id=MODEL))
    env = make_conductor(runs_dir, EthicsAdviser()).invoke(
        request("advisor.ethics", CONTEXT), acting_for=TEST_PRINCIPAL
    )
    without = env.payload_as(SensitivityFlags)
    assert set(with_model.limitations) != set(without.limitations)
    assert any("TODO(#40)" in line for line in with_model.limitations)


def _false_negatives() -> list[dict[str, str]]:
    cases: list[dict[str, str]] = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    return cases


@pytest.mark.parametrize("case", _false_negatives(), ids=lambda c: c["field"])
def test_a_field_the_keywords_miss_is_kept_when_a_model_flags_it(
    runs_dir: Path, case: dict[str, str]
) -> None:
    # The seed of the false-negative set (TODO(#700)): the keyword table misses each of these,
    # and a model's flag for it is kept with the category it gave.
    context = SensitivityContext(fields=[case["field"]], involves_people=True)
    assert EthicsAdviser()._flag(case["field"]) is None
    model = FakeModel(reader_reply([(case["field"], case["category"], "named by the case")]))
    _, payload = invoke(runs_dir, model, context)
    assert by_field(payload) == {case["field"]: (case["category"], Derivation.MODEL)}
