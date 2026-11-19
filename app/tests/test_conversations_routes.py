"""Conversations (#130): starting one, its turns, and whose work is whose (#153)."""

from __future__ import annotations

import asyncio
import re
import threading
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from support import (
    JSON_HEADERS,
    OTHER,
    check_fixture,
    configure_env,
    delegating_app,
    dist_dir,
    new_governance,
    normalised_conversation,
    start,
    turn,
)

from dd_app.app import build_app
from dd_app.governance import (
    Governance,
    TurnConflictError,
    UnknownConversationError,
)
from dd_app.routes.conversations import Conversation
from dd_app.routes.runs import RunResult
from dd_app.turn_body import Turn
from dd_harness.projects import ProjectStore
from dd_harness.testing import (
    TEST_PRINCIPAL,
)
from dd_sdk.contract.models import UUID7_PATTERN, Envelope, InvocationRequest, Principal


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    return configure_env(monkeypatch, tmp_path)


@pytest.fixture
def governance(env: Path) -> Iterator[Governance]:
    yield from new_governance()


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    return dist_dir(tmp_path)


@pytest.fixture
def delegating(env: Path, dist: Path) -> Iterator[tuple[Governance, Any]]:
    """The app over the orchestrator and `example.hello`, each reached over in-process A2A, with
    the orchestrator calling back to the app's own routes, under the app's reference profile. It
    keeps no projects."""
    yield delegating_app(env, dist, None)


@pytest.fixture
def in_projects(env: Path, dist: Path) -> Iterator[tuple[Governance, Any]]:
    """As `delegating`, with each conversation started in a project of its own."""
    yield delegating_app(env, dist, ProjectStore(env / "projects"))


# Conversations (#130): a turn is one invocation of the orchestrator with a `conversation_id`,
# and the server, not the caller, builds its history from the stored turns (docs/specs/app.md).


def test_a_conversation_is_started_with_no_turns(governance: Governance, dist: Path):
    client = TestClient(build_app(governance, dist))
    conversation_id = start(client)
    assert re.fullmatch(UUID7_PATTERN, conversation_id)
    found = client.get(f"/api/conversations/{conversation_id}").json()
    assert found["turns"] == [] and found["history"] == []
    # Listed once it has a turn, since the store is what holds a conversation.
    assert client.get("/api/conversations").json() == []


@pytest.mark.parametrize(
    "conversation_id",
    ["01900000-0000-7000-8000-000000000001", "not-an-id", "01900000-0000-4000-8000-000000000001"],
)
def test_a_conversation_the_app_did_not_start_is_not_found(
    governance: Governance, dist: Path, conversation_id: str
):
    client = TestClient(build_app(governance, dist))
    for response in (
        client.get(f"/api/conversations/{conversation_id}"),
        turn(client, conversation_id, "hello world"),
    ):
        assert response.status_code == 404
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["type"].endswith("conversation-not-found")


def test_each_turn_is_shown_the_turns_before_it(in_projects: tuple[Governance, Any]):
    governance, app = in_projects
    client = TestClient(app)
    conversation_id = start(client)
    first = turn(client, conversation_id, "hello world")
    assert first.status_code == 200
    second = turn(client, conversation_id, "hello again", first.json()["envelope"]["invocation_id"])
    assert second.status_code == 200
    envelopes = [first.json()["envelope"], second.json()["envelope"]]
    for envelope in envelopes:
        assert envelope["conversation_id"] == conversation_id
        assert envelope["outcome"]["status"] == "succeeded"
        assert [d["delegated_agent_id"] for d in envelope["delegations"]] == ["example.hello"]

    store = governance.conductor.store
    shown = [(store.get_request(e["invocation_id"]) or {})["input"] for e in envelopes]
    # The app starts each conversation in an untitled project of its own, so the conductor adds
    # only that no person has named it.
    assert shown[0] == {
        "schema_class": "Message",
        "message_text": "hello world",
        "history": [],
        "project_title_by_researcher": False,
    }
    assert shown[1]["message_text"] == "hello again"
    user, agent = shown[1]["history"]
    assert (user["role"], user["turn_text"]) == ("user", "hello world")
    assert agent["role"] == "agent"
    assert agent["turn_text"] == envelopes[0]["payload"]["reply_text"]
    assert agent["turn_invocation_id"] == envelopes[0]["invocation_id"]

    found = client.get(f"/api/conversations/{conversation_id}").json()
    assert [t["invocation_id"] for t in found["turns"]] == [e["invocation_id"] for e in envelopes]
    for t, envelope in zip(found["turns"], envelopes, strict=True):
        assert [c["invocation_id"] for c in t["children"]] == [
            d["delegated_invocation_id"] for d in envelope["delegations"]
        ]
    (listed,) = client.get("/api/conversations").json()
    assert (listed["conversation_id"], listed["turns"]) == (conversation_id, 2)
    # orchestrator.stub writes no title, so the conversation is named by its first message.
    assert (listed["title"], listed["title_source"]) == ("hello world", "message")
    assert listed["project_id"] == found["project_id"]
    one = client.get("/api/conversations?limit=1")
    assert one.json() == [listed] and "next" not in one.links
    assert client.get("/api/conversations?limit=many").status_code == 400
    check_fixture("conversation-turn.json", normalised_conversation(second.json()), model=RunResult)
    check_fixture("conversation.json", normalised_conversation(found), model=Conversation)


