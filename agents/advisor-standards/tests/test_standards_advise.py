"""The model advisor through the conductor, with a scripted model: its search tool and budget,
what it may add beside the rules' picks, and what the agent refuses to take from it
(`advise.py`)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

import pytest

from dd_agent_advisor_standards import testing as fakes
from dd_agent_advisor_standards.advise import SEARCH, SUBMIT, SYSTEM_PROMPT, ModelAdvisor
from dd_agent_advisor_standards.agent import StandardsAgent
from dd_agent_advisor_standards.classes import Recommendation, Recommendations
from dd_agent_advisor_standards.fairsharing.records import TERMINOLOGY, Record
from dd_harness.testing import TEST_PRINCIPAL
from dd_sdk.contract.models import Derivation, Envelope, OutcomeStatus
from dd_sdk.model import (
    ModelCallError,
    ModelRequest,
    ModelResponse,
    ToolCall,
    ToolResults,
    Usage,
    declared,
)
from dd_sdk.registry import Hit, Query

MODEL = "claude-test"

WRB = Record(
    fairsharing_id="FAIRsharing.test-wrb",
    doi="10.25504/FAIRsharing.test-wrb",
    name="World Reference Base for Soil Resources",
    abbreviation="WRB",
    record_type=TERMINOLOGY,
    status="ready",
    description="The international soil classification system, a controlled vocabulary of soil "
    "reference groups.",
    subjects=["Soil science"],
)


class HiddenRetrieval(fakes.FakeRetrieval):
    """The fake registry, with `hidden` records found only by the model's own searches."""

    def __init__(self, hidden: list[Record]) -> None:
        super().__init__()
        self.hidden = hidden

    def search(self, query: Query) -> list[Hit]:
        hits = super().search(query)
        if query.label == "model search":
            hits = [Hit(record=r, lexical_score=1.0) for r in self.hidden] + hits
        return hits


def use(*calls: tuple[str, dict[str, Any]]) -> ModelResponse:
    tool_calls = tuple(
        ToolCall(id=f"toolu_{n}", name=name, input=args) for n, (name, args) in enumerate(calls)
    )
    return ModelResponse(
        "", model_id=MODEL, usage=Usage(100, 10), tool_calls=tool_calls, stop="tool_use"
    )


def submit(
    rationales: list[dict[str, Any]] | None = None,
    additions: list[dict[str, Any]] | None = None,
    concerns: list[dict[str, Any]] | None = None,
) -> ModelResponse:
    return use(
        (
            SUBMIT,
            {
                "rationales": rationales or [],
                "additions": additions or [],
                "concerns": concerns or [],
            },
        )
    )


def search(text: str, record_type: str | None = None) -> ModelResponse:
    args: dict[str, Any] = {"text": text}
    if record_type:
        args["record_type"] = record_type
    return use((SEARCH.name, args))


Turn = ModelResponse | Exception | Callable[["ScriptedModel"], ModelResponse]


@dataclass
class ScriptedModel:
    """Plays back one turn per call and keeps each request. A turn may be a function of the
    model, called when it is due, so it can name a record by the number an earlier call gave it."""

    turns: list[Turn]
    model_id: str = MODEL
    provider: str = "fake"
    hosting: Literal["hosted", "local"] = "hosted"
    sent: list[ModelRequest] = field(default_factory=list)

    def send(self, request: ModelRequest) -> ModelResponse:
        self.sent.append(request)
        if not self.turns:
            raise AssertionError("the model was called more often than scripted")
        turn = self.turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        if isinstance(turn, ModelResponse):
            return turn
        return turn(self)

    def prompt(self) -> str:
        first = self.sent[0].messages[0]
        assert isinstance(first, dict)
        return str(first["content"])

    def results(self, n: int) -> list[str]:
        """The tool results sent with call `n`."""
        last = self.sent[n].messages[-1]
        assert isinstance(last, ToolResults)
        return [r.content for r in last.results]


def number(model: ScriptedModel, name: str, n: int = 0) -> str:
    """The number the record called `name` was given in call `n`'s prompt or tool results."""
    text = model.prompt() if n == 0 else "\n".join(model.results(n))
    for block in text.split("<record ")[1:]:
        if f"name: {name}" in block:
            return block.split('number="', 1)[1].split('"', 1)[0]
    raise AssertionError(f"{name} was not numbered")


