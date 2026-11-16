"""advisor.rights with an interpreter model (docs/specs/agents.md, Model-backed personas): the
model reads a reuse wish the rules cannot, chooses only from the adviser's own table, and any
reply that cannot be used leaves the rules' result. Every model here is a `FakeModel`; no key is
needed."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from dd_agent_advisor_rights import factory
from dd_agent_advisor_rights.agent import (
    CHOOSE_QUESTION,
    MANDATED_REUSE_QUESTION,
    REUSE_QUESTION,
    RightsAdviser,
    load_table,
)
from dd_agent_advisor_rights.classes import RightsContext, RightsOptions
from dd_agent_advisor_rights.interpret import (
    DEFAULT_MODEL,
    SYSTEM_PROMPT,
    ModelInterpreter,
    RightsReply,
    TemplateInterpreter,
)
from dd_agent_advisor_rights.testing import rights_reply
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_sdk.agent import describe
from dd_sdk.contract.models import Derivation, Envelope, GroundingMode, OutcomeStatus
from dd_sdk.credentials import ConfigError
from dd_sdk.model import ModelCallError, ModelRequest, declared
from dd_sdk.testing import FakeModel

MODEL = "fake-model"
NOT_SELL = "Anyone may use it, but not to sell it."
TABLE_IDS = [row["spdx_id"] for row in load_table()["licences"]]


def adviser(model: FakeModel) -> RightsAdviser:
    """Built as the factory builds it with a model: the model declared on the card."""
    agent = RightsAdviser(interpreter=ModelInterpreter(model))
    agent.spec = replace(agent.spec, models=(declared(model),))
    return agent


def run(runs_dir: Path, agent: RightsAdviser, asked: RightsContext) -> Envelope:
    conductor = make_conductor(runs_dir, agent)
    env = conductor.invoke(request("advisor.rights", asked), acting_for=TEST_PRINCIPAL)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.grounding_mode == GroundingMode.INPUT_ONLY
    assert conductor.grounding_reports[env.invocation_id].passed
    return env


def licences(env: Envelope) -> list[tuple[str, Derivation]]:
    return [(lic.spdx_id, lic.derivation) for lic in env.payload_as(RightsOptions).licences]


def questions(env: Envelope) -> list[tuple[str, Derivation]]:
    return [(q.text, q.derivation) for q in env.payload_as(RightsOptions).questions]


@pytest.mark.requirement("DD-GROUNDING-MODE", "DD-GROUNDED-PAYLOAD")
@pytest.mark.parametrize(
    ("said", "reply", "offered"),
    [
        (NOT_SELL, rights_reply(["non-commercial"], ["CC-BY-NC-4.0"]), ["CC-BY-NC-4.0"]),
        (
            "They must credit me, and whatever they build from it must stay open.",
            rights_reply(["share-alike"], ["ODbL-1.0"]),
            ["ODbL-1.0"],
        ),
        (
            "Credit the team; otherwise no strings.",
            # The model orders one; the other licence that fits still follows, in table order.
            rights_reply(["attribution"], ["ODC-By-1.0"]),
            ["ODC-By-1.0", "CC-BY-4.0"],
        ),
    ],
    ids=["not-to-sell", "share-alike", "attribution-ordered"],
)
def test_a_reuse_wish_in_the_researchers_words_selects_the_licences_that_fit(
    runs_dir: Path, said: str, reply: str, offered: list[str]
) -> None:
    template = run(runs_dir, RightsAdviser(), RightsContext(reuse_wanted=said, sensitive=False))
    assert [i for i, _ in licences(template)] == TABLE_IDS  # by rule it falls through
    assert REUSE_QUESTION in [q for q, _ in questions(template)]

    env = run(
        runs_dir, adviser(FakeModel(reply)), RightsContext(reuse_wanted=said, sensitive=False)
    )

    assert licences(env) == [(i, Derivation.MODEL) for i in offered]
    asked = questions(env)
    assert asked[0] == (CHOOSE_QUESTION, Derivation.TEMPLATE)
    assert REUSE_QUESTION not in [q for q, _ in asked]
    [(read_as, how)] = [(q, d) for q, d in asked if q.startswith("A model read")]
    assert how == Derivation.MODEL and said in read_as
    assert f"A model ({MODEL})" in env.outcome.statement
    assert env.telemetry.model_id == MODEL


def test_a_licence_outside_the_table_cannot_reach_the_payload(runs_dir: Path) -> None:
    reply = rights_reply(
        ["non-commercial", "no-derivatives"],
        ["MIT", "CC-BY-NC-SA-4.0", "CC-BY-4.0", "cc-by-nc-4.0", "CC-BY-NC-4.0"],
    )
    env = run(runs_dir, adviser(FakeModel(reply)), RightsContext(reuse_wanted=NOT_SELL))

    payload = env.payload_as(RightsOptions)
    assert [lic.spdx_id for lic in payload.licences] == ["CC-BY-NC-4.0"]
    assert set(TABLE_IDS) >= {lic.spdx_id for lic in payload.licences}
    assert "MIT" not in json.dumps(payload.model_dump(exclude={"dropped"}, mode="json"))
    assert payload.dropped == [
        "reuse 'no-derivatives': 'no-derivatives' is not a reuse value in the table",
        "licence 'MIT': 'MIT' is not among the licences that fit the reuse read",
        "licence 'CC-BY-NC-SA-4.0': 'CC-BY-NC-SA-4.0' is not among the licences that fit the "
        "reuse read",
        "licence 'CC-BY-4.0': 'CC-BY-4.0' is not among the licences that fit the reuse read",
        "licence 'CC-BY-NC-4.0': given twice",
    ]
    assert "5 parts of its reply were not used" in env.outcome.statement


def test_an_unclear_wish_still_offers_every_licence_and_asks(runs_dir: Path) -> None:
    env = run(
        runs_dir,
        adviser(FakeModel(rights_reply())),
        RightsContext(reuse_wanted="Not sure yet."),
    )
    assert licences(env) == [(i, Derivation.TEMPLATE) for i in TABLE_IDS]
    assert (REUSE_QUESTION, Derivation.TEMPLATE) in questions(env)


def test_a_mandated_licence_is_still_listed_by_rule(runs_dir: Path) -> None:
    reply = rights_reply(["non-commercial"], ["CC-BY-NC-4.0"], ["Does the mandate cover data?"])
    env = run(
        runs_dir,
        adviser(FakeModel(reply)),
        RightsContext(reuse_wanted=NOT_SELL, mandated_licence="CC-BY-4.0"),
    )

    assert licences(env) == [("CC-BY-4.0", Derivation.TEMPLATE)]
    asked = questions(env)
    # CC BY allows selling, which the model read the researcher as not wanting.
    assert (MANDATED_REUSE_QUESTION, Derivation.MODEL) in asked
    assert ("Does the mandate cover data?", Derivation.MODEL) in asked
    assert env.payload_as(RightsOptions).dropped == [
        "licence 'CC-BY-NC-4.0': a mandated licence is listed by rule"
    ]


def test_tailored_questions_are_kept_only_where_they_may_be_asked(runs_dir: Path) -> None:
    long = "Why? " * 80
    reply = rights_reply(
        questions=[
            "Who holds the rights in the archive photographs you include?",
            CHOOSE_QUESTION,
            long,
            "Does the publisher's licence allow redistribution?",
            "Have the interviewees agreed to reuse?",
            "One too many?",
        ]
    )
    env = run(runs_dir, adviser(FakeModel(reply)), RightsContext(third_party_content=True))

    model_questions = [q for q, how in questions(env) if how == Derivation.MODEL]
    assert model_questions == [
        "Who holds the rights in the archive photographs you include?",
        "Does the publisher's licence allow redistribution?",
        "Have the interviewees agreed to reuse?",
    ]
    dropped = env.payload_as(RightsOptions).dropped
    assert len(dropped) == 3
    assert "it repeats a question already asked" in dropped[0]
    assert "it is too long" in dropped[1]
    assert "more than 3 questions" in dropped[2]


def test_no_questions_without_third_party_content_or_a_mandate(runs_dir: Path) -> None:
    reply = rights_reply(["any"], ["CC0-1.0"], ["Have you thought about an embargo?"])
    env = run(runs_dir, adviser(FakeModel(reply)), RightsContext(reuse_wanted="Anything goes."))
    assert all(not q.startswith("Have you") for q, _ in questions(env))
    [why] = env.payload_as(RightsOptions).dropped
    assert "may only ask about third-party content or a mandated licence" in why


def test_only_what_the_rules_cannot_read_reaches_the_model(runs_dir: Path) -> None:
    model = FakeModel(rights_reply(questions=["Who owns the maps?"]))
    run(
        runs_dir,
        adviser(model),
        RightsContext(reuse_wanted="attribution", sensitive=True, third_party_content=True),
    )

    [sent] = model.sent
    assert isinstance(sent, ModelRequest)
    assert sent.system == SYSTEM_PROMPT
    assert sent.schema is RightsReply
    [message] = sent.messages
    assert isinstance(message, dict)
    content = json.loads(str(message["content"]).split("\n", 1)[1])
    # The keyword was read by rule, and whether the data are sensitive is not sent.
    assert content["said"] == {"third_party_content": True}
    assert [row["spdx_id"] for row in content["licences"]] == TABLE_IDS


def test_no_call_when_there_is_nothing_to_read(runs_dir: Path) -> None:
    model = FakeModel(rights_reply())
    env = run(runs_dir, adviser(model), RightsContext(reuse_wanted="any", sensitive=False))

    assert model.sent == []
    assert "nothing for the interpreter model" in env.outcome.statement
    assert env.telemetry.model_calls == []


@pytest.mark.parametrize(
    ("model", "why"),
    [
        (FakeModel(refuse=True), "the model declined"),
        (FakeModel("Probably non-commercial."), "did not match its schema"),
        (FakeModel(lambda _: (_ for _ in ()).throw(ModelCallError("timed out"))), "timed out"),
    ],
    ids=["refused", "not-json", "unreachable"],
)
def test_a_reply_that_cannot_be_used_leaves_the_rules_result(
    runs_dir: Path, model: FakeModel, why: str
) -> None:
    env = run(runs_dir, adviser(model), RightsContext(reuse_wanted=NOT_SELL))

    assert licences(env) == [(i, Derivation.TEMPLATE) for i in TABLE_IDS]
    assert (REUSE_QUESTION, Derivation.TEMPLATE) in questions(env)
    assert "They follow by rule, because" in env.outcome.statement
    assert why in env.outcome.statement


def test_a_fenced_reply_is_used(runs_dir: Path) -> None:
    reply = rights_reply(["non-commercial"], ["CC-BY-NC-4.0"])
    env = run(
        runs_dir, adviser(FakeModel(f"```json\n{reply}\n```")), RightsContext(reuse_wanted=NOT_SELL)
    )
    assert licences(env) == [("CC-BY-NC-4.0", Derivation.MODEL)]


def test_the_factory_defaults_to_the_template_and_declares_no_model() -> None:
    agent = factory.build({})
    assert isinstance(agent.interpreter, TemplateInterpreter)
    assert describe(agent.spec)["models"] == []


@pytest.mark.parametrize("setting", ["model", "anthropic"])
def test_the_factory_declares_the_model_it_sends_data_to(setting: str) -> None:
    pytest.importorskip("anthropic")
    agent = factory.build({factory.SWITCH: setting, "ANTHROPIC_API_KEY": "sk-test"})
    assert isinstance(agent.interpreter, ModelInterpreter)
    [use] = agent.spec.models
    assert (use.provider, use.model) == ("anthropic", DEFAULT_MODEL)


def test_an_unknown_interpreter_stops_the_agent_at_start_up() -> None:
    with pytest.raises(ConfigError):
        factory.build({factory.SWITCH: "regex"})
