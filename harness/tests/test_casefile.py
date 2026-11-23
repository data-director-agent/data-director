"""Case files (docs/specs/casefile.md): one run, conversation or project, exported as a filtered
copy of the stores that every reader opens, checked rather than trusted.
"""

from __future__ import annotations

import json
import logging
import zipfile
from pathlib import Path
from typing import Any

import pytest

from dd_harness import casefile
from dd_harness.conductor import Conductor
from dd_harness.projects import ProjectStore
from dd_harness.server import main
from dd_harness.storage import STAGES
from dd_harness.testing import (
    TEST_PRINCIPAL,
    DocumentStub,
    ScriptedAgent,
    document_request,
    grant_token,
    make_conductor,
    message,
    open_case,
    record,
    reply_over,
    request,
    review_of_input,
)
from dd_sdk import security_log
from dd_sdk.agent import AgentResult, RunContext
from dd_sdk.contract.models import Envelope, GroundingMode, InvocationRequest
from dd_sdk.security_log import SecurityEvent
from dd_sdk.testing import security_events


def _delegating(sent: dict[str, str] | None = None) -> ScriptedAgent:
    def behaviour(req: InvocationRequest, ctx: RunContext) -> AgentResult:
        assert ctx.delegate is not None
        if sent is not None:
            sent["token"] = grant_token(ctx)
        return reply_over(ctx, ctx.delegate("fake.none", record()))

    return ScriptedAgent(GroundingMode.DELEGATION, behaviour)


def _conductor(tmp_path: Path) -> tuple[Conductor, ProjectStore]:
    projects = ProjectStore(tmp_path / "projects")
    conductor = make_conductor(
        tmp_path / "runs",
        _delegating(),
        ScriptedAgent(GroundingMode.NONE, review_of_input),
        DocumentStub(),
    )
    conductor.projects = projects
    return conductor, projects


def _turn(conductor: Conductor, req: InvocationRequest, conversation: str) -> Envelope:
    asked = req.model_copy(update={"conversation_id": conversation})
    return conductor.invoke(asked, acting_for=TEST_PRINCIPAL)


@pytest.fixture
def world(tmp_path: Path) -> dict[str, Any]:
    """A project with one conversation of three turns: a delegation with its child, a draft kept
    as a version, and a turn the input check refuses; and a run outside any conversation."""
    conductor, projects = _conductor(tmp_path)
    project = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test", title="Soil")
    conversation = projects.start_conversation(project, acted_for=TEST_PRINCIPAL, caused_by="t")
    delegated = _turn(conductor, request("fake.delegation", message()), conversation)
    draft = _turn(conductor, request("stub.document", document_request()), conversation)
    # A delegation agent accepts a Message, so the input check refuses a record.
    refused = _turn(conductor, request("fake.delegation", record()), conversation)
    elsewhere = conductor.invoke(request("fake.none"), acting_for=TEST_PRINCIPAL)
    return {
        "conductor": conductor,
        "projects": projects,
        "project": project,
        "conversation": conversation,
        "delegated": delegated,
        "draft": draft,
        "refused": refused,
        "elsewhere": elsewhere,
        "out": tmp_path / "out",
    }


def _export(world: dict[str, Any], scope: str, ident: str, name: str = "case") -> Path:
    target: Path = world["out"] / name
    casefile.export(
        target,
        world["conductor"].store,
        world["projects"].log,
        scope,
        ident,
        TEST_PRINCIPAL,
    )
    return target


def _run_ids(case: Path) -> set[str]:
    with open_case(case) as (runs, _):
        return {e["invocation_id"] for e in runs.iter_envelopes()}


def test_a_run_case_holds_the_run_and_what_it_delegated_and_nothing_else(
    world: dict[str, Any],
) -> None:
    parent = world["delegated"]
    case = _export(world, "run", parent.invocation_id)
    [delegation] = parent.delegations
    assert _run_ids(case) == {parent.invocation_id, delegation.delegated_invocation_id}
    assert not (case / "projects").exists()


def test_a_conversation_case_holds_every_turn_and_its_project(world: dict[str, Any]) -> None:
    case = _export(world, "conversation", world["conversation"])
    turns = {world[k].invocation_id for k in ("delegated", "draft", "refused")}
    found = _run_ids(case)
    assert turns <= found and world["elsewhere"].invocation_id not in found
    with open_case(case) as (_, projects):
        assert projects is not None
        assert projects.events(world["project"]) == world["projects"].events(world["project"])


def test_a_project_case_holds_its_log_its_content_and_its_runs(world: dict[str, Any]) -> None:
    case = _export(world, "project", world["project"])
    source: ProjectStore = world["projects"]
    project = world["project"]
    with open_case(case) as (runs, projects):
        assert projects is not None
        assert projects.events(project) == source.events(project)
        assert projects.documents(project) == source.documents(project)
        for envelope in runs.iter_envelopes():
            invocation_id = envelope["invocation_id"]
            stored = world["conductor"].store
            assert envelope == stored.get(invocation_id)
            assert runs.get_request(invocation_id) == stored.get_request(invocation_id)
            assert runs.get_prompts(invocation_id) == stored.get_prompts(invocation_id)
            assert runs.get_artifact(invocation_id, STAGES) == stored.get_artifact(
                invocation_id, STAGES
            )


