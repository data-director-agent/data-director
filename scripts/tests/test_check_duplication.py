"""Tests for scripts/check_duplication.py: the duplication ratchet, and a canary that plants a copy.

The ratchet's rules are tested on made-up clone reports, so need no jscpd. The canary runs the
pinned jscpd over a copy of the members' sources: the copy passes against the recorded baseline,
then a block planted in two agents must fail it. It needs jscpd installed in scripts/jscpd
(`npm ci --prefix scripts/jscpd --ignore-scripts`) and is skipped without it, except where
DD_REQUIRE_JSCPD is set, as in the CI "Architecture" job, where a missing jscpd is a failure.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_duplication as cd  # noqa: E402

AGENT_A = "agents/advisor-files/src/dd_agent_advisor_files/agent.py"
AGENT_B = "agents/advisor-metadata/src/dd_agent_advisor_metadata/agent.py"

# A block that no member has, planted in two agents to stand for code copied between them.
PLANTED = '''

def _planted_tally(records: list[dict[str, str]], field: str) -> dict[str, int]:
    """Count the records by the value of one field, ignoring blank values."""
    tally: dict[str, int] = {}
    for record in records:
        value = record.get(field, "").strip().casefold()
        if not value:
            continue
        tally[value] = tally.get(value, 0) + 1
    ordered = sorted(tally.items(), key=lambda item: (-item[1], item[0]))
    return {key: count for key, count in ordered if count > 0 and key != "unknown"}
'''


def _clone(first: str, second: str, lines: int, start: int = 1) -> dict[str, object]:
    end = start + lines - 1
    return {
        "lines": lines,
        "firstFile": {"name": first, "start": start, "end": end},
        "secondFile": {"name": second, "start": start, "end": end},
    }


# --- Scope ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "agents/advisor-dmp/src/dd_agent_advisor_dmp/agent.py",
        "harness/src/dd_harness/conductor.py",
        "sdk/browser/src/index.ts",
        "app/web/src/components/project/DeleteProject.tsx",
        "inventory/browser/src/scan.ts",
    ],
)
def test_members_sources_are_in_scope(path: str) -> None:
    assert cd.in_scope(path)


@pytest.mark.parametrize(
    "path",
    [
        "agents/advisor-dmp/tests/test_agent.py",
        "harness/tests/test_conductor.py",
        "app/web/src/App.test.tsx",
        "sdk/src/dd_sdk/schema/generated/core.py",
        "scripts/check_size.py",
        "docs/hooks_inventory.py",
        "app/web/src/vite-env.d.ts",
    ],
)
def test_tests_generated_code_and_tooling_are_out_of_scope(path: str) -> None:
    assert not cd.in_scope(path)


# --- The ratchet ----------------------------------------------------------------------------


def test_clones_are_grouped_by_the_pair_of_files_in_sorted_order(tmp_path: Path) -> None:
    found = cd.by_pair(
        tmp_path,
        [_clone("b.py", "a.py", 6), _clone("a.py", "b.py", 8, start=20), _clone("c.py", "c.py", 5)],
    )
    assert set(found) == {("a.py", "b.py"), ("c.py", "c.py")}
    assert (found[("a.py", "b.py")].clones, found[("a.py", "b.py")].lines) == (2, 14)


def test_absolute_paths_are_made_relative_to_the_root(tmp_path: Path) -> None:
    found = cd.by_pair(tmp_path, [_clone(str(tmp_path / "x" / "a.py"), str(tmp_path / "b.py"), 5)])
    assert set(found) == {("b.py", "x/a.py")}


def test_a_pair_matching_its_entry_passes() -> None:
    found = {("a.py", "b.py"): cd.Shared(2, 14)}
    assert cd.problems(found, {("a.py", "b.py"): cd.Shared(2, 14)}) == []


def test_a_new_pair_is_reported_with_where_the_copies_are(tmp_path: Path) -> None:
    found = cd.by_pair(tmp_path, [_clone("a.py", "b.py", 6, start=10)])
    [problem] = cd.problems(found, {})
    assert "a.py:10-15" in problem and "b.py:10-15" in problem


@pytest.mark.parametrize("grown", [cd.Shared(3, 14), cd.Shared(2, 15)])
def test_a_pair_with_more_blocks_or_lines_than_its_entry_is_reported(grown: cd.Shared) -> None:
    assert cd.problems({("a.py", "b.py"): grown}, {("a.py", "b.py"): cd.Shared(2, 14)})


def test_an_entry_larger_than_its_pair_or_stale_is_reported() -> None:
    baseline = {("a.py", "b.py"): cd.Shared(2, 14), ("c.py", "d.py"): cd.Shared(1, 5)}
    report = cd.problems({("a.py", "b.py"): cd.Shared(1, 6)}, baseline)
    assert len(report) == 2


def test_update_lowers_and_removes_but_never_raises_or_adds() -> None:
    baseline = {
        ("a.py", "b.py"): cd.Shared(2, 14),
        ("c.py", "d.py"): cd.Shared(1, 5),
        ("e.py", "f.py"): cd.Shared(1, 6),
    }
    found = {
        ("a.py", "b.py"): cd.Shared(1, 6),  # shrank
        ("e.py", "f.py"): cd.Shared(2, 9),  # grew
        ("g.py", "h.py"): cd.Shared(1, 5),  # new
    }
    lowered = cd.updated(found, baseline)
    assert {pair: (s.clones, s.lines) for pair, s in lowered.items()} == {
        ("a.py", "b.py"): (1, 6),
        ("e.py", "f.py"): (1, 6),
    }
    # What grew or is new is still reported after the update.
    assert len(cd.problems(found, lowered)) == 2


def test_the_baseline_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "baseline.toml"
    baseline = {("a.py", "b.py"): cd.Shared(2, 14), ("c.py", "c.py"): cd.Shared(1, 5)}
    cd.write_baseline(path, baseline)
    assert cd._same(cd.load_baseline(path), baseline)


def test_the_recorded_baseline_is_in_order_and_names_only_tracked_sources() -> None:
    text = cd.BASELINE.read_text(encoding="utf-8")
    baseline = cd.load_baseline(cd.BASELINE)
    assert text == cd.HEADER + "".join(
        f'\n[[pair]]\nfiles = ["{a}", "{b}"]\nclones = {s.clones}\nlines = {s.lines}\n'
        for (a, b), s in sorted(baseline.items())
    )
    sources = set(cd.tracked(ROOT))
    assert {name for pair in baseline for name in pair} <= sources


# --- The canary -----------------------------------------------------------------------------


def _jscpd_or_skip() -> None:
    try:
        cd.jscpd(install=False)
    except cd.JscpdUnavailableError as error:
        if os.environ.get("DD_REQUIRE_JSCPD"):
            pytest.fail(str(error))
        pytest.skip(str(error))


@pytest.fixture
def copy(tmp_path: Path) -> Path:
    """The members' tracked sources and the recorded baseline, as a git repository."""
    _jscpd_or_skip()
    for path in cd.tracked(ROOT):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / path, target)
    shutil.copy2(cd.BASELINE, tmp_path / "baseline.toml")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    return tmp_path


