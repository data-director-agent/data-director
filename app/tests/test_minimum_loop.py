"""The minimum loop, end to end, through the app as a researcher's browser drives it (#204).

A researcher inventories a folder, chooses ORDA, has the metadata record, README and data
dictionary drafted, approves them (the record after an edit), validates the project and downloads
its deposit package. The test then reads the package's audit trail: every run behind an approved
version and every decision is in it.

The agents are the in-tree ones on their deterministic paths, served in memory over A2A. Replacing
one with another that serves the same steps changes `AGENTS` alone; nothing else here names an
agent class. The repository's requirements are the deployment's own (`app/config/repositories`).
"""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from starlette.testclient import TestClient
from support import APP_URL, ORDA, configure_env, dist_dir, pin_export

from dd_agent_advisor_documentation.agent import build as build_documentation
from dd_agent_advisor_files.agent import build as build_files
from dd_agent_advisor_metadata.agent import build as build_metadata
from dd_agent_orchestrator_stub.agent import build as build_orchestrator
from dd_app.app import build_app
from dd_app.config import settings_from_env
from dd_app.governance import Governance
from dd_harness.deposit import (
    INVENTORY_NAME,
    LOG_NAME,
    PROVENANCE_NAME,
    REPORT_NAME,
    REQUIREMENTS_NAME,
    STATEMENT_NAME,
)
from dd_harness.testing import TEST_PRINCIPAL, asgi_client_factory, in_process
from dd_inventory.scan import make_inventory

# The loop's agents: the orchestrator first, then each agent a step is delegated to. A later
# sprint replaces an entry here, and nothing else in this module.
AGENTS: tuple[Callable[[], Any], ...] = (
    build_orchestrator,
    build_files,
    build_metadata,
    build_documentation,
)
SAMPLE = Path(__file__).resolve().parent / "fixtures" / "minimum-loop"
MADE_AT = datetime(2026, 11, 1, 9, tzinfo=UTC)
# The drafting steps of the Blueprint's process flow, and the documents each drafts.
DRAFTING = {
    "preparation.metadata": {"metadata_record"},
    "preparation.documentation": {"readme", "data_dictionary"},
}
# What the researcher writes into the drafted record before approving it: what ORDA's form asks
# for that the drafter leaves for a person (app/config/repositories/overrides/orda.yaml).
WRITTEN_BY_THE_RESEARCHER: dict[str, Any] = {
    "titles": [{"title": "Soil cores from two Sheffield sites, 2024"}],
    "creators": [
        {
            "name": "Carberry, Josiah",
            "nameType": "Personal",
            "nameIdentifiers": [
                {
                    "nameIdentifier": TEST_PRINCIPAL.principal_id,
                    "nameIdentifierScheme": "ORCID",
                }
            ],
        }
    ],
    "types": {"resourceTypeGeneral": "Dataset"},
    "subjects": [
        {"subject": "Soil sciences", "subjectScheme": "ANZSRC Fields of Research"},
        {"subject": "soil organic carbon"},
    ],
    "descriptions": [
        {
            "description": "Organic carbon and pH of soil cores taken at two depths.",
            "descriptionType": "Abstract",
        }
    ],
    "rightsList": [
        {
            "rights": "Creative Commons Attribution 4.0 International",
            "rightsIdentifier": "CC-BY-4.0",
            "rightsUri": "https://creativecommons.org/licenses/by/4.0/legalcode",
        }
    ],
}
REASON = "Wrote the title, authors, categories, keywords, description and licence."


@pytest.fixture
def governance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Governance]:
    configure_env(monkeypatch, tmp_path)
    monkeypatch.setenv("DD_SOURCES_CONFIG", str(pin_export(tmp_path / "re3data")))
    yield Governance.create(settings_from_env(), APP_URL)


@pytest.fixture
def client(governance: Governance, tmp_path: Path) -> TestClient:
    """The app, with each agent served in memory and the orchestrator calling back to the app's
    own routes to delegate, as it reaches the deployed app over HTTP."""
    served: dict[str, Any] = {}

    def app_client(base_url: str, timeout_s: float) -> httpx.AsyncClient:
        return asgi_client_factory(served["app"])(base_url, timeout_s)

    # Registered before the app is built, which reads what the registry holds.
    orchestrator, *specialists = AGENTS
    governance.conductor.registry.add(
        in_process(orchestrator(), delegate_client_factory=app_client)
    )
    for build in specialists:
        governance.conductor.registry.add(in_process(build()))
    served["app"] = app = build_app(governance, dist_dir(tmp_path))
    return TestClient(app)