def invoke(
    runs_dir: Path, model: ScriptedModel, retrieval: Any = None, max_lookups: int = 4
) -> Envelope:
    agent = StandardsAgent(
        retrieval=retrieval or fakes.FakeRetrieval(),
        explainer=ModelAdvisor(model, max_lookups),
    )
    agent.spec = replace(agent.spec, models=(declared(model),))
    conductor = fakes.make_conductor(runs_dir, standards=agent, crate=False)
    env: Envelope = conductor.invoke(fakes.request("advisor.standards"), acting_for=TEST_PRINCIPAL)
    report = conductor.grounding_reports[env.invocation_id]
    assert report.passed, report.violations
    return env


def items(env: Envelope) -> list[Recommendation]:
    return env.payload_as(Recommendations).items


def cited(item: Recommendation) -> str:
    return item.grounded_on[0].source_id


def scripted(*turns: Turn) -> ScriptedModel:
    return ScriptedModel(list(turns))


# --- the rules' picks ------------------------------------------------------------------------


@pytest.mark.requirement("DD-GROUNDED-PAYLOAD", "C14.1")
def test_a_rationale_is_the_models_and_a_pick_without_one_keeps_the_template(
    runs_dir: Path,
) -> None:
    model = scripted(
        lambda m: submit(
            rationales=[
                {
                    "record": number(m, "AGROVOC Multilingual Thesaurus"),
                    "target": "dataset",
                    "rationale": "AGROVOC covers soil science terms.",
                }
            ]
        )
    )
    env = invoke(runs_dir, model)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    by_record = {(cited(i), i.target): i for i in items(env)}
    agrovoc = by_record[(fakes.AGROVOC.fairsharing_id, "dataset")]
    assert agrovoc.rationale_derivation == Derivation.MODEL
    assert agrovoc.selection_derivation == Derivation.LEXICAL
    others = [i for k, i in by_record.items() if k[0] != fakes.AGROVOC.fairsharing_id]
    assert others and all(i.rationale_derivation == Derivation.TEMPLATE for i in others)


def test_a_concern_is_shown_beside_a_pick_and_never_removes_it(runs_dir: Path) -> None:
    template = invoke(runs_dir / "a", scripted(submit()))
    model = scripted(
        lambda m: submit(
            concerns=[{"record": number(m, "Comma-separated values"), "concern": "Doubtful."}]
        )
    )
    env = invoke(runs_dir / "b", model)
    assert [(cited(i), i.target) for i in items(env)] == [
        (cited(i), i.target) for i in items(template)
    ]
    csv = [i for i in items(env) if cited(i) == fakes.CSV.fairsharing_id]
    assert csv and all(i.concern == "Doubtful." for i in csv)
    assert all(i.concern is None for i in items(env) if cited(i) != fakes.CSV.fairsharing_id)


def test_a_rationale_naming_another_identifier_is_replaced(runs_dir: Path) -> None:
    model = scripted(
        lambda m: submit(
            rationales=[
                {
                    "record": number(m, "Comma-separated values"),
                    "target": "dataset",
                    "rationale": "Use FAIRsharing.made-up instead.",
                }
            ]
        )
    )
    env = invoke(runs_dir, model)
    [csv] = [i for i in items(env) if cited(i) == fakes.CSV.fairsharing_id]
    assert csv.rationale_derivation == Derivation.TEMPLATE
    assert "made-up" not in csv.rationale


# --- additions -------------------------------------------------------------------------------


@pytest.mark.requirement("DD-GROUNDED-PAYLOAD", "DD-EVIDENCE")
def test_a_record_the_model_found_is_added_and_cited_from_evidence(runs_dir: Path) -> None:
    model = scripted(
        search("soil classification", TERMINOLOGY),
        lambda m: submit(
            additions=[
                {
                    "record": number(m, WRB.name, 1),
                    "kind": "controlled_vocabulary",
                    "target": "dataset",
                    "rationale": "The soil reference groups suit a soil survey.",
                }
            ]
        ),
    )
    env = invoke(runs_dir, model, retrieval=HiddenRetrieval([WRB]))
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    [wrb] = [i for i in items(env) if cited(i) == WRB.fairsharing_id]
    assert (wrb.selection_derivation, wrb.classification_derivation) == (
        Derivation.MODEL,
        Derivation.MODEL,
    )
    assert wrb.rationale_derivation == Derivation.MODEL and wrb.score is None and wrb.notes
    assert WRB.fairsharing_id in {e.source_id for e in env.evidence}
    root = {g.source_id for g in env.payload_as(Recommendations).grounded_on}
    assert WRB.fairsharing_id in root
    assert "search_fairsharing" in [t.name for t in model.sent[0].tools]