def _check(root: Path, *argv: str) -> int:
    return cd.main(list(argv), root=root, baseline_path=root / "baseline.toml", install=False)


def test_the_copy_passes(copy: Path) -> None:
    assert _check(copy) == 0


def test_a_block_copied_between_two_agents_fails(
    copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for agent in (AGENT_A, AGENT_B):
        with (copy / agent).open("a", encoding="utf-8") as file:
            file.write(PLANTED)
    capsys.readouterr()
    assert _check(copy) == 1
    out = capsys.readouterr().out
    assert AGENT_A in out and AGENT_B in out


def test_update_does_not_let_the_copy_through(copy: Path) -> None:
    for agent in (AGENT_A, AGENT_B):
        with (copy / agent).open("a", encoding="utf-8") as file:
            file.write(PLANTED)
    before = (copy / "baseline.toml").read_text(encoding="utf-8")
    assert _check(copy, "--update") == 1
    assert (copy / "baseline.toml").read_text(encoding="utf-8") == before


def test_a_raised_entry_fails(copy: Path) -> None:
    baseline = cd.load_baseline(copy / "baseline.toml")
    pair = next(iter(sorted(baseline)))
    baseline[pair] = cd.Shared(baseline[pair].clones + 1, baseline[pair].lines + 10)
    cd.write_baseline(copy / "baseline.toml", baseline)
    assert _check(copy) == 1
