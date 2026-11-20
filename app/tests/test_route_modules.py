"""Each route module on its own: mounted without the rest of the app, and its request models
refusing a malformed body with the refusal that names what was wrong (#975)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.testclient import TestClient
from support import JSON_HEADERS, configure_env, dist_dir, new_governance

from dd_app.deployment_view import DeploymentView
from dd_app.project_service import ProjectService
from dd_app.reads import Reads
from dd_app.routes import conversations, progress, projects, runs
from dd_app.routes.common import RUN_REFUSED, Deps, RequestBody
from dd_app.routes.conversations import SendTurn, StartConversation
from dd_app.routes.progress import ChooseEntry, IntakeAnswer
from dd_app.routes.projects import CreateProject
from dd_app.turn_body import Turn, parse_turn
from dd_harness.testing import TEST_PRINCIPAL

TURN = {"agent_id": "orchestrator.stub", "message_text": "Hello", "follows": None}


@pytest.fixture
def deps(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Deps]:
    configure_env(monkeypatch, tmp_path)
    for governance in new_governance():
        yield Deps(
            governance=governance,
            projects=ProjectService.over(governance),
            reads=Reads(governance),
            deployment=DeploymentView(governance),
            web_dist=dist_dir(tmp_path),
            identity={},
        )


def alone(module: Any, deps: Deps) -> TestClient:
    return TestClient(Starlette(routes=module.routes(deps)))


def refusal(model: type[RequestBody], body: Any) -> str:
    with pytest.raises(ValidationError) as caught:
        model.model_validate(body)
    return model.refusal_for(caught.value)


def test_a_module_serves_its_routes_and_no_others(deps: Deps) -> None:
    client = alone(runs, deps)
    assert client.get("/api/runs").status_code == 200
    assert client.get("/api/projects").status_code == 404


def test_a_malformed_run_is_refused_by_its_model(deps: Deps) -> None:
    response = alone(runs, deps).post("/api/runs", json={"agent_id": 1, "input": {}})
    assert response.status_code == 400
    body = response.json()
    assert (body["type"].rsplit("/", 1)[1], body["title"]) == ("request-refused", RUN_REFUSED)


def test_a_project_route_alone_still_checks_the_persons_role(deps: Deps) -> None:
    client = alone(projects, deps)
    created = client.post("/api/projects", json={"title": "Soil cores"})
    assert created.status_code == 201
    project_id = created.json()["project_id"]
    renamed = client.put(f"/api/projects/{project_id}/title", json={"title": "Peat cores"})
    assert renamed.status_code == 200
    missing = client.put("/api/projects/01900000-0000-7000-8000-000000000009/title", json={})
    assert missing.status_code == 404


def test_a_conversation_started_with_no_body_has_a_project_of_its_own(deps: Deps) -> None:
    started = alone(conversations, deps).post("/api/conversations", headers=JSON_HEADERS)
    assert started.status_code == 201
    assert started.json()["project_id"] is not None


def test_progress_refuses_a_boolean_for_an_entry_point(deps: Deps) -> None:
    assert deps.governance.projects is not None
    project_id = deps.governance.projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    path = f"/api/projects/{project_id}/progress/entry"
    response = alone(progress, deps).put(path, json={"entry": True})
    assert response.status_code == 400
    assert response.json()["detail"] == ChooseEntry.field_refusals["entry"]


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({**TURN, "agent_id": 7}, "agent_id"),
        ({k: v for k, v in TURN.items() if k != "follows"}, "follows"),
        ({**TURN, "follows": 3}, "follows"),
        ({**TURN, "inventory": []}, "inventory"),
        (
            {**TURN, "documentation": {"name": "a.md", "media_type": "text/markdown"}},
            "documentation",
        ),
        (
            {**TURN, "documentation": {"name": "a", "media_type": "b", "text": "c", "x": 1}},
            "documentation",
        ),
        ({**TURN, "reply_answers": {"answer_to": "nope"}}, "reply_answers"),
    ],
)
def test_a_turn_names_the_field_it_refuses(body: dict[str, Any], field: str) -> None:
    assert refusal(SendTurn, body) == SendTurn.field_refusals[field]


def test_a_turn_stream_takes_a_document_as_text_or_as_a_file() -> None:
    """The stream's `forwardedProps` take a document as the route does (`parse_turn`): its text,
    or a Word document's or PDF's bytes as base64, which the server reads (#961)."""
    text = {"name": "a.md", "media_type": "text/markdown", "text": "t"}
    as_text = parse_turn({**TURN, "documentation": text})
    assert isinstance(as_text, Turn) and as_text.documentation is not None
    assert (as_text.documentation.text, as_text.documentation.data) == ("t", None)
    pdf = {"name": "a.pdf", "media_type": "application/pdf", "data": "JVBERg=="}
    as_file = parse_turn({**TURN, "documentation": pdf})
    assert isinstance(as_file, Turn) and as_file.documentation is not None
    assert as_file.documentation.data == b"%PDF"
    for wrong in ({**pdf, "data": "not base64!"}, {**pdf, "text": "t"}, {"name": "a.pdf"}):
        refused = parse_turn({**TURN, "documentation": wrong})
        assert isinstance(refused, Response) and refused.status_code == 400


def test_a_turn_with_a_field_it_does_not_take_names_it() -> None:
    assert "colour" in refusal(SendTurn, {**TURN, "colour": "red"})
    assert "colour" in refusal(StartConversation, {"colour": "red"})
    assert "colour" in refusal(CreateProject, {"colour": "red"})


def test_a_turn_refuses_a_history_and_an_empty_message() -> None:
    with_history = refusal(SendTurn, {**TURN, "history": []})
    empty = refusal(SendTurn, {**TURN, "message_text": "  "})
    assert with_history not in SendTurn.field_refusals.values()
    assert empty not in (with_history, SendTurn.refusal)


def test_a_body_that_is_not_an_object_gets_the_models_own_refusal() -> None:
    assert refusal(SendTurn, []) == SendTurn.refusal
    assert refusal(IntakeAnswer, {"answer_values": [1]}) == IntakeAnswer.refusal


def test_a_turn_attaching_only_an_inventory_needs_no_words() -> None:
    turn = SendTurn.model_validate({**TURN, "message_text": "", "inventory": {}})
    assert turn.attached() is None