class Researcher:
    """One researcher in one conversation, sending what the shell sends."""

    def __init__(self, client: TestClient, orchestrator: str) -> None:
        self.client = client
        self.orchestrator = orchestrator
        started = client.post("/api/conversations")
        assert started.status_code == 201, started.json()
        self.conversation_id: str = started.json()["conversation_id"]
        self.project_id: str = started.json()["project_id"]
        self.project = f"/api/projects/{self.project_id}"
        self.latest: dict[str, Any] | None = None

    def say(self, text: str, choose: str | None = None, **extra: Any) -> dict[str, Any]:
        body: dict[str, Any] = {
            "agent_id": self.orchestrator,
            "message_text": text,
            "follows": self.latest["invocation_id"] if self.latest else None,
            **extra,
        }
        if choose is not None:
            assert self.latest is not None
            body["choice_answer"] = {
                "answer_to": self.latest["invocation_id"],
                "answer_values": [choose],
            }
        response = self.client.post(f"/api/conversations/{self.conversation_id}/turns", json=body)
        assert response.status_code == 200, response.json()
        envelope: dict[str, Any] = response.json()["envelope"]
        assert envelope["outcome"]["status"] == "succeeded", envelope["outcome"]
        self.latest = envelope
        return envelope

    def offered(self) -> list[str]:
        assert self.latest is not None
        question = self.latest["payload"].get("reply_question") or {}
        return [option["option_value"] for option in question.get("question_options", [])]

    def take_step(self, step: str) -> dict[str, Any]:
        """Choose `step` from what the orchestrator offers, skipping, as a researcher may, each
        step it suggests first that this loop does not need."""
        for _ in range(20):
            self.say("What next?")
            offered = self.offered()
            if step in offered:
                return self.say(f"Let's do {step}.", choose=step)
            skip = next(s for s in offered if s not in DRAFTING)
            marked = self.client.put(
                f"{self.project}/progress/steps/{skip}", json={"mark": "skipped"}
            )
            assert marked.status_code == 201, marked.json()
        raise AssertionError(f"{step} was never offered")

    def get(self, path: str) -> Any:
        response = self.client.get(f"{self.project}{path}")
        assert response.status_code == 200, response.text
        return response.json()

    def post(self, path: str, body: Any = None, status: int = 201) -> Any:
        response = self.client.post(f"{self.project}{path}", json=body)
        assert response.status_code == status, response.text
        return response.json()

    def decide(self, document: dict[str, Any], **decision: Any) -> Any:
        (latest,) = [v for v in document["versions"] if v["state"] == "proposed"]
        return self.post(
            f"/documents/{document['document_id']}/decisions",
            {
                "version": latest["version"],
                "digest": latest["digest"],
                "decision": "approved",
                **decision,
            },
        )