@pytest.mark.requirement("DD-CONVERSATION")
def test_a_question_is_answered_in_the_form(in_projects: tuple[Governance, Any]):
    governance, app = in_projects
    client = TestClient(app)
    conversation_id = start(client)
    first = turn(client, conversation_id, "hi")
    assert first.status_code == 200
    asked = first.json()["envelope"]
    (question,) = asked["payload"]["reply_questions"]
    assert [o["option_value"] for o in question["question_options"]] == ["1", "2", "3"]
    check_fixture(
        "conversation-question.json",
        normalised_conversation(client.get(f"/api/conversations/{conversation_id}").json()),
        model=Conversation,
    )

    def answer(values: list[str], to: str = asked["invocation_id"], **kw: Any) -> Any:
        given = {"answered_key": question["question_key"], "answer_values": values, **kw}
        return turn(
            client,
            conversation_id,
            "Data already collected, being prepared for sharing",
            asked["invocation_id"],
            reply_answers={"answer_to": to, "given_answers": [given]},
        )

    refused = answer(["9"])
    assert refused.status_code == 400
    assert "not an option of the question: 9" in refused.json()["detail"]
    assert answer(["1", "2"]).status_code == 400  # one answer only
    assert answer(["2"], answer_words="ours").status_code == 400  # no answer in words
    from_elsewhere = answer(["2"], to="0190a000-0000-7000-8000-000000000000")
    assert "latest turn" in from_elsewhere.json()["detail"]
    assert answer(["2"], answer_to_typo=True).status_code == 400  # not a QuestionAnswer
    assert len(client.get(f"/api/conversations/{conversation_id}").json()["turns"]) == 1

    answered = answer(["2"])
    assert answered.status_code == 200, answered.json()
    envelope = answered.json()["envelope"]
    stored = governance.conductor.store.get_request(envelope["invocation_id"]) or {}
    assert stored["input"]["reply_answers"] == {
        "answer_to": asked["invocation_id"],
        "given_answers": [{"answered_key": question["question_key"], "answer_values": ["2"]}],
    }
    assert envelope["outcome"]["statement"].startswith("Listed the steps from entry point 2")
    # The answer reads as a normal message in the history; the question is written after the
    # reply that asked it.
    found = client.get(f"/api/conversations/{conversation_id}").json()
    _, agent, again, _ = found["history"]
    assert agent["turn_text"].endswith("(The researcher was offered these to choose one.)")
    assert again["turn_text"] == "Data already collected, being prepared for sharing"
    check_fixture("conversation-answered.json", normalised_conversation(found), model=Conversation)


def test_a_conversation_is_started_in_a_project_of_its_own(governance: Governance, dist: Path):
    client = TestClient(build_app(governance, dist))
    first, second = (
        client.post("/api/conversations", headers=JSON_HEADERS).json() for _ in range(2)
    )
    assert first["project_id"] != second["project_id"]
    store = governance.projects
    assert store is not None
    for started in (first, second):
        assert store.project_of(started["conversation_id"]) == started["project_id"]
        events = store.events(started["project_id"])
        assert [e["event"] for e in events] == ["project_created", "conversation_started"]
        assert {e["acted_for"]["principal_id"] for e in events} == {TEST_PRINCIPAL.principal_id}
        found = client.get(f"/api/conversations/{started['conversation_id']}").json()
        assert (found["project_id"], found["inventory"]) == (started["project_id"], None)


