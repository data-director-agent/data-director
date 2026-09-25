"""The source check (ADR-0016): cited records re-hashed against a pinned copy of the source."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from dd_agent_factcheck.agent import FactChecker
from dd_agent_r3.agent import R3Agent
from dd_agent_r3.explain import TemplateExplainer
from dd_agent_r3.fairsharing.snapshot import SnapshotBackend
from dd_sdk.contract.models import GroundingMode, OutcomeStatus, parse_input
from dd_sdk.evidence import DOCUMENT_CANONICALISATION, content_hash
from workbench import cli
from workbench import testing as fakes
from workbench.settings import DEFAULT_SOURCES_CONFIG, ROOT
from workbench.sources import RecordsFile, SourceConfigError, Sources, check

pytestmark = pytest.mark.requirement("DD-EVIDENCE")

SNAPSHOT_REF = "test:records"
RECORD = {"source_id": "src:a", "text": "Alpha."}


def _pinned(tmp_path: Path, rows: list[dict[str, Any]]) -> tuple[Path, str]:
    path = tmp_path / "records.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def _sources(tmp_path: Path, rows: list[dict[str, Any]] | None = None) -> Sources:
    path, pin = _pinned(tmp_path, [RECORD] if rows is None else rows)
    return Sources({SNAPSHOT_REF: RecordsFile.load(path, "source_id", pin)})


def _evidence(
    source_id: str = "src:a",
    document: dict[str, Any] = RECORD,
    snapshot_ref: str | None = SNAPSHOT_REF,
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "snapshot_ref": snapshot_ref,
        "canonicalisation": DOCUMENT_CANONICALISATION,
        "content_hash": content_hash(document, DOCUMENT_CANONICALISATION),
        "content": document,
    }


def _envelope(*evidence: dict[str, Any], mode: str = "retrieval") -> dict[str, Any]:
    return {"grounding_mode": mode, "evidence": list(evidence)}


# --- Configuration ----------------------------------------------------------------------------


def test_a_file_that_does_not_match_its_pin_is_a_configuration_error(tmp_path: Path) -> None:
    path, _ = _pinned(tmp_path, [RECORD])
    with pytest.raises(SourceConfigError, match="not the pinned"):
        RecordsFile.load(path, "source_id", "0" * 64)


def test_config_resolves_paths_beside_the_file(tmp_path: Path) -> None:
    path, pin = _pinned(tmp_path, [RECORD])
    config = tmp_path / "sources.yaml"
    config.write_text(
        f"sources:\n  - snapshot_refs: [{SNAPSHOT_REF}]\n    path: {path.name}\n"
        f"    id_field: source_id\n    sha256: {pin}\n",
        encoding="utf-8",
    )
    assert Sources.from_config(config).by_snapshot_ref[SNAPSHOT_REF].record("src:a") == RECORD


def test_the_committed_source_copies_match_their_pins() -> None:
    assert Sources.from_config(DEFAULT_SOURCES_CONFIG).by_snapshot_ref


# --- Rules ------------------------------------------------------------------------------------


def test_evidence_matching_the_source_is_verified(tmp_path: Path) -> None:
    report = check(_envelope(_evidence()), _sources(tmp_path))
    assert report.passed and report.verified == 1 and not report.unresolved


def test_evidence_from_a_source_with_no_copy_is_unresolved_not_verified(tmp_path: Path) -> None:
    report = check(_envelope(_evidence(snapshot_ref="live")), _sources(tmp_path))
    assert report.passed and report.verified == 0
    assert report.unresolved == ["src:a (live)"]
    assert "0 verified, 1 unresolved" in report.summary()


def test_s1_a_cited_record_the_source_does_not_hold(tmp_path: Path) -> None:
    invented = {"source_id": "src:invented", "text": "Plausible."}
    report = check(_envelope(_evidence("src:invented", invented)), _sources(tmp_path))
    assert [v[:3] for v in report.violations] == ["S1:"]


def test_s2_content_consistent_with_its_hash_but_not_with_the_source(tmp_path: Path) -> None:
    # The agent altered the record and re-hashed it: E1 passes, the source check does not.
    altered = {"source_id": "src:a", "text": "Alpha, revised."}
    report = check(_envelope(_evidence("src:a", altered)), _sources(tmp_path))
    assert [v[:3] for v in report.violations] == ["S2:"]


def test_input_and_delegation_evidence_is_left_to_the_linter_outside_retrieval(
    tmp_path: Path,
) -> None:
    cited = [_evidence("input:x", snapshot_ref=None), _evidence("invocation:y", snapshot_ref=None)]
    for mode in ("input_only", "none", "delegation"):
        report = check(_envelope(*cited, mode=mode), _sources(tmp_path))
        assert report.passed and report.verified == 0 and not report.unresolved
    # In retrieval mode no linter rule holds such a citation to the conductor's hashes.
    report = check(_envelope(*cited, mode="retrieval"), _sources(tmp_path))
    assert len(report.unresolved) == 2


# --- Conductor --------------------------------------------------------------------------------


def _fact_check(tmp_path: Path, source: fakes.Retrieve, sources: Sources) -> Any:
    def result(request: Any, ctx: Any) -> Any:
        out = fakes.fact_check_over(source)
        evidence = [e.model_copy(update={"snapshot_ref": SNAPSHOT_REF}) for e in out.evidence]
        return replace(out, evidence=evidence)

    agent = fakes.ScriptedAgent(GroundingMode.RETRIEVAL, result, steps=[source])
    conductor = fakes.make_conductor(tmp_path / "runs", agent)
    conductor.sources = sources
    envelope = conductor.invoke(fakes.request("fake.retrieval", fakes.claim()))
    return envelope, conductor.store.run_dir(envelope.invocation_id)


def test_conductor_withholds_a_result_citing_a_record_the_source_does_not_hold(
    tmp_path: Path,
) -> None:
    invented = fakes.Retrieve("src:invented", {"source_id": "src:invented", "text": "Beta."})
    envelope, run_dir = _fact_check(tmp_path, invented, _sources(tmp_path))
    # The agent's own account is consistent, so the linter passes; the source check does not.
    assert (run_dir / "grounding.txt").read_text().startswith("grounding: passed")
    assert envelope.outcome.status == OutcomeStatus.FAILED
    assert envelope.payload is None
    assert "the source check" in (envelope.outcome.statement or "")
    assert "S1:" in (run_dir / "sources.txt").read_text()


def test_conductor_records_a_verified_result(tmp_path: Path) -> None:
    source = fakes.Retrieve("src:a", RECORD)
    envelope, run_dir = _fact_check(tmp_path, source, _sources(tmp_path))
    assert envelope.outcome.status == OutcomeStatus.SUCCEEDED
    assert (run_dir / "sources.txt").read_text() == "sources: 1 verified, 0 unresolved\n"


# --- Real agents against the committed copies -------------------------------------------------


def _sample(name: str) -> Any:
    return parse_input(json.loads((ROOT / "samples" / name).read_text(encoding="utf-8")))


@pytest.mark.parametrize(
    ("agent", "sample"),
    [
        (
            R3Agent(retrieval=SnapshotBackend(), explainer=TemplateExplainer()),
            "soil-chemistry.profile.json",
        ),
        (FactChecker(), "claim.json"),
    ],
    ids=["r3", "fact.checker"],
)
def test_real_agents_evidence_verifies_against_the_committed_copies(
    tmp_path: Path, agent: Any, sample: str
) -> None:
    conductor = fakes.make_conductor(tmp_path / "runs", agent)
    conductor.sources = Sources.from_config(DEFAULT_SOURCES_CONFIG)
    request = fakes.request(agent.spec.agent_id, _sample(sample), bundle="profile:default")
    envelope = conductor.invoke(request)
    assert envelope.outcome.status == OutcomeStatus.SUCCEEDED, envelope.outcome.statement
    report = check(envelope.to_document(), conductor.sources)
    assert report.passed and report.verified > 0 and not report.unresolved


# --- CLI --------------------------------------------------------------------------------------


def test_verify_exits_non_zero_on_a_violation(tmp_path: Path, capsys: Any) -> None:
    path, pin = _pinned(tmp_path, [RECORD])
    config = tmp_path / "sources.yaml"
    config.write_text(
        f"sources:\n  - snapshot_refs: [{SNAPSHOT_REF}]\n    path: {path.name}\n"
        f"    id_field: source_id\n    sha256: {pin}\n",
        encoding="utf-8",
    )
    good, bad = tmp_path / "good.json", tmp_path / "bad.json"
    good.write_text(json.dumps(_envelope(_evidence())), encoding="utf-8")
    altered = {"source_id": "src:a", "text": "Alpha, revised."}
    bad.write_text(json.dumps(_envelope(_evidence("src:a", altered))), encoding="utf-8")
    assert cli.main(["verify", str(good), "--sources", str(config)]) == 0
    assert cli.main(["verify", str(bad), "--sources", str(config)]) == 1
    assert "S2:" in capsys.readouterr().out
