"""Validation of a project against its repository's requirements, and the deposit package built
from a valid one (docs/specs/deposit.md, invariants 7 to 9)."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
import rdflib
from rdflib.namespace import RDF, SH
from requirement_sets import ELSEWHERE, ORDA, override, pinned, standard, write

from dd_harness import server
from dd_harness.deposit import (
    LICENCE_CHECK,
    LOG_NAME,
    PROVENANCE_NAME,
    REPORT_NAME,
    REQUIREMENTS_NAME,
    STATEMENT_NAME,
    VIOLATION,
    WARNING,
    PackageRefusedError,
    build_package,
    validate,
)
from dd_harness.projects import (
    APPROVED,
    PACKAGE_BUILT,
    PROJECT_VALIDATED,
    Decision,
    ProjectStore,
)
from dd_harness.requirements import load_requirements
from dd_harness.store import RunStore
from dd_harness.testing import (
    HARNESS_URL,
    TEST_PRINCIPAL,
    DocumentStub,
    document_request,
    file_inventory,
    make_conductor,
    request,
)
from dd_sdk.contract.models import DocumentKind

# A DataCite record, in its JSON form, with every field the test sets require or recommend.
RECORD: dict[str, Any] = {
    "titles": [{"title": "Soil cores from Hope Valley"}],
    "creators": [{"name": "Carberry, Josiah"}],
    "types": {"resourceTypeGeneral": "Dataset"},
    "subjects": [{"subject": "soil science"}],
    "descriptions": [{"description": "Cores taken in 2026.", "descriptionType": "Abstract"}],
    "rightsList": [
        {
            "rights": "Creative Commons Attribution 4.0 International",
            "rightsIdentifier": "CC-BY-4.0",
            "rightsUri": "https://creativecommons.org/licenses/by/4.0/legalcode",
        }
    ],
}
FILES = ("data/cores.csv", "data/sites.csv")
# Where the document stub is served in process (dd_harness.testing.serving).
STUB_HOST = "stub.document.agents.test"
# rdflib's JSON-LD parser builds a ConjunctiveGraph internally, whatever graph it is given; the
# RO-Crate validator parses the crate with it too.
READS_JSON_LD = pytest.mark.filterwarnings(
    "ignore:ConjunctiveGraph is deprecated:DeprecationWarning"
)


@pytest.fixture(scope="module")
def vcr_config(vcr_config: dict[str, Any]) -> dict[str, Any]:
    """The cassette holds what the RO-Crate validator fetches, never the in-process A2A calls a
    test makes to draft its documents."""
    return {
        **vcr_config,
        "ignore_hosts": [HARNESS_URL.removeprefix("http://"), STUB_HOST],
        # The validator fetches the RO-Crate context once for each check that reads it; the
        # cassette keeps one copy.
        "allow_playback_repeats": True,
    }


@pytest.fixture
def projects(tmp_path: Path) -> ProjectStore:
    return ProjectStore(tmp_path / "projects")


@pytest.fixture
def runs(tmp_path: Path) -> RunStore:
    return RunStore(tmp_path / "runs")


@pytest.fixture
def chosen(projects: ProjectStore, tmp_path: Path) -> str:
    """A project with an inventory of two files and ORDA chosen, and no document."""
    project_id = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test", title="Soil")
    projects.add_inventory(
        project_id, file_inventory(*FILES), acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    choose(projects, project_id, tmp_path)
    return project_id


def choose(projects: ProjectStore, project_id: str, tmp_path: Path, **changes: Any) -> None:
    """Record ORDA as chosen, with its override changed as given."""
    folder = tmp_path / f"repositories-{len(list(tmp_path.glob('repositories-*')))}"
    repositories = write(folder, ("standards", standard()), ("overrides", override(**changes)))
    projects.choose_repository(
        project_id,
        ORDA,
        registry=pinned(folder / "re3data"),
        requirements=load_requirements(repositories),
        acted_for=TEST_PRINCIPAL,
        caused_by="test",
    )


def approve(
    projects: ProjectStore,
    runs: RunStore,
    project_id: str,
    kind: DocumentKind,
    text: str | None = None,
) -> None:
    """Draft a document of `kind` with the stub, its run's crate kept, and approve it: as drafted,
    or edited to `text`."""
    conductor = make_conductor(runs.root, DocumentStub(), crate=True)
    envelope = conductor.invoke(
        request("stub.document", document_request(kind)), acting_for=TEST_PRINCIPAL
    )
    ref = projects.record_draft(project_id, envelope)
    (document,) = [d for d in projects.documents(project_id) if d["document_id"] == ref.document_id]
    decision = Decision(
        ref.document_id,
        ref.version,
        document["versions"][-1]["digest"],
        APPROVED,
        reason="Checked against the field notebook." if text is not None else None,
        edited_text=text,
    )
    projects.decide(project_id, decision, acted_for=TEST_PRINCIPAL, caused_by="test")


@pytest.fixture
def ready(projects: ProjectStore, runs: RunStore, chosen: str) -> str:
    """A project with an approved metadata record and README: valid for ORDA."""
    approve(projects, runs, chosen, DocumentKind.METADATA_RECORD, json.dumps(RECORD))
    approve(projects, runs, chosen, DocumentKind.README)
    return chosen


def messages(results: Any, severity: str) -> list[str]:
    return [r.message for r in results if r.severity == severity]


@pytest.mark.requirement("R4.2")
def test_a_project_without_a_required_document_is_refused_and_says_why(
    projects: ProjectStore, runs: RunStore, chosen: str
) -> None:
    with pytest.raises(PackageRefusedError, match="ORDA requires a metadata record") as refused:
        build_package(projects, runs, chosen, acted_for=TEST_PRINCIPAL, caused_by="test")
    validation = refused.value.validation
    assert not validation.conforms
    assert messages(validation.results, VIOLATION) == [
        "ORDA requires a metadata record, and none has been approved."
    ]
    assert messages(validation.results, WARNING) == [
        "ORDA recommends a README, and none has been approved."
    ]
    # The report is kept, and no package is.
    events = [e["event"] for e in projects.events(chosen)]
    assert events[-1] == PROJECT_VALIDATED
    assert PACKAGE_BUILT not in events
    assert projects.events(chosen)[-1]["conforms"] is False


def test_a_project_with_no_repository_chosen_has_nothing_to_be_valid_against(
    projects: ProjectStore,
) -> None:
    project_id = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    validation = validate(projects, project_id)
    assert not validation.conforms
    assert validation.requirements_digest is None
    assert "No repository has been chosen" in validation.violations[0].message


@pytest.mark.requirement("R4.2")
def test_a_missing_required_field_is_a_violation_and_a_recommended_one_a_warning(
    projects: ProjectStore, runs: RunStore, chosen: str
) -> None:
    """The record's fields are checked by SHACL shapes generated from the merged set: a missing
    required field is an `sh:Violation` naming the repository's form label, a missing
    recommended one an `sh:Warning`."""
    record = {k: v for k, v in RECORD.items() if k != "subjects"}
    approve(projects, runs, chosen, DocumentKind.METADATA_RECORD, json.dumps(record))
    validation = validate(projects, chosen)
    assert messages(validation.results, VIOLATION) == [
        "The metadata record has no Keywords (subjects), which ORDA requires."
    ]
    (keywords,) = validation.violations
    assert keywords.path == "http://schema.org/keywords"
    assert keywords.component == str(SH.MinCountConstraintComponent)

    # An abstract only recommended (the standard's set alone) is a warning when it is missing.
    del record["descriptions"]
    standard_only = ProjectStore(projects.root.parent / "elsewhere")
    project_id = standard_only.create(acted_for=TEST_PRINCIPAL, caused_by="test")
    folder = write(projects.root.parent / "standard-only", ("standards", standard()))
    standard_only.choose_repository(
        project_id,
        ELSEWHERE,
        registry=pinned(folder / "re3data"),
        requirements=load_requirements(folder),
        acted_for=TEST_PRINCIPAL,
        caused_by="test",
    )
    approve(standard_only, runs, project_id, DocumentKind.METADATA_RECORD, json.dumps(record))
    found = validate(standard_only, project_id)
    assert (
        "The metadata record has no descriptions, descriptionType Abstract, which Elsewhere "
        "recommends."
    ) in messages(found.results, WARNING)
    # The warnings from resolving the choice are carried and do not block.
    assert any("no override" in m for m in messages(found.results, WARNING))
    assert [r.message for r in found.violations] == [
        "No inventory of the data files has been added, so the package could not say which "
        "files to deposit in Elsewhere."
    ]


def test_a_record_that_is_not_datacite_json_is_a_violation(
    projects: ProjectStore, runs: RunStore, chosen: str
) -> None:
    approve(projects, runs, chosen, DocumentKind.METADATA_RECORD, "Title: Soil cores")
    (violation,) = validate(projects, chosen).violations
    assert violation.message.startswith("The approved metadata record is not a DataCite record")


def test_a_licence_the_repository_does_not_offer_is_a_violation(
    projects: ProjectStore, runs: RunStore, chosen: str
) -> None:
    record = {**RECORD, "rightsList": [{"rights": "All rights reserved"}]}
    approve(projects, runs, chosen, DocumentKind.METADATA_RECORD, json.dumps(record))
    (violation,) = validate(projects, chosen).violations
    assert violation.component == LICENCE_CHECK
    assert violation.message == (
        "The metadata record's licence (All rights reserved) is not one ORDA accepts: CC-BY-4.0."
    )
    # A licence named by its spdx.org URL is the licence that identifier names.
    spdx = {"rightsUri": "https://spdx.org/licenses/CC-BY-4.0.html"}
    approve(
        projects,
        runs,
        chosen,
        DocumentKind.METADATA_RECORD,
        json.dumps({**RECORD, "rightsList": [spdx]}),
    )
    assert validate(projects, chosen).conforms


def test_inventory_media_types_and_sizes_are_checked_when_the_repository_states_them(
    projects: ProjectStore, runs: RunStore, ready: str, tmp_path: Path
) -> None:
    assert validate(projects, ready).conforms
    choose(
        projects,
        ready,
        tmp_path,
        media_types=["application/zip"],
        max_file_size=5,
        max_item_size=15,
    )
    assert messages(validate(projects, ready).results, VIOLATION) == [
        "data/cores.csv is text/csv, which ORDA does not accept.",
        "data/cores.csv is 10 bytes, over the 5 bytes ORDA accepts for one file.",
        "data/sites.csv is text/csv, which ORDA does not accept.",
        "data/sites.csv is 10 bytes, over the 5 bytes ORDA accepts for one file.",
        "The files come to 20 bytes, over the 15 bytes ORDA accepts for one item.",
    ]


@READS_JSON_LD
def test_the_validation_report_is_a_shacl_validation_report(
    projects: ProjectStore, runs: RunStore, chosen: str
) -> None:
    validation = validate(projects, chosen)
    graph = rdflib.Graph().parse(data=json.dumps(validation.report_jsonld()), format="json-ld")
    (report,) = graph.subjects(RDF.type, SH.ValidationReport)
    assert graph.value(report, SH.conforms) == rdflib.Literal(False)
    results = list(graph.objects(report, SH.result))
    assert len(results) == len(validation.results)
    severities = {graph.value(r, SH.resultSeverity) for r in results}
    assert severities == {SH.Violation, SH.Warning}
    for result in results:
        assert (result, RDF.type, SH.ValidationResult) in graph
        assert graph.value(result, SH.focusNode) is not None
        assert graph.value(result, SH.sourceConstraintComponent) is not None


@READS_JSON_LD
@pytest.mark.requirement("R4.2", "R10.2")
def test_a_valid_project_writes_a_package_with_its_audit_trail(
    projects: ProjectStore, runs: RunStore, ready: str
) -> None:
    package = build_package(projects, runs, ready, acted_for=TEST_PRINCIPAL, caused_by="test")
    assert package.validation.conforms
    # Warnings are shown and do not block.
    assert "ORDA recommends a data dictionary" not in " ".join(
        r.message for r in package.validation.violations
    )

    # Kept by its digest, and recorded in the project log after the report it was built from.
    events = projects.events(ready)
    validated, built = events[-2], events[-1]
    assert (validated["event"], built["event"]) == (PROJECT_VALIDATED, PACKAGE_BUILT)
    assert validated["conforms"] is True
    assert built["digest"] == package.digest
    assert built["report_digest"] == validated["digest"]
    assert built["requirements_digest"] == package.validation.requirements_digest
    assert [d["document_kind"] for d in built["documents"]] == ["metadata_record", "readme"]
    assert len(built["runs"]) == 2
    assert projects.package(ready, package.digest) == package.content

    archive = zipfile.ZipFile(io.BytesIO(package.content))
    names = set(archive.namelist())
    for name in (
        "ro-crate-metadata.json",
        REQUIREMENTS_NAME,
        REPORT_NAME,
        LOG_NAME,
        STATEMENT_NAME,
        PROVENANCE_NAME,
        "inventory.json",
    ):
        assert name in names
    for run in built["runs"]:
        assert f"runs/{run}/ro-crate-metadata.json" in names
    # No data file is in the package.
    assert not any(name.endswith(".csv") for name in names)

    crate = json.loads(archive.read("ro-crate-metadata.json"))
    graph = {entity["@id"]: entity for entity in crate["@graph"]}
    root = graph["./"]
    assert root["name"] == "Soil cores from Hope Valley"
    assert root["description"] == "Cores taken in 2026."
    assert root["license"] == {"@id": "https://creativecommons.org/licenses/by/4.0/legalcode"}
    assert graph[root["creator"]["@id"]]["name"] == "Carberry, Josiah"

    # Each data file is described with its digest and marked as not included.
    for path in FILES:
        entity = graph[f"#file/{path}"]
        assert entity["sha256"] == "a" * 64
        assert entity["includedInPackage"] is False
        assert {"@id": entity["@id"]} in root["hasPart"]

    # Each document names its version, what produced it and the decision that approved it.
    record = next(e for k, e in graph.items() if k.startswith("documents/metadata_record-"))
    assert record["version"] == "2"
    assert json.loads(archive.read(record["@id"])) == RECORD
    made = next(
        e
        for e in graph.values()
        if e.get("@type") == "CreateAction" and e.get("result") == {"@id": record["@id"]}
    )
    assert graph[made["agent"]["@id"]]["name"] == TEST_PRINCIPAL.name
    approval = next(
        e
        for e in graph.values()
        if e.get("@type") == "AssessAction" and e["object"] == {"@id": record["@id"]}
    )
    assert approval["description"] == "Checked against the field notebook."
    assert graph[approval["agent"]["@id"]]["name"] == TEST_PRINCIPAL.name
    readme = next(e for k, e in graph.items() if k.startswith("documents/readme-"))
    drafted = next(
        e
        for e in graph.values()
        if e.get("@type") == "CreateAction" and e.get("result") == {"@id": readme["@id"]}
    )
    assert graph[drafted["instrument"]["@id"]]["name"] == "stub.document"
    assert drafted["subjectOf"]["@id"].startswith("runs/")

    # The audit trail: the log as it stood when the package was built, and the disclosure.
    log = [json.loads(line) for line in archive.read(LOG_NAME).splitlines()]
    assert log == [dict(sorted(e.items())) for e in events[:-1]]
    statement = archive.read(STATEMENT_NAME).decode()
    assert "README" in statement and "Metadata record" in statement
    rdflib.Graph().parse(data=archive.read(PROVENANCE_NAME), format="json-ld")


def test_a_run_that_kept_no_crate_is_named_and_not_made_up(
    projects: ProjectStore, runs: RunStore, chosen: str
) -> None:
    conductor = make_conductor(runs.root, DocumentStub())
    envelope = conductor.invoke(
        request("stub.document", document_request(DocumentKind.METADATA_RECORD)),
        acting_for=TEST_PRINCIPAL,
    )
    ref = projects.record_draft(chosen, envelope)
    digest = projects.documents(chosen)[0]["versions"][-1]["digest"]
    projects.decide(
        chosen,
        Decision(
            ref.document_id,
            ref.version,
            digest,
            APPROVED,
            reason="Wrote the record by hand.",
            edited_text=json.dumps(RECORD),
        ),
        acted_for=TEST_PRINCIPAL,
        caused_by="test",
    )
    package = build_package(projects, runs, chosen, acted_for=TEST_PRINCIPAL, caused_by="test")
    archive = zipfile.ZipFile(io.BytesIO(package.content))
    assert not any(name.startswith("runs/") for name in archive.namelist())
    crate = json.loads(archive.read("ro-crate-metadata.json"))
    (run,) = [e for e in crate["@graph"] if e["@id"] == f"#run-{envelope.invocation_id}"]
    assert run["description"] == "This run kept no Process Run Crate."


@READS_JSON_LD
@pytest.mark.vcr
@pytest.mark.requirement("R4.2")
def test_the_package_passes_the_ro_crate_validator(
    projects: ProjectStore, runs: RunStore, ready: str, tmp_path: Path
) -> None:
    """The package passes the RO-Crate validator's checks at the REQUIRED level. The validator
    fetches the RO-Crate context; the cassette replays it."""
    from rocrate_validator import services
    from rocrate_validator.models import Severity

    package = build_package(projects, runs, ready, acted_for=TEST_PRINCIPAL, caused_by="test")
    path = tmp_path / "package.zip"
    path.write_bytes(package.content)
    settings = services.ValidationSettings(
        rocrate_uri=str(path),
        profile_identifier="ro-crate-1.3",
        requirement_severity=Severity.REQUIRED,
        # Plain requests, which the cassette replays; the validator's HTTP cache is not.
        no_cache=True,
    )
    result = services.validate(settings)
    assert result.passed(), [issue.message for issue in result.issues]


@pytest.fixture
def operator(monkeypatch: pytest.MonkeyPatch, projects: ProjectStore, runs: RunStore) -> None:
    monkeypatch.setenv("DD_PROJECTS_DIR", str(projects.root))
    monkeypatch.setenv("DD_RUNS_DIR", str(runs.root))
    monkeypatch.setenv("DD_PRINCIPAL_ID", TEST_PRINCIPAL.principal_id)
    monkeypatch.setenv("DD_PRINCIPAL_NAME", TEST_PRINCIPAL.name)


@pytest.mark.usefixtures("operator")
def test_the_validate_command_keeps_the_report_and_exits_1_on_a_violation(
    projects: ProjectStore, chosen: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert server.main(["project", "validate", chosen]) == 1
    out, err = capsys.readouterr()
    assert out.strip() == projects.events(chosen)[-1]["digest"]
    assert "dd-harness: violation: ORDA requires a metadata record" in err
    assert "dd-harness: warning: ORDA recommends a README" in err
    assert projects.events(chosen)[-1]["caused_by"] == "dd-harness project validate"


@pytest.mark.usefixtures("operator")
def test_the_package_command_writes_the_package_or_says_why_not(
    projects: ProjectStore,
    runs: RunStore,
    chosen: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out_file = tmp_path / "package.zip"
    assert server.main(["project", "package", chosen, "-o", str(out_file)]) == 1
    _, err = capsys.readouterr()
    assert "violation: ORDA requires a metadata record" in err
    assert "no package was built" in err
    assert not out_file.exists()

    approve(projects, runs, chosen, DocumentKind.METADATA_RECORD, json.dumps(RECORD))
    assert server.main(["project", "package", chosen, "-o", str(out_file)]) == 0
    out, _ = capsys.readouterr()
    built = projects.events(chosen)[-1]
    assert built["event"] == PACKAGE_BUILT
    assert built["caused_by"] == "dd-harness project package"
    assert out.strip() == built["digest"]
    assert out_file.read_bytes() == projects.package(chosen, built["digest"])