def test_a_conversation_is_started_in_the_project_it_names(governance: Governance, dist: Path):
    client = TestClient(build_app(governance, dist))
    first = client.post("/api/conversations", headers=JSON_HEADERS).json()
    response = client.post("/api/conversations", json={"project_id": first["project_id"]})
    assert response.status_code == 201
    second = response.json()
    assert second["project_id"] == first["project_id"]
    assert second["conversation_id"] != first["conversation_id"]
    store = governance.projects
    assert store is not None
    assert store.project_of(second["conversation_id"]) == first["project_id"]
    events = store.events(first["project_id"])
    assert [e["event"] for e in events] == [
        "project_created",
        "conversation_started",
        "conversation_started",
    ]
    # A null project is a new one, as no body is.
    other = client.post("/api/conversations", json={"project_id": None}).json()
    assert other["project_id"] != first["project_id"]


def test_a_conversation_is_not_started_in_a_project_the_person_may_not_read(
    governance: Governance, dist: Path
):
    client = TestClient(build_app(governance, dist))
    store = governance.projects
    assert store is not None
    someone = Principal(principal_id="https://orcid.org/0000-0002-1694-233X", name="Someone Else")
    theirs = store.create(acted_for=someone, caused_by="test")
    for project_id in (theirs, str(uuid.uuid4()), "../../etc"):
        response = client.post("/api/conversations", json={"project_id": project_id})
        assert response.status_code == 404
        assert response.json()["type"].endswith("project-not-found")
    assert [e["event"] for e in store.events(theirs)] == ["project_created"]


@pytest.mark.parametrize(
    "body",
    [{"project_id": 7}, {"project_id": None, "title": "x"}, ["a"]],
)
def test_a_conversation_start_with_a_malformed_body_is_refused(
    governance: Governance, dist: Path, body: Any
):
    client = TestClient(build_app(governance, dist))
    response = client.post("/api/conversations", json=body)
    assert response.status_code == 400
    assert response.headers["content-type"] == "application/problem+json"


def test_a_cancelled_turn_still_comes_before_the_next(delegating: tuple[Governance, Any]):
    """A turn cancelled (the client went away) runs on to the end in the conductor's thread. A
    message sent again meanwhile is refused, not run twice (#337); once the first is stored, a
    turn that follows it runs and is shown it."""
    governance, _app = delegating
    conductor = governance.conductor
    entered, release = threading.Event(), threading.Event()
    invoke = conductor.invoke

    def held_first(request: InvocationRequest, **kwargs: Any) -> Any:
        if not entered.is_set():
            entered.set()
            release.wait(timeout=30)
        return invoke(request, **kwargs)

    conductor.invoke = held_first  # type: ignore[method-assign]
    conversation_id = governance.start_conversation(TEST_PRINCIPAL)

    def top_level_turns() -> list[dict[str, Any]]:
        return [e for e in conductor.store.iter_envelopes() if not e.get("parent_invocation_id")]

    async def scenario() -> Envelope:
        first = asyncio.create_task(
            governance.turn(
                conversation_id, Turn("orchestrator.stub", "hello world", None), TEST_PRINCIPAL
            )
        )
        await asyncio.to_thread(entered.wait, 30)
        first.cancel()
        with pytest.raises(TurnConflictError, match="still running"):
            await governance.turn(
                conversation_id, Turn("orchestrator.stub", "hello world", None), TEST_PRINCIPAL
            )
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await first
        (stored,) = top_level_turns()
        return await governance.turn(
            conversation_id,
            Turn("orchestrator.stub", "hello again", stored["invocation_id"]),
            TEST_PRINCIPAL,
        )

    try:
        second = asyncio.run(scenario())
    finally:
        release.set()
        conductor.close()

    shown = (conductor.store.get_request(second.invocation_id) or {})["input"]
    user, _agent = shown["history"]
    assert user["turn_text"] == "hello world"
    assert len(top_level_turns()) == 2  # the resend never ran
    assert governance.turn_locks.try_hold(conversation_id) is not None  # the lock was released


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"history": []}, "history"),
        (
            {"input": {}},
            "only `agent_id`, `message_text`, `follows`, `inventory`, `documentation` and "
            "`reply_answers`",
        ),
        ({"message_text": 3}, "as strings"),
        ({"follows": 3}, "must give `follows`"),
        ({"message_text": "  "}, "empty"),
    ],
)
def test_a_malformed_turn_is_refused_and_nothing_runs(
    delegating: tuple[Governance, Any], body: dict[str, Any], detail: str
):
    governance, app = delegating
    client = TestClient(app)
    conversation_id = start(client)
    response = turn(client, conversation_id, "hello world", **body)
    assert response.status_code == 400
    assert response.headers["content-type"] == "application/problem+json"
    assert detail in response.json()["detail"]
    assert list(governance.conductor.store.iter_envelopes()) == []