def test_an_unknown_identifier_is_named_and_writes_nothing(world: dict[str, Any]) -> None:
    for scope in casefile.SCOPES:
        with pytest.raises(LookupError, match=scope):
            _export(world, scope, "0190a000-0000-7000-8000-000000000000", scope)
        assert not (world["out"] / scope).exists()


def test_a_fresh_case_verifies_as_a_directory_and_as_a_zip(world: dict[str, Any]) -> None:
    directory = _export(world, "project", world["project"])
    zipped = _export(world, "project", world["project"], "case.zip")
    for case in (directory, zipped):
        report = casefile.verify(case)
        assert report.passed, report.summary()
        assert len(report.checks) > 1


def test_a_zip_depends_on_its_content_alone(world: dict[str, Any]) -> None:
    zipped = _export(world, "run", world["delegated"].invocation_id, "case.zip")
    with zipfile.ZipFile(zipped) as archive:
        assert {info.date_time for info in archive.infolist()} == {(1980, 1, 1, 0, 0, 0)}


def _failed(report: casefile.VerifyReport) -> list[str]:
    return [check.about for check in report.checks if not check.passed]


def test_verify_finds_a_changed_byte_and_a_missing_file(world: dict[str, Any]) -> None:
    case = _export(world, "conversation", world["conversation"])
    (case / "CASE.md").write_text("changed", encoding="utf-8")
    assert _failed(casefile.verify(case)) == ["files"]
    (case / "timeline.jsonl").unlink()
    assert "files" in _failed(casefile.verify(case))


def test_verify_finds_a_request_that_is_not_what_the_run_hashed(world: dict[str, Any]) -> None:
    case = _export(world, "run", world["elsewhere"].invocation_id)
    path = case / "runs" / world["elsewhere"].invocation_id / "request.json"
    stored = json.loads(path.read_text(encoding="utf-8"))
    stored["input"]["title"] = "Not what the agent was given"
    path.write_text(json.dumps(stored), encoding="utf-8")
    failed = _failed(casefile.verify(case))
    assert "files" in failed
    assert any(about.endswith("input hash") for about in failed)


def test_the_index_puts_runs_that_did_not_succeed_first(world: dict[str, Any]) -> None:
    case = _export(world, "conversation", world["conversation"])
    statuses = {
        e["invocation_id"]: e["outcome"]["status"]
        for e in world["conductor"].store.iter_envelopes(conversation_id=world["conversation"])
    }
    index = (case / "CASE.md").read_text(encoding="utf-8")
    failures, _, every = index.partition("## Every run")
    for invocation_id, status in statuses.items():
        assert (invocation_id in failures) == (status != "succeeded")
        assert invocation_id in every


def test_the_timeline_is_in_time_order_and_names_its_sources(world: dict[str, Any]) -> None:
    case = _export(world, "project", world["project"])
    lines = [json.loads(line) for line in (case / "timeline.jsonl").read_text().splitlines()]
    assert [line["at"] for line in lines] == sorted(line["at"] for line in lines)
    assert {line["kind"] for line in lines} == {"project", "stage", "run"}
    assert all((case / line["file"]).is_file() for line in lines)


def test_exporting_is_a_security_event(
    world: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger=security_log.LOGGER)
    _export(world, "conversation", world["conversation"])
    exported = [
        e for e in security_events(caplog.records) if e["event"] == SecurityEvent.CASE_EXPORTED
    ]
    assert [(e["action"], e["conversation_id"], e["project_id"]) for e in exported] == [
        ("conversation", world["conversation"], world["project"])
    ]


def test_a_case_carries_no_grant_the_harness_sent(tmp_path: Path) -> None:
    sent: dict[str, str] = {}
    conductor = make_conductor(
        tmp_path / "runs", _delegating(sent), ScriptedAgent(GroundingMode.NONE, review_of_input)
    )
    env = conductor.invoke(request("fake.delegation", message()), acting_for=TEST_PRINCIPAL)
    case = tmp_path / "case"
    casefile.export(case, conductor.store, None, "run", env.invocation_id, TEST_PRINCIPAL)
    assert sent["token"]
    for path in case.rglob("*"):
        if path.is_file():
            assert sent["token"] not in path.read_text(encoding="utf-8", errors="replace"), path


def test_the_cli_exports_and_verifies(
    world: dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DD_RUNS_DIR", str(world["conductor"].store.root))
    monkeypatch.setenv("DD_PROJECTS_DIR", str(world["projects"].log.root))
    monkeypatch.setenv("DD_PRINCIPAL_ID", TEST_PRINCIPAL.principal_id)
    monkeypatch.setenv("DD_PRINCIPAL_NAME", "An operator")
    target = world["out"] / "cli.zip"
    assert main(["case", "export", "--project", world["project"], "-o", str(target)]) == 0
    assert "case.json sha256:" in capsys.readouterr().out
    assert main(["case", "verify", str(target)]) == 0
    missing = world["out"] / "missing"
    assert (
        main(
            ["case", "export", "--run", "0190a000-0000-7000-8000-000000000000", "-o", str(missing)]
        )
        == 2
    )
    assert not missing.exists()
