"""The command line. An instrument, so the tests are about it not lying."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from standards_advisor.cli import main


@pytest.fixture
def run_argv(tmp_path: Path, project_root: Path):
    """Build an argv, resolving sample paths so the tests do not depend on the cwd."""

    def build(*extra: str) -> list[str]:
        resolved = [
            str(project_root / item) if item.startswith("samples/") else item for item in extra
        ]
        return [
            "--project-root",
            str(project_root),
            "--runs-root",
            str(tmp_path / "runs"),
            *resolved,
        ]

    return build


def test_a_run_succeeds_and_says_review_is_required(run_argv, capsys):
    sample = "samples/soil-chemistry.csv"
    code = main(run_argv("run", sample))
    assert code == 0

    out = capsys.readouterr().out
    # C15 makes review mandatory and the document cannot express it as false. The interface
    # saying so is the other half of that.
    assert "requires human review" in out
    assert "nothing found: 4" in out


def test_a_run_reports_the_registry_as_stale(run_argv, capsys):
    main(run_argv("run", "samples/soil-chemistry.csv"))
    out = capsys.readouterr().out
    # §7.3: the snapshot date must be visible in the interface, not just in a log.
    assert "registry: unavailable (stale)" in out


def test_json_output_is_the_document(run_argv, capsys):
    main(run_argv("run", "samples/soil-chemistry.csv", "--json"))
    payload = json.loads(capsys.readouterr().out)
    assert payload["requires_human_review"] is True
    assert payload["recommendations"] == []
    assert len(payload["nothing_found"]) == 4


def test_show_run_summarises_a_past_run(run_argv, capsys, tmp_path: Path):
    main(run_argv("run", "samples/soil-chemistry.csv"))
    capsys.readouterr()

    run_id = next(p.name for p in (tmp_path / "runs").iterdir() if p.is_dir())
    assert main(run_argv("show-run", run_id)) == 0

    out = capsys.readouterr().out
    assert run_id in out
    for stage in ("profile", "retrieve", "rank", "explain", "check", "assemble"):
        assert stage in out
    assert "events:" in out


def test_show_run_on_an_unknown_id_fails_clearly(run_argv, capsys):
    assert main(run_argv("show-run", "nope")) == 2
    assert "no run record" in capsys.readouterr().err


def test_a_missing_input_file_is_reported_but_does_not_crash(run_argv, capsys):
    """A bad path is a content problem, recorded as a failure, not an exception."""
    code = main(run_argv("run", "samples/does-not-exist.csv"))
    assert code == 0
    out = capsys.readouterr().out
    assert "complete_with_failures" in out
    assert "nothing found: 4" in out


def test_export_schemas_is_idempotent(run_argv, capsys):
    assert main(run_argv("export-schemas")) == 0
    assert "already current" in capsys.readouterr().out


def test_the_version_flag_works(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