def test_a_turn_must_name_the_turn_it_follows(delegating: tuple[Governance, Any]):
    governance, app = delegating
    client = TestClient(app)
    response = client.post(
        f"/api/conversations/{start(client)}/turns",
        json={"agent_id": "orchestrator.stub", "message_text": "hello world"},
    )
    assert response.status_code == 400
    assert "must give `follows`" in response.json()["detail"]
    assert list(governance.conductor.store.iter_envelopes()) == []


@pytest.mark.parametrize("follows", [None, "01900000-0000-7000-8000-000000000001"])
def test_a_turn_that_does_not_follow_the_latest_is_refused_and_nothing_runs(
    delegating: tuple[Governance, Any], follows: str | None
):
    """A message sent again after its first attempt was stored names the turn before it, so it
    is refused rather than run twice (#337, docs/specs/orchestration.md)."""
    governance, app = delegating
    client = TestClient(app)
    conversation_id = start(client)
    assert turn(client, conversation_id, "hello world").status_code == 200
    stored = list(governance.conductor.store.iter_envelopes())
    response = turn(client, conversation_id, "hello world", follows)
    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"].endswith("turn-conflict")
    assert stored[-1]["invocation_id"] in response.json()["detail"]
    assert list(governance.conductor.store.iter_envelopes()) == stored


def test_a_turn_goes_only_to_the_orchestrator_the_profile_names(
    delegating: tuple[Governance, Any],
):
    governance, app = delegating
    client = TestClient(app)
    response = turn(client, start(client), "hello world", agent_id="example.hello")
    assert response.status_code == 400
    assert "'orchestrator.stub', not 'example.hello'" in response.json()["detail"]
    assert list(governance.conductor.store.iter_envelopes()) == []


def test_a_turn_that_is_not_json_is_refused(governance: Governance, dist: Path):
    client = TestClient(build_app(governance, dist))
    response = client.post(
        f"/api/conversations/{start(client)}/turns", content=b"{", headers=JSON_HEADERS
    )
    assert response.status_code == 400


def test_a_turn_to_an_unknown_agent_is_refused_before_it_runs(governance: Governance, dist: Path):
    client = TestClient(build_app(governance, dist))
    response = client.post(
        f"/api/conversations/{start(client)}/turns",
        json={"agent_id": "no.such.agent", "message_text": "hello", "follows": None},
    )
    assert response.status_code == 400
    assert response.json()["type"].endswith("request-refused")
    assert list(governance.conductor.store.iter_envelopes()) == []


# Whose work is whose (#153): each person sees and continues only their own runs and
# conversations, and someone else's is answered as one that does not exist.


@pytest.mark.parametrize("fixture", ["delegating", "in_projects"])
def test_a_conversation_and_its_delegations_are_its_starters_alone(
    fixture: str, request: pytest.FixtureRequest
):
    governance, _app = request.getfixturevalue(fixture)
    conversation_id = governance.start_conversation(OTHER)
    # Not yet given a turn: its starter may read it, nobody else.
    assert governance.conversation(conversation_id, OTHER) is not None
    assert governance.conversation(conversation_id, TEST_PRINCIPAL) is None
    with pytest.raises(UnknownConversationError):
        asyncio.run(
            governance.turn(
                conversation_id, Turn("orchestrator.stub", "hello world", None), TEST_PRINCIPAL
            )
        )
    assert list(governance.conductor.store.iter_envelopes()) == []

    answered = asyncio.run(
        governance.turn(conversation_id, Turn("orchestrator.stub", "hello world", None), OTHER)
    )
    envelope = answered.to_document()
    (child,) = envelope["delegations"]

    # The delegated child is the starter's, as its parent is.
    assert {r["invocation_id"] for r in governance.runs(OTHER).items} == {
        envelope["invocation_id"],
        child["delegated_invocation_id"],
    }
    assert governance.runs(TEST_PRINCIPAL).items == []
    for invocation_id in (envelope["invocation_id"], child["delegated_invocation_id"]):
        assert governance.stored_run(invocation_id, OTHER) is not None
        assert governance.stored_run(invocation_id, TEST_PRINCIPAL) is None
    listed = governance.conversations(OTHER).items
    assert [c["conversation_id"] for c in listed] == [conversation_id]
    assert governance.conversations(TEST_PRINCIPAL).items == []
    assert governance.conversation(conversation_id, TEST_PRINCIPAL) is None
    with pytest.raises(UnknownConversationError):
        asyncio.run(
            governance.turn(
                conversation_id,
                Turn("orchestrator.stub", "hello again", envelope["invocation_id"]),
                TEST_PRINCIPAL,
            )
        )
    assert len(governance.runs(OTHER).items) == 2
