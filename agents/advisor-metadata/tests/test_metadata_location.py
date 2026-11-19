"""advisor.metadata asks whether a location may be published, and at what precision, before it asks
for the place (#1073, docs/specs/drafting.md, invariant 9), on its template and model paths."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from test_metadata_agent import sample
from test_metadata_questions import value_at
from test_metadata_suggestions import StubClient, draft, suggest_every

from dd_agent_advisor_metadata.location import Decision, answered, decided, located_fields
from dd_agent_advisor_metadata.questions import question_id
from dd_sdk.contract.facts import ProjectFact
from dd_sdk.contract.models import Document, DraftAnswer, DraftRequest, OutcomeStatus

ENTRY = "geoLocations[0]"
PLACE = "geoLocations[0].geoLocationPlace"


def drafted(
    runs_dir: Path,
    answers: dict[str, str] | None = None,
    decisions: list[dict[str, Any]] | None = None,
    client: StubClient | None = None,
) -> tuple[Document, str]:
    asked: DraftRequest = sample().model_copy(
        update={
            "draft_answers": [
                DraftAnswer(answered_question=question_id(path), answer_text=text)
                for path, text in (answers or {}).items()
            ],
            "project_decisions": [ProjectFact.model_validate(d) for d in decisions or []],
        }
    )
    env, grounded = draft(runs_dir, client, asked)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert grounded
    return env.payload_as(Document), env.outcome.statement


def targets(document: Document) -> dict[str | None, str]:
    return {q.gap_property: q.question_prompt for q in document.document_questions}


def sensitivity(decision: str, precision: str | None = None) -> dict[str, Any]:
    return {
        "fact_kind": "sensitivity",
        "fact_subject": "data/sites.tsv",
        "sensitive_subject": "data/sites.tsv",
        "sensitivity_decision": decision,
        **({"location_precision": precision} if precision else {}),
    }


def test_the_place_is_not_asked_for_until_publication_is_decided(runs_dir: Path) -> None:
    document, _ = drafted(runs_dir)
    asked = targets(document)
    assert ENTRY in asked and PLACE not in asked
    # The fields that suggest a location are named in the first question.
    assert "latitude" in asked[ENTRY] and "data/sites.tsv" in asked[ENTRY]
    assert value_at(json.loads(document.document_text), PLACE) is None


def test_an_answer_on_precision_asks_for_the_place_at_that_precision(runs_dir: Path) -> None:
    before, _ = drafted(runs_dir)
    after, _ = drafted(runs_dir, {ENTRY: "region"})
    asked = targets(after)
    assert ENTRY not in asked and "region" in asked[PLACE]
    # The answer on publication is a decision, never placed in the record.
    assert after.document_text == before.document_text


def test_a_withheld_location_is_left_empty_asked_no_more_and_said(runs_dir: Path) -> None:
    document, statement = drafted(runs_dir, {ENTRY: "Withhold: curlew nest nearby"})
    asked = targets(document)
    assert ENTRY not in asked and PLACE not in asked
    assert value_at(json.loads(document.document_text), PLACE) is None
    assert "withheld" in statement


def test_the_projects_decision_stands_over_an_answer(runs_dir: Path) -> None:
    withheld, _ = drafted(runs_dir, {ENTRY: "exact"}, [sensitivity("withhold")])
    assert {ENTRY, PLACE}.isdisjoint(targets(withheld))
    generalised, _ = drafted(runs_dir, decisions=[sensitivity("generalise", "region")])
    assert "region" in targets(generalised)[PLACE]
    undecided, _ = drafted(runs_dir, {ENTRY: "exact"}, [sensitivity("undecided")])
    assert "exact" in targets(undecided)[PLACE]


def test_a_place_answered_already_stays_placed(runs_dir: Path) -> None:
    document, _ = drafted(runs_dir, {PLACE: "Peak District"})
    assert value_at(json.loads(document.document_text), PLACE) == "Peak District"
    assert {ENTRY, PLACE}.isdisjoint(targets(document))


def test_no_location_question_is_offered_to_the_model(runs_dir: Path) -> None:
    client = StubClient(suggest_every)
    document, _ = drafted(runs_dir, client=client)
    [sent] = client.sent
    offered = json.loads(sent["messages"][0]["content"].split("\n\nFacts:\n")[0].split(":\n", 1)[1])
    assert all(not q["property"].startswith("geoLocations") for q in offered)
    first = next(q for q in document.document_questions if q.gap_property == ENTRY)
    assert first.suggested_answer is None


def test_the_coarsest_precision_decided_stands_and_any_undecided_reopens() -> None:
    located = located_fields(sample().inventory)
    assert located == {"data/sites.tsv": ["latitude", "longitude"]}
    facts = [
        ProjectFact.model_validate({**sensitivity("publish", "exact"), "fact_subject": "lat"}),
        ProjectFact.model_validate(sensitivity("generalise", "country")),
    ]
    both = decided(facts, located)
    assert both is not None and (both.withheld, both.precision) == (False, "country")
    undecided = ProjectFact.model_validate(sensitivity("undecided"))
    assert decided([*facts, undecided], located) is None
    # A sensitivity fact about something other than a location says nothing about the place.
    other = {**sensitivity("withhold"), "sensitive_subject": "participant_name"}
    assert decided([ProjectFact.model_validate(other)], located) is None
    assert answered("  ") is None
    assert answered("withheld") == Decision(True, "withheld", "your answer")
    assert answered("region only") == Decision(False, "region only", "your answer")