@pytest.mark.parametrize(
    ("record", "kind", "target"),
    [
        pytest.param("S99", "controlled_vocabulary", "dataset", id="unknown number"),
        pytest.param(
            "Comma-separated values", "controlled_vocabulary", "dataset", id="wrong record type"
        ),
        pytest.param("Comma-separated values", "data_format", "dataset", id="repeats a pick"),
        pytest.param("Old soil vocabulary", "controlled_vocabulary", "dataset", id="deprecated"),
        pytest.param(
            "ISO 8601 Date and time format", "field_format", "field:no_such", id="unknown field"
        ),
        pytest.param("ISO 8601 Date and time format", "field_format", "dataset", id="no field"),
    ],
)
def test_an_addition_the_agent_cannot_check_is_dropped_and_said(
    runs_dir: Path, record: str, kind: str, target: str
) -> None:
    def turn(m: ScriptedModel) -> ModelResponse:
        handle = record if record.startswith("S9") else number(m, record)
        claim = {"record": handle, "kind": kind, "target": target, "rationale": "Fits."}
        return submit(additions=[claim])

    template = invoke(runs_dir / "a", scripted(submit()))
    env = invoke(runs_dir / "b", scripted(turn))
    assert env.outcome.status == OutcomeStatus.SUCCEEDED
    assert all(i.selection_derivation == Derivation.LEXICAL for i in items(env))
    assert len(items(env)) == len(items(template))
    assert "dropped" in env.outcome.statement


def test_additions_are_capped_per_kind(runs_dir: Path) -> None:
    hidden = [
        WRB.model_copy(
            update={"fairsharing_id": f"FAIRsharing.test-v{n}", "name": f"Soil vocabulary {n}"}
        )
        for n in range(5)
    ]

    def turn(m: ScriptedModel) -> ModelResponse:
        return submit(
            additions=[
                {
                    "record": number(m, r.name, 1),
                    "kind": "controlled_vocabulary",
                    "target": "dataset",
                    "rationale": "Fits.",
                }
                for r in hidden
            ]
        )

    env = invoke(
        runs_dir, scripted(search("soil vocabulary"), turn), retrieval=HiddenRetrieval(hidden)
    )
    added = [i for i in items(env) if i.selection_derivation == Derivation.MODEL]
    assert 0 < len(added) < len(hidden)
    assert "dropped" in env.outcome.statement


# --- the search budget -----------------------------------------------------------------------


def test_searches_beyond_the_budget_are_refused(runs_dir: Path) -> None:
    model = scripted(search("soil"), search("soil horizons"), submit())
    invoke(runs_dir, model, max_lookups=1)
    assert [t.name for t in model.sent[1].tools] == [SUBMIT]
    assert "No searches are left" in model.results(2)[0]


def test_no_search_is_offered_when_none_is_allowed(runs_dir: Path) -> None:
    model = scripted(submit())
    invoke(runs_dir, model, max_lookups=0)
    assert [t.name for t in model.sent[0].tools] == [SUBMIT]


# --- falling back ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "turns",
    [
        pytest.param([ModelResponse("", refused=True, model_id=MODEL)], id="declined"),
        pytest.param([ModelCallError("unreachable")], id="unreachable"),
        pytest.param([ModelResponse("I think so.", model_id=MODEL)] * 2, id="never submits"),
        pytest.param(
            [use((SUBMIT, {"additions": "not a list"}))] + [ModelResponse("", model_id=MODEL)] * 2,
            id="invalid submission",
        ),
    ],
)
def test_without_a_submission_the_template_is_used_and_said(
    runs_dir: Path, turns: list[Turn]
) -> None:
    env = invoke(runs_dir, scripted(*turns))
    assert env.outcome.status == OutcomeStatus.SUCCEEDED
    assert all(i.rationale_derivation == Derivation.TEMPLATE for i in items(env))
    assert all(i.selection_derivation == Derivation.LEXICAL for i in items(env))
    assert "template was used" in env.outcome.statement


# --- what the model is sent ------------------------------------------------------------------


def test_the_model_is_sent_metadata_and_numbered_records_only(runs_dir: Path) -> None:
    model = scripted(submit())
    invoke(runs_dir, model)
    request = model.sent[0]
    assert request.system == SYSTEM_PROMPT
    prompt = model.prompt()
    assert "untrusted" in prompt and 'number="S1"' in prompt and "rule_picks=" in prompt
    # Records are named by number, not by FAIRsharing identifier.
    assert "FAIRsharing.test-" not in prompt
