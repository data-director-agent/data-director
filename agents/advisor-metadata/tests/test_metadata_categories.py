"""advisor.metadata suggests an entry from a named subject classification only from the fields the
tool gateway returned, and each suggestion cites the field's own record (#703). The classification
server is the real `mcp-subjects`, served in process behind the harness's gateway; the model is a
`FakeModel`. No network, no key."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest
from test_metadata_agent import sample

from dd_agent_advisor_metadata.agent import MetadataLibrarian
from dd_agent_advisor_metadata.categories import SERVER
from dd_agent_advisor_metadata.evals.drafting import subjects_gateway
from dd_agent_advisor_metadata.suggest import ModelSuggester, TemplateSuggester
from dd_agent_advisor_metadata.testing import asked_in, suggestion_reply
from dd_harness.testing import TEST_PRINCIPAL, make_conductor, request
from dd_harness.testing.tools import tools_profile
from dd_sdk.contract.models import (
    Document,
    DocumentQuestion,
    Envelope,
    GroundingMode,
    OutcomeStatus,
)
from dd_sdk.model import ModelRequest
from dd_sdk.testing import FakeModel

GRANTED = {"advisor.metadata": [SERVER]}
SOIL = "4106"
SCHEME = "ANZSRC Fields of Research"

type Choose = Callable[[list[dict[str, Any]]], Mapping[str, str | None]]


def replying(choose: Choose) -> Callable[[ModelRequest], str]:
    return lambda sent: suggestion_reply(choose(asked_in(sent)))


def categories(asked: list[dict[str, Any]], code: str = SOIL) -> dict[str, str | None]:
    """`code` for every question that offers choices; nothing else."""
    return {q["question_id"]: code for q in asked if q.get("choose_from")}


def run(
    tmp_path: Path,
    choose: Choose = categories,
    *,
    grant: bool = True,
    model: bool = True,
) -> tuple[Envelope, bool, FakeModel]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    fake = FakeModel(replying(choose))
    suggester = ModelSuggester(fake) if model else TemplateSuggester()
    conductor = make_conductor(
        tmp_path / "runs",
        MetadataLibrarian(suggester=suggester),
        profile=tools_profile(tmp_path, GRANTED if grant else {}),
        gateway=subjects_gateway(),
    )
    env = conductor.invoke(request("advisor.metadata", sample()), acting_for=TEST_PRINCIPAL)
    return env, conductor.grounding_reports[env.invocation_id].passed, fake


def category_questions(env: Envelope) -> list[DocumentQuestion]:
    document = env.payload_as(Document)
    entries = json.loads(document.document_text)["subjects"]
    return [
        q
        for q in document.document_questions
        if (q.gap_property or "").startswith("subjects[")
        and entries[int((q.gap_property or "")[9:].split("]")[0])].get("subjectScheme")
    ]


@pytest.mark.requirement("DD-TOOL-GATEWAY", "DD-GROUNDING-MODE")
def test_a_suggested_category_is_a_field_the_gateway_returned_and_cites_its_record(
    tmp_path: Path,
) -> None:
    env, passed, fake = run(tmp_path)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.grounding_mode == GroundingMode.RETRIEVAL and passed

    # The model chose from the scheme's own fields, retrieved before it was called.
    offered = [q for q in asked_in(fake.sent[0]) if q.get("choose_from")]
    assert offered and {"code": SOIL, "label": "Soil sciences"} in offered[0]["choose_from"]

    [question] = category_questions(env)
    assert question.suggested_answer == "Soil sciences"
    term = f"tool:{SERVER}/anzsrc-for:{SOIL}"
    assert term in {r.source_id for r in env.tool_retrievals}
    cited = {ref.source_id for ref in env.payload_as(Document).grounded_on}
    assert term in cited
    [evidence] = [e for e in env.evidence if e.source_id == term]
    assert evidence.content is not None and evidence.content["label"] == "Soil sciences"


def test_the_record_is_the_same_whether_or_not_a_category_is_suggested(tmp_path: Path) -> None:
    suggested, _, _ = run(tmp_path / "a")
    plain, _, _ = run(tmp_path / "b", grant=False)
    assert suggested.payload_as(Document).document_text == plain.payload_as(Document).document_text


@pytest.mark.parametrize(
    "choose",
    [
        lambda asked: categories(asked, "9999"),  # not a field of the scheme
        lambda asked: categories(asked, "Soil science and agronomy"),  # a label of its own
    ],
)
def test_a_code_the_scheme_does_not_hold_is_dropped_and_said(
    tmp_path: Path, choose: Choose
) -> None:
    env, passed, _ = run(tmp_path, choose)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED and passed
    assert all(q.suggested_answer is None for q in category_questions(env))
    assert not any(
        ref.source_id.startswith("tool:") for ref in env.payload_as(Document).grounded_on
    )


def test_with_no_grant_no_category_is_suggested_and_the_outcome_says_why(tmp_path: Path) -> None:
    env, passed, fake = run(tmp_path, grant=False)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED and passed
    assert all(q.suggested_answer is None for q in category_questions(env))
    assert not env.tool_retrievals
    # The model was not offered the category question at all.
    assert not any(q.get("choose_from") for q in asked_in(fake.sent[0]))
    assert SCHEME in env.outcome.statement


def test_the_template_suggester_retrieves_nothing_and_suggests_no_category(
    tmp_path: Path,
) -> None:
    env, passed, fake = run(tmp_path, model=False)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED and passed
    assert not fake.sent and not env.tool_retrievals
    assert all(q.suggested_answer is None for q in category_questions(env))
