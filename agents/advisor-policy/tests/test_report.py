"""The parts of the result built from what was advised (`report.py`): the models' use, the
repositories the policies require, and the obligations they state differently."""

from __future__ import annotations

from dd_agent_advisor_policy import report
from dd_agent_advisor_policy.classes import Actor, ActorRole, Obligation, ObligationKind, Strength
from dd_agent_advisor_policy.explain import Explanation, Item, Rationale
from dd_agent_advisor_policy.reading import TextReadings
from dd_agent_advisor_policy.records import Clause, PolicyRecord, Relation
from dd_sdk.contract.models import Derivation
from dd_sdk.model import Usage
from dd_sdk.prompts import ModelCallLog

SRC = Actor(role=ActorRole.FUNDER, name="Social Research Council")
TESTING = Actor(role=ActorRole.INSTITUTION, name="University of Testing")
MANDATES = PolicyRecord(
    fairsharing_id="FAIRsharing.test-funder",
    name="Social Research Council data policy",
    policy_type="funder",
    relations=[Relation(relation="requires", registry="Database", name="Social Survey Archive")],
)
SILENT = PolicyRecord(
    fairsharing_id="FAIRsharing.test-university",
    name="University of Testing - Research Data Policy",
    policy_type="institution",
    clauses={"sharing_data": Clause(values={"mandated_data_sharing": "suggested"})},
)
RATIONALE = Rationale(text="Matched by name.", derivation=Derivation.TEMPLATE)


def advised(*items: Item) -> report.Advised:
    return [(item, RATIONALE) for item in items]


def item(record: PolicyRecord, actor: Actor, *obligations: Obligation) -> Item:
    return Item(record=record, actor=actor, obligations=obligations, notes=())


def test_a_run_without_a_model_reports_only_its_tokens() -> None:
    explanation = Explanation(rationales=[], usage=Usage(input_tokens=None, output_tokens=None))
    use = report.model_use(explanation, TextReadings(), "advisor-model", "reader-model")
    assert set(use) == {"input_tokens", "output_tokens"}


def test_a_run_with_both_models_reports_them_together() -> None:
    explanation = Explanation(
        rationales=[],
        usage=Usage(input_tokens=10, output_tokens=5),
        calls=ModelCallLog("fake"),
    )
    texts = TextReadings(input_tokens=3, output_tokens=2, calls=ModelCallLog("fake"))
    use = report.model_use(explanation, texts, "advisor-model", "reader-model")
    assert use["model_id"] == "advisor-model"
    assert (use["input_tokens"], use["output_tokens"]) == (13, 7)
    only_reader = report.model_use(
        Explanation(rationales=[], usage=Usage()), texts, None, "reader-model"
    )
    assert only_reader["model_id"] == "reader-model"


def test_a_required_repository_comes_from_a_record_or_a_models_quote() -> None:
    assert list(report.mandated(advised(item(MANDATES, SRC)))) == ["social survey archive"]
    assert report.mandated(advised(item(SILENT, TESTING))) == {}
    quoted = Obligation(
        kind=ObligationKind.REPOSITORY,
        strength=Strength.REQUIRED,
        value="UK Data Service",
        quote="Data must be deposited with the UK Data Service.",
        derivation=Derivation.MODEL,
    )
    unquoted = quoted.model_copy(update={"derivation": Derivation.REGISTRY})
    assert report.named_repositories(advised(item(SILENT, TESTING, quoted))) == ["UK Data Service"]
    assert report.named_repositories(advised(item(SILENT, TESTING, unquoted))) == []


def test_obligations_stated_differently_are_a_conflict_grounded_on_both_records() -> None:
    required = Obligation(kind=ObligationKind.DEPOSIT, strength=Strength.REQUIRED)
    suggested = Obligation(kind=ObligationKind.DEPOSIT, strength=Strength.RECOMMENDED)
    [conflict] = report.conflicts(
        advised(item(MANDATES, SRC, required), item(SILENT, TESTING, suggested))
    )
    assert {g.source_id for g in conflict.grounded_on} == {
        MANDATES.source_id,
        SILENT.source_id,
    }
    assert report.conflicts(advised(item(MANDATES, SRC, required))) == []