def delegated(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    return list(envelope.get("delegations") or [])


@pytest.mark.requirement("R4.2", "R5", "R10.2", "C13.3")
def test_a_researcher_goes_from_their_files_to_a_deposit_package(
    client: TestClient, governance: Governance
) -> None:
    # A turn goes to the orchestrator the deployment's profile names.
    orchestrator = governance.conductor.profile.orchestrator
    assert orchestrator is not None
    researcher = Researcher(client, orchestrator)

    # 1. Inventory: the researcher scans their folder (`dd-inventory`) and attaches the result.
    inventory = make_inventory(SAMPLE, now=MADE_AT, runtime=None)
    entry = client.put(f"{researcher.project}/progress/entry", json={"entry": 3})
    assert entry.status_code == 201, entry.text
    researcher.say("", inventory=inventory)
    assert researcher.get("/inventory")["inventory_files"] == inventory["inventory_files"]

    # 2. Choose ORDA; its requirements are the deployment's DataCite set with ORDA's override.
    response = client.put(f"{researcher.project}/repository", json={"re3data_id": ORDA})
    assert response.status_code == 201, response.json()
    assert response.json()["re3data_id"] == ORDA

    # 3. Draft: each step is delegated, and what it drafts is proposed in the project.
    drafting_runs: dict[str, str] = {}
    for step, kinds in DRAFTING.items():
        envelope = researcher.take_step(step)
        children = delegated(envelope)
        assert children, (researcher.offered(), envelope["payload"])
        assert len(children) == len(kinds)
        assert {c["delegated_status"] for c in children} == {"succeeded"}
        for child in children:
            drafting_runs[child["delegated_invocation_id"]] = child["delegated_agent_id"]
    documents = {d["document_kind"]: d for d in researcher.get("/documents")["documents"]}
    assert set(documents) == set().union(*DRAFTING.values())
    assert all(d["versions"][-1]["state"] == "proposed" for d in documents.values())
    assert {d["versions"][-1]["drafted_by"]["invocation_id"] for d in documents.values()} == set(
        drafting_runs
    )

    # 4. Approve: the README and data dictionary as drafted, the record after an edit.
    for kind in ("readme", "data_dictionary"):
        researcher.decide(documents[kind])
    drafted_record = json.loads(documents["metadata_record"]["versions"][-1]["text"])
    edited = json.dumps({**drafted_record, **WRITTEN_BY_THE_RESEARCHER}, indent=2) + "\n"
    researcher.decide(documents["metadata_record"], reason=REASON, edited_text=edited)
    documents = {d["document_kind"]: d for d in researcher.get("/documents")["documents"]}
    assert all(d["versions"][-1]["state"] == "approved" for d in documents.values())
    record = documents["metadata_record"]
    # The researcher's edit is a version of its own, the one approved.
    assert len(record["versions"]) == 2
    assert json.loads(record["versions"][-1]["text"]) == json.loads(edited)

    # 5. Validate against ORDA.
    validation = researcher.post("/validation")
    assert validation["conforms"], validation["violations"]
    assert validation["violations"] == []

    # 6. Package, and download it by its digest.
    built = researcher.post("/package")
    assert built["conforms"]
    download = client.get(built["package"]["href"])
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/zip"
    package = zipfile.ZipFile(io.BytesIO(download.content))
    names = {n for n in package.namelist() if not n.endswith("/")}

    # The package holds every approved document, the inventory, the requirements, the report,
    # the log, the disclosure, and a crate for every run behind an approved version.
    assert {
        "ro-crate-metadata.json",
        INVENTORY_NAME,
        REQUIREMENTS_NAME,
        REPORT_NAME,
        LOG_NAME,
        STATEMENT_NAME,
        PROVENANCE_NAME,
    } <= names
    assert len([n for n in names if n.startswith("documents/")]) == len(documents)
    for invocation_id in drafting_runs:
        assert f"runs/{invocation_id}/ro-crate-metadata.json" in names
    # The data files are described, not packed.
    assert not names & {f["file_path"] for f in inventory["inventory_files"]}

    # Every run behind an approved version is in the crate, by the agent that drafted it.
    crate = {e["@id"]: e for e in json.loads(package.read("ro-crate-metadata.json"))["@graph"]}
    for invocation_id, agent_id in drafting_runs.items():
        action = crate[f"#run-{invocation_id}"]
        assert action["@type"] == "CreateAction"
        assert crate[action["instrument"]["@id"]]["name"] == agent_id

    # Every decision is in the crate, made by the researcher; the edit's reason goes with it.
    assessments = [e for e in crate.values() if e["@type"] == "AssessAction"]
    assert len(assessments) == len(documents)
    assert {crate[a["agent"]["@id"]]["name"] for a in assessments} == {TEST_PRINCIPAL.name}
    assert REASON in {a.get("description") for a in assessments}

    # The project log, as packaged, records the loop in order, each event for the researcher.
    log = [json.loads(line) for line in package.read(LOG_NAME).decode().splitlines()]
    assert all(e["acted_for"]["principal_id"] == TEST_PRINCIPAL.principal_id for e in log)
    order = [e["event"] for e in log]
    for earlier, later in (
        ("inventory_added", "repository_chosen"),
        ("repository_chosen", "document_version_added"),
        ("document_version_added", "document_version_decided"),
        ("document_version_decided", "project_validated"),
    ):
        assert order.index(earlier) < order.index(later)
    drafts = [e for e in log if e["event"] == "document_version_added" and e.get("drafted_by")]
    assert {e["drafted_by"]["invocation_id"] for e in drafts} == set(drafting_runs)
    assert len([e for e in log if e["event"] == "document_version_decided"]) == len(documents)

    # The log the app keeps ends with the package it built, naming those runs and the report.
    events = governance.projects.events(researcher.project_id)  # type: ignore[union-attr]
    assert events[-1]["event"] == "package_built"
    assert events[-1]["digest"] == built["package"]["digest"]
    assert events[-1]["report_digest"] == built["report_digest"]
    assert set(events[-1]["runs"]) == set(drafting_runs)
